"""Envío al servidor propio (nube o servidor de planta) por HTTPS, con cola en disco.

* Los eventos, tendencias y capturas de problemas se guardan primero en `<datos>/envio_servidor/` (un archivo por
  lote) y se borran solo cuando el servidor confirma. Así un corte de red o un reinicio no pierden datos.
* Cada lote lleva un id: si se reenvía (p. ej. se cortó la red antes de la respuesta) el servidor lo ignora.
* El estado actual no se encola: solo importa el último, que se envía junto con los lotes o solo cada
  `heartbeat_s` cuando no cambia nada.
* Todo va comprimido (gzip) y en un hilo propio: el monitoreo nunca espera a la red.
* Solo hay conexiones de salida desde el HMI hacia el servidor; el servidor nunca le envía órdenes.
"""
from __future__ import annotations

import gzip
import json
import logging
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Callable, Optional

from . import __version__

log = logging.getLogger(__name__)

PROTOCOL = 1
QUEUE_DIR = "envio_servidor"
MAX_QUEUE_BYTES = 300 * 1024 * 1024  # al pasar este tamaño se descartan los lotes más viejos
MAX_BATCH_ITEMS = 5000
TIMEOUT_S = 15.0


class ServerError(RuntimeError):
    def __init__(self, msg: str, status: Optional[int] = None):
        super().__init__(msg)
        self.status = status


def _url(base: str, path: str) -> str:
    return base.rstrip("/") + path


def request(base: str, path: str, method: str = "GET", body: Optional[dict] = None, token: str = "",
            headers: Optional[dict] = None, verify: bool = True, timeout: float = TIMEOUT_S) -> dict:
    """Petición JSON al servidor (comprimida si lleva cuerpo). Lanza ServerError con un mensaje claro."""
    data = None
    h = {"Accept": "application/json", "User-Agent": f"ExtrusionMonitor/{__version__}"}
    if body is not None:
        data = gzip.compress(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        h.update({"Content-Type": "application/json", "Content-Encoding": "gzip"})
    if token:
        h["Authorization"] = f"Bearer {token}"
    h.update(headers or {})
    req = urllib.request.Request(_url(base, path), data=data, method=method, headers=h)
    ctx = None
    if base.lower().startswith("https") and not verify:
        ctx = ssl._create_unverified_context()  # solo para certificados internos de prueba
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("detail")
        except Exception:
            detail = None
        raise ServerError(str(detail or f"HTTP {exc.code}"), exc.code) from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        raise ServerError(f"sin conexión con el servidor ({reason})") from exc


def register(base: str, enroll_key: str, line_id: str, line_name: str, area: str, verify: bool = True) -> str:
    """Registra la línea con la clave de registro del servidor y devuelve su clave propia."""
    res = request(base, "/api/v1/register", "POST",
                  {"line_id": line_id, "line_name": line_name, "area": area, "app_version": __version__},
                  headers={"X-Enroll-Key": enroll_key}, verify=verify)
    return res["token"]


class CloudOutbox:
    """Cola en disco y envío en segundo plano."""

    def __init__(self, home: Path, settings_fn: Callable, sender: Callable = request, clock=time.time):
        self.dir = Path(home) / QUEUE_DIR
        self.settings_fn = settings_fn  # StationSettings actual
        self.sender = sender
        self.clock = clock
        self._lock = threading.Lock()
        self._status: Optional[dict] = None
        self._status_dirty = False
        self._status_sent_at = 0.0
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_ok: Optional[float] = None
        self.last_error = ""
        self.dropped = 0
        self._seq = 0
        self._backoff = 0.0

    # --- entrada (hilo del exportador) --------------------------------------------------------------
    def enqueue(self, events: list[dict], trend: list[dict], problems: Optional[list[dict]] = None) -> None:
        items = list(events), list(trend), list(problems or [])
        if not any(items):
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        ev, tr, pr = items
        while ev or tr or pr:  # lotes de tamaño acotado
            batch = {"batch_id": uuid.uuid4().hex, "created": self.clock(), "events": ev[:MAX_BATCH_ITEMS],
                     "trend": tr[:MAX_BATCH_ITEMS], "problems": pr[:MAX_BATCH_ITEMS]}
            ev, tr, pr = ev[MAX_BATCH_ITEMS:], tr[MAX_BATCH_ITEMS:], pr[MAX_BATCH_ITEMS:]
            # el nombre ordena los lotes por creación (se envían en ese orden)
            self._seq = max(self._seq + 1, time.time_ns())
            name = f"{self._seq:020d}-{batch['batch_id'][:8]}.json"
            tmp = self.dir / (name + ".tmp")
            tmp.write_bytes(gzip.compress(json.dumps(batch, ensure_ascii=False).encode("utf-8")))
            tmp.replace(self.dir / name)
        self._trim()
        self._wake.set()

    def set_status(self, status: dict) -> None:
        with self._lock:
            self._status = status
            self._status_dirty = True

    def pending(self) -> list[Path]:
        return sorted(self.dir.glob("*.json")) if self.dir.is_dir() else []

    def pending_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.pending())

    def _trim(self) -> None:
        files = self.pending()
        total = sum(p.stat().st_size for p in files)
        while files and total > MAX_QUEUE_BYTES:
            p = files.pop(0)
            total -= p.stat().st_size
            p.unlink(missing_ok=True)
            self.dropped += 1
            log.warning("Cola del servidor llena: se descartó el lote %s", p.name)

    # --- envío --------------------------------------------------------------------------------------
    def flush(self, force_status: bool = False, timeout: float = TIMEOUT_S) -> bool:
        """Envía los lotes pendientes (del más viejo al más nuevo) y el estado. True si todo salió."""
        s = self.settings_fn()
        if not (s.server_enabled and s.server_url and s.server_token):
            return False
        base, token, verify = s.server_url, s.server_token, s.server_verify_tls
        try:
            for p in self.pending():
                try:
                    batch = json.loads(gzip.decompress(p.read_bytes()))
                except (OSError, ValueError):
                    log.warning("Lote dañado descartado: %s", p.name)
                    p.unlink(missing_ok=True)
                    continue
                batch.pop("created", None)
                batch["protocol"] = PROTOCOL
                with self._lock:
                    if self._status is not None:
                        batch["status"] = self._status
                        self._status_dirty = False
                self.sender(base, "/api/v1/ingest", "POST", batch, token=token, verify=verify, timeout=timeout)
                p.unlink(missing_ok=True)
                self._status_sent_at = self.clock()
            with self._lock:
                status = self._status
                due = self._status_dirty and (force_status or self.clock() - self._status_sent_at >= s.server_interval_s)
                stale = self.clock() - self._status_sent_at >= s.server_heartbeat_s
            if status is not None and (due or stale):
                self.sender(base, "/api/v1/ingest", "POST", {"protocol": PROTOCOL, "status": status},
                            token=token, verify=verify, timeout=timeout)
                with self._lock:
                    if self._status is status:
                        self._status_dirty = False
                self._status_sent_at = self.clock()
        except ServerError as exc:
            if str(exc) != self.last_error:
                log.warning("Servidor: %s", exc)
            self.last_error = str(exc)
            self._backoff = min(60.0, max(2.0, self._backoff * 2))
            return False
        self.last_ok = self.clock()
        self.last_error = ""
        self._backoff = 0.0
        return True

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="envio-servidor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(TIMEOUT_S + 2)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.flush()
            except Exception:  # nunca debe caerse el hilo
                log.exception("Envío al servidor")
            s = self.settings_fn()
            self._wake.wait(max(1.0, self._backoff or min(s.server_interval_s, 5.0)))
            self._wake.clear()
