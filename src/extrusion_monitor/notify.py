"""Notificaciones por correo, Telegram o webhook (Teams / Slack / Google Chat / propio) de las alertas elegidas.

Las reglas se evalúan con cada lectura (hilo del motor) y los envíos van por un hilo aparte con reintentos,
para no frenar el monitoreo. Cada alerta tiene un tiempo de espera para no repetir el mismo aviso. La
configuración es de la estación (no de la receta) y se guarda en `<datos>/notificaciones.json`; contraseñas y
tokens van cifrados (ver `secrets_store`).
"""
from __future__ import annotations

import json
import logging
import queue
import smtplib
import ssl
import threading
import time
import urllib.request
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Optional

from .i18n import tr, translate_text
from .secrets_store import protect, unprotect

log = logging.getLogger(__name__)

# clave -> (nombre, unidad del umbral o "", umbral por defecto, activa por defecto)
RULES = {
    "alarm": ("Variable fuera de límite (alarma)", "", None, True),
    "warn": ("Variable en aviso (fuera de la tolerancia de aviso)", "", None, False),
    "read_error": ("Error de lectura de una variable", "s sin lectura", 60.0, True),
    "screen": ("Pantalla del HMI o cámara sin imagen", "", None, True),
    "stop": ("Paro de máquina", "min detenida", 5.0, True),
    "stop_total": ("Tiempo de paro acumulado en el turno", "min", 30.0, False),
    "scrap": ("Desperdicio alto en una captura", "(unidad de longitud)", 50.0, True),
    "scrap_shift": ("Desperdicio acumulado en el turno", "(unidad de longitud)", 200.0, False),
    "low_cpk": ("Cpk bajo (sostenido 5 min)", "Cpk menor que", 1.0, False),
    "low_oee": ("OEE bajo al cerrar el turno", "% menor que", 60.0, False),
    "behavior": ("Comportamiento anormal (IA)", "", None, True),
    "drift": ("Tendencia que alcanzará el límite", "", None, False),
    "control": ("Control automático detenido por seguridad o en alarma", "", None, True),
    "supervisor": ("Inicio de sesión de supervisor", "", None, True),
    "recipe": ("Cambio de receta", "", None, False),
    "monitor": ("Monitoreo detenido o programa cerrado", "", None, True),
    "report": ("Reportes de análisis programados (adjunta el PDF)", "", None, False),
}
WEBHOOK_KINDS = {"teams": "Microsoft Teams", "slack": "Slack", "gchat": "Google Chat", "generic": "Otro (JSON)"}
CPK_HOLD_S = 300.0
RETRIES = 3


@dataclass
class EmailSettings:
    enabled: bool = False
    host: str = ""
    port: int = 587
    security: str = "starttls"  # starttls | ssl | none
    user: str = ""
    password: str = ""  # cifrada
    sender: str = ""
    to: list[str] = field(default_factory=list)


@dataclass
class TelegramSettings:
    enabled: bool = False
    token: str = ""  # cifrado
    chat_ids: list[str] = field(default_factory=list)


@dataclass
class WebhookSettings:
    enabled: bool = False
    url: str = ""  # cifrada (lleva la clave del canal)
    kind: str = "teams"


@dataclass
class RuleSettings:
    enabled: bool = False
    threshold: Optional[float] = None


@dataclass
class NotifySettings:
    email: EmailSettings = field(default_factory=EmailSettings)
    telegram: TelegramSettings = field(default_factory=TelegramSettings)
    webhook: WebhookSettings = field(default_factory=WebhookSettings)
    rules: dict[str, RuleSettings] = field(default_factory=lambda: {
        k: RuleSettings(v[3], v[2]) for k, v in RULES.items()})
    cooldown_min: float = 15.0  # el mismo aviso no se repite antes de este tiempo
    quiet: bool = False  # pausa todos los envíos (mantenimiento)

    @staticmethod
    def file(home: Path) -> Path:
        return Path(home) / "notificaciones.json"

    @classmethod
    def load(cls, home: Path) -> "NotifySettings":
        s = cls()
        try:
            d = json.loads(cls.file(home).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return s
        try:
            e = d.get("email") or {}
            s.email = EmailSettings(bool(e.get("enabled")), str(e.get("host", "")), int(e.get("port", 587)),
                                    e.get("security", "starttls") if e.get("security") in ("starttls", "ssl", "none")
                                    else "starttls", str(e.get("user", "")), str(e.get("password", "")),
                                    str(e.get("sender", "")), [str(x) for x in e.get("to", []) if str(x).strip()])
            t = d.get("telegram") or {}
            s.telegram = TelegramSettings(bool(t.get("enabled")), str(t.get("token", "")),
                                          [str(x) for x in t.get("chat_ids", []) if str(x).strip()])
            w = d.get("webhook") or {}
            s.webhook = WebhookSettings(bool(w.get("enabled")), str(w.get("url", "")),
                                        w.get("kind", "teams") if w.get("kind") in WEBHOOK_KINDS else "teams")
            for k, r in (d.get("rules") or {}).items():
                if k in RULES and isinstance(r, dict):
                    th = r.get("threshold")
                    s.rules[k] = RuleSettings(bool(r.get("enabled")), float(th) if th is not None else RULES[k][2])
            s.cooldown_min = float(d.get("cooldown_min", 15.0))
            s.quiet = bool(d.get("quiet", False))
        except (TypeError, ValueError, AttributeError):
            log.warning("notificaciones.json con datos inválidos; se usan los valores por defecto")
        return s

    def save(self, home: Path) -> None:
        f = self.file(home)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(f)

    # contraseñas y tokens
    def set_secret(self, which: str, value: str) -> None:
        enc = protect(value)
        if which == "email":
            self.email.password = enc
        elif which == "telegram":
            self.telegram.token = enc
        elif which == "webhook":
            self.webhook.url = enc

    def secret(self, which: str) -> str:
        return unprotect({"email": self.email.password, "telegram": self.telegram.token,
                          "webhook": self.webhook.url}[which])

    def channels(self) -> list[str]:
        out = []
        if self.email.enabled and self.email.host and self.email.to:
            out.append("email")
        if self.telegram.enabled and self.telegram.token and self.telegram.chat_ids:
            out.append("telegram")
        if self.webhook.enabled and self.webhook.url:
            out.append("webhook")
        return out

    def on(self, rule: str) -> bool:
        r = self.rules.get(rule)
        return bool(r and r.enabled)

    def th(self, rule: str) -> Optional[float]:
        r = self.rules.get(rule)
        return r.threshold if r is not None and r.threshold is not None else RULES[rule][2]


@dataclass
class Message:
    rule: str
    subject: str
    body: str
    level: str = "ALARMA"  # ALARMA | AVISO | INFO
    attachment: Optional[Path] = None
    ts: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


# --- envío -------------------------------------------------------------------------------------------


def send_email(s: NotifySettings, msg: Message, timeout: float = 20) -> None:
    e = s.email
    m = EmailMessage()
    m["Subject"] = msg.subject
    m["From"] = e.sender or e.user
    m["To"] = ", ".join(e.to)
    m.set_content(msg.body)
    if msg.attachment is not None and Path(msg.attachment).exists():
        data = Path(msg.attachment).read_bytes()
        m.add_attachment(data, maintype="application", subtype="pdf", filename=Path(msg.attachment).name)
    ctx = ssl.create_default_context()
    if e.security == "ssl":
        srv = smtplib.SMTP_SSL(e.host, e.port or 465, timeout=timeout, context=ctx)
    else:
        srv = smtplib.SMTP(e.host, e.port or 587, timeout=timeout)
    try:
        if e.security == "starttls":
            srv.starttls(context=ctx)
        pw = s.secret("email")
        if e.user and pw:
            srv.login(e.user, pw)
        srv.send_message(m)
    finally:
        try:
            srv.quit()
        except Exception:
            pass


def _post(url: str, data: bytes, content_type: str, timeout: float = 20) -> None:
    req = urllib.request.Request(url, data=data, headers={"Content-Type": content_type}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (URL configurada por el usuario)
        if r.status >= 300:
            raise OSError(f"HTTP {r.status}")


def send_telegram(s: NotifySettings, msg: Message, timeout: float = 20) -> None:
    token = s.secret("telegram")
    base = f"https://api.telegram.org/bot{token}"
    for chat in s.telegram.chat_ids:
        if msg.attachment is not None and Path(msg.attachment).exists():
            boundary = uuid.uuid4().hex
            parts = []
            for name, value in (("chat_id", chat), ("caption", f"{msg.subject}\n\n{msg.body}"[:1000])):
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n"
                             .encode())
            fname = Path(msg.attachment).name
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{fname}\"\r\n"
                         "Content-Type: application/pdf\r\n\r\n".encode() + Path(msg.attachment).read_bytes() + b"\r\n")
            parts.append(f"--{boundary}--\r\n".encode())
            _post(base + "/sendDocument", b"".join(parts), f"multipart/form-data; boundary={boundary}", timeout)
        else:
            body = json.dumps({"chat_id": chat, "text": f"{msg.subject}\n\n{msg.body}"}).encode()
            _post(base + "/sendMessage", body, "application/json", timeout)


def send_webhook(s: NotifySettings, msg: Message, timeout: float = 20) -> None:
    url = s.secret("webhook")
    text = f"**{msg.subject}**\n\n{msg.body}" if s.webhook.kind in ("teams", "gchat") else f"*{msg.subject}*\n{msg.body}"
    if s.webhook.kind == "generic":
        payload = {"title": msg.subject, "text": msg.body, "level": msg.level, "rule": msg.rule, "ts": msg.ts}
    else:
        payload = {"text": text}
    _post(url, json.dumps(payload).encode(), "application/json", timeout)


SENDERS = {"email": send_email, "telegram": send_telegram, "webhook": send_webhook}


# --- notificador ---------------------------------------------------------------------------------------


class Notifier:
    """Evalúa las alertas elegidas y envía los avisos por los canales configurados."""

    def __init__(self, home: Path, engine=None, clock: Callable[[], float] = time.time,
                 who: Callable[[], str] = lambda: "", where: Callable[[], str] = lambda: "",
                 senders: Optional[dict] = None, on_result: Optional[Callable[[Message, str, str], None]] = None):
        self.home = Path(home)
        self.engine = engine
        self.clock = clock
        self.who, self.where = who, where
        self.senders = senders or SENDERS
        self.on_result = on_result
        self.settings = NotifySettings.load(self.home)
        self._last: dict[tuple[str, str], float] = {}
        self._seen: dict[tuple[str, str], float] = {}  # hallazgos ya avisados
        self._stop_since: Optional[float] = None
        self._stop_sent = False
        self._shift_key: Optional[float] = None
        self._stop_acc = 0.0
        self._stop_total_sent = False
        self._cpk_low: dict[str, float] = {}
        self._queue: "queue.Queue[Optional[Message]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self.history: deque = deque(maxlen=100)  # (ts, canal, estado, asunto)
        self.sent: list[Message] = []  # para pruebas

    def reload(self) -> None:
        self.settings = NotifySettings.load(self.home)

    # --- envío con espera entre avisos ---
    def emit(self, rule: str, key: str, subject: str, body: str, level: str = "ALARMA",
             attachment: Optional[Path] = None, force: bool = False) -> bool:
        s = self.settings
        if s.quiet or not (force or s.on(rule)) or not s.channels():
            return False
        now = self.clock()
        k = (rule, key)
        if not force and now - self._last.get(k, -1e18) < s.cooldown_min * 60:
            return False
        self._last[k] = now
        where = self.where()
        who = self.who()
        # en el idioma de la interfaz (los mensajes del motor se traducen por plantilla)
        subject, body = translate_text(subject), translate_text(body)
        lines = [body, "", time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(now))]
        if where:
            lines.append(where)
        if who:
            lines.append(tr("Usuario en turno: {u}", u=who))
        recipe = getattr(getattr(self.engine, "state", None), "recipe", None)
        if recipe:
            lines.append(tr("Receta: {r}", r=recipe))
        msg = Message(rule, f"[{where or tr('Monitor')}] {tr(level)}: {subject}", "\n".join(lines), level,
                      attachment, now)
        self._queue.put(msg)
        self._ensure_thread()
        return True

    def _ensure_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._worker, name="notificaciones", daemon=True)
            self._thread.start()

    def _worker(self) -> None:
        while True:
            try:
                msg = self._queue.get(timeout=30)
            except queue.Empty:
                return
            if msg is None:
                self._queue.task_done()
                return
            for ch in self.settings.channels():
                status = "ok"
                for attempt in range(RETRIES):
                    try:
                        self.senders[ch](self.settings, msg)
                        status = "ok"
                        break
                    except Exception as e:  # sin red, credenciales…: se reintenta y se registra
                        status = f"error: {e}"
                        time.sleep(min(10, 2 ** attempt) if self.senders is SENDERS else 0)
                self.history.append((time.time(), ch, status, msg.subject))
                if self.on_result:
                    try:
                        self.on_result(msg, ch, status)
                    except Exception:
                        log.exception("registro de notificación")
            self.sent.append(msg)
            self._queue.task_done()

    def flush(self, timeout: float = 10.0) -> None:
        """Espera a que salgan los avisos encolados (al cerrar el programa y en pruebas)."""
        t0 = time.monotonic()
        while self._queue.unfinished_tasks and time.monotonic() - t0 < timeout:
            time.sleep(0.05)

    def test(self) -> dict[str, str]:
        """Envía un mensaje de prueba por cada canal ahora mismo (sin cola) y devuelve el resultado."""
        msg = Message("test", translate_text(f"[{self.where() or 'Monitor'}] Prueba de notificaciones"),
                      tr("Si recibes este mensaje, las notificaciones de esta estación funcionan."), "INFO")
        out = {}
        for ch in self.settings.channels():
            try:
                self.senders[ch](self.settings, msg)
                out[ch] = "ok"
            except Exception as e:
                out[ch] = f"error: {e}"
        return out

    # --- reglas con cada lectura (hilo del motor) ---
    def on_snapshot(self, snap) -> None:
        try:
            self._evaluate(snap)
        except Exception:
            log.exception("evaluación de notificaciones")

    def _evaluate(self, snap) -> None:
        s = self.settings
        if s.quiet or not s.channels():
            return
        now = snap.ts
        cfg = self.engine.config if self.engine is not None else None
        # hallazgos: fuera de límite, aviso, lectura, comportamiento, tendencia
        active = set()
        for f in snap.findings:
            rule = self._rule_of(f)
            if rule is None:
                continue
            k = (rule, f"{f.rule}:{f.var_id}")
            active.add(k)
            if k in self._seen:
                continue
            if rule == "read_error" and now - f.since < (s.th("read_error") or 0):
                continue
            if s.on(rule) and self.emit(rule, k[1], _short(f.message), f.message,
                                        "ALARMA" if int(f.level) >= 3 else "AVISO"):
                self._seen[k] = now
        for k in [k for k in self._seen if k not in active]:
            self._seen.pop(k)  # se normalizó: un nuevo evento volverá a avisar
        # eventos del ciclo
        for e in snap.events:
            if e.kind in ("screen", "camera") and int(e.level) >= 2:
                self.emit("screen", e.kind, _short(e.message), e.message, "AVISO")
            elif e.kind == "control" and int(e.level) >= 3:
                self.emit("control", e.var_id or "control", _short(e.message), e.message)
            elif e.kind == "recipe_change":
                self.emit("recipe", "recipe", _short(e.message), e.message, "INFO")
        if snap.error and "PANTALLA" not in {f.rule for f in snap.findings}:
            self.emit("screen", "error", _short(snap.error), snap.error, "AVISO")
        if cfg is not None:
            self._stops(snap, cfg)
            self._cpk(snap, cfg)

    @staticmethod
    def _rule_of(f) -> Optional[str]:
        lvl = int(f.level)
        if f.rule == "LECTURA":
            return "read_error"
        if f.rule == "COMPORTAMIENTO":
            return "behavior" if lvl >= 2 else None
        if f.rule == "TENDENCIA":
            return "drift"
        if f.rule in ("TOLERANCIA", "AJUSTE_RECETA", "SELECTOR", "RECETA_HMI"):
            return "alarm" if lvl >= 3 else ("warn" if lvl == 2 else None)
        return None

    def _stops(self, snap, cfg) -> None:
        from .analysis.oee import shift_start
        o = cfg.oee
        st = snap.statuses.get(o.speed_var) if (o.enabled and o.speed_var) else None
        now = snap.ts
        sh = shift_start(now, o.shift_starts)
        if self._shift_key is None:
            self._shift_key = sh
        elif sh != self._shift_key:  # cambió el turno
            prev = self._shift_key
            self._shift_key = sh
            self._stop_acc, self._stop_total_sent = 0.0, False
            self._shift_oee(cfg, prev, sh)
        if st is None or st.reading.value is None or not st.fresh:
            return
        stopped = st.reading.value <= o.stop_threshold
        if stopped:
            if self._stop_since is None:
                self._stop_since, self._stop_sent = now, False
            mins = (now - self._stop_since) / 60
            if not self._stop_sent and mins >= (self.settings.th("stop") or 0):
                self._stop_sent = self.emit("stop", "stop", f"Máquina detenida desde hace {mins:.0f} min",
                                            f"La línea está detenida desde las "
                                            f"{time.strftime('%H:%M', time.localtime(self._stop_since))} "
                                            f"({mins:.0f} min).")
            total = self._stop_acc + (now - self._stop_since)
            if not self._stop_total_sent and total / 60 >= (self.settings.th("stop_total") or 1e9):
                self._stop_total_sent = self.emit(
                    "stop_total", f"total:{sh}", f"Paro acumulado del turno: {total / 60:.0f} min",
                    f"El tiempo de paro del turno ya suma {total / 60:.0f} min (límite "
                    f"{self.settings.th('stop_total'):.0f} min).")
        elif self._stop_since is not None:
            dur = now - self._stop_since
            self._stop_acc += dur
            if self._stop_sent:  # avisa que reanudó (sin espera)
                self.emit("stop", "resume", f"Máquina en marcha de nuevo (paro de {dur / 60:.0f} min)",
                          f"La línea reanudó a las {time.strftime('%H:%M', time.localtime(now))} tras "
                          f"{dur / 60:.0f} min detenida.", "INFO", force=self.settings.on("stop"))
            self._stop_since, self._stop_sent = None, False

    def _cpk(self, snap, cfg) -> None:
        if not self.settings.on("low_cpk"):
            return
        thr = self.settings.th("low_cpk") or 1.0
        for vid, st in snap.statuses.items():
            cpk = st.trend.cpk if st.trend is not None else None
            if cpk is None or not st.var.measured:
                self._cpk_low.pop(vid, None)
                continue
            if cpk < thr:
                t0 = self._cpk_low.setdefault(vid, snap.ts)
                if snap.ts - t0 >= CPK_HOLD_S:
                    label = cfg.var_label(st.var)
                    self.emit("low_cpk", vid, f"Cpk bajo en {label}: {cpk:.2f}",
                              f"El Cpk de «{label}» está en {cpk:.2f} (menor que {thr:g}) desde hace "
                              f"{(snap.ts - t0) / 60:.0f} min.", "AVISO")
            else:
                self._cpk_low.pop(vid, None)

    def _shift_oee(self, cfg, a: float, b: float) -> None:
        if not self.settings.on("low_oee") or self.engine is None or self.engine.historian is None:
            return
        try:
            from .analysis.oee import OeeSample, compute
            o = cfg.oee
            rows = self.engine.historian.oee_samples(a, b)
            samples = [OeeSample(r[0], r[1], r[2], r[3], r[4], None if r[5] is None else bool(r[5]), r[6] or 0)
                       for r in rows]
            res = compute(samples, a, b, o.microstop_s, o.length_factor,
                          planned=self.engine.historian.planned_intervals(a, b))
        except Exception:
            log.exception("OEE del turno para notificar")
            return
        if res.oee is not None and 100 * res.oee < (self.settings.th("low_oee") or 0):
            self.emit("low_oee", f"oee:{a}", f"OEE del turno: {100 * res.oee:.0f} %",
                      f"El turno que empezó a las {time.strftime('%H:%M', time.localtime(a))} cerró con OEE "
                      f"{100 * res.oee:.0f} % (D {100 * (res.availability or 0):.0f} · R "
                      f"{100 * (res.performance or 0):.0f} · C {100 * (res.quality or 0):.0f}).", "AVISO")

    # --- avisos que vienen de la interfaz ---
    def problem_saved(self, rec: dict) -> None:
        unit = rec.get("unit") or ""
        scrap = float(rec.get("scrap") or 0)
        if scrap and scrap >= (self.settings.th("scrap") or 1e18):
            self.emit("scrap", f"cap:{rec.get('id')}", f"Desperdicio alto: {scrap:g} {unit}",
                      f"Captura de {('paro' if rec.get('kind') == 'downtime' else 'calidad')}: "
                      f"{rec.get('category') or ''} › {rec.get('reason') or ''} con {scrap:g} {unit} de desperdicio"
                      + (f" ({rec['operator']})" if rec.get("operator") else "") + ".")
        if self.settings.on("scrap_shift") and self.engine is not None and self.engine.historian is not None:
            from .analysis.oee import shift_start
            now = self.clock()
            a = shift_start(now, self.engine.config.oee.shift_starts)
            total = sum(float(r.get("scrap") or 0) for r in self.engine.historian.problems(a, now))
            if total >= (self.settings.th("scrap_shift") or 1e18):
                self.emit("scrap_shift", f"shift:{a}", f"Desperdicio del turno: {total:g} {unit}",
                          f"El desperdicio capturado en el turno ya suma {total:g} {unit} (límite "
                          f"{self.settings.th('scrap_shift'):g}).")

    def supervisor_login(self, name: str) -> None:
        self.emit("supervisor", f"sup:{name}:{int(self.clock())}", f"Inicio de sesión de supervisor: {name}",
                  f"{name} inició la sesión de supervisor (puede cambiar recetas, variables y la configuración).",
                  "INFO")

    def monitor_stopped(self, closing: bool = False) -> None:
        self.emit("monitor", "closed" if closing else "stopped",
                  "Programa cerrado" if closing else "Monitoreo detenido",
                  "Se cerró el programa de monitoreo: la línea ya no se vigila." if closing else
                  "Se detuvo el monitoreo: la línea ya no se vigila hasta que se reanude.", "AVISO")

    def report_ready(self, path: Path, title: str) -> None:
        self.emit("report", f"rep:{path}", title, f"Se generó el reporte «{title}» (adjunto).", "INFO",
                  attachment=Path(path))


def _short(text: str, n: int = 90) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 1] + "…"
