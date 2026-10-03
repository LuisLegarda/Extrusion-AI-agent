"""Exportación al dashboard global: escribe el estado de la línea en la carpeta compartida.

Corre en su propio hilo: una carpeta de red lenta o caída nunca detiene la lectura del HMI. Si la carpeta
no está disponible, los eventos y tendencias se guardan en memoria (con límite) y se escriben al volver.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from . import __version__
from .analysis.oee import STATE_LABELS, OeeSample, compute, shift_start
from .analysis.rules import Level
from .config import Workspace
from .fleet import (EVENTS_DIR, SCHEMA_VERSION, STATUS_FILE, TREND_DIR, StationSettings, append_lines, day_name,
                    dumps, line_slug, write_atomic)

log = logging.getLogger(__name__)

LEVELS = {Level.OK: "OK", Level.INFO: "INFO", Level.WARN: "WARN", Level.ALARM: "ALARM"}
MAX_PENDING = 20000  # renglones en memoria mientras la carpeta no está disponible
OEE_EVERY_S = 30.0


def load_station(ws: Workspace) -> StationSettings:
    try:
        return StationSettings.model_validate_json((ws.home / "station.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return StationSettings()


def save_station(ws: Workspace, st: StationSettings) -> None:
    path = ws.home / "station.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(st.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)


def _num(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


class FleetExporter:
    def __init__(self, engine, workspace: Workspace, settings: Optional[StationSettings] = None):
        self.engine = engine
        self.workspace = workspace
        self.settings = settings or load_station(workspace)
        self._lock = threading.Lock()
        self._snap = None
        self._events: list[str] = []
        self._acc: dict[str, list[float]] = {}  # valores del minuto en curso por variable
        self._acc_start = time.time()
        self._trend: list[tuple[float, str]] = []  # (ts, renglón) pendientes de escribir
        self._oee = None
        self._oee_at = 0.0
        self._last_purge = 0.0
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_ok: Optional[float] = None
        self.last_error = ""
        engine.listeners.append(self.offer)

    # --- configuración ---------------------------------------------------------------------
    @property
    def line_id(self) -> str:
        s = self.settings
        return line_slug(s.line_id or s.line_name or self.engine.config.machine_name)

    @property
    def line_dir(self) -> Optional[Path]:
        s = self.settings
        if not (s.enabled and s.export_dir):
            return None
        return Path(s.export_dir) / self.line_id

    def reconfigure(self, settings: StationSettings) -> None:
        with self._lock:
            self.settings = settings
            self.last_error = ""
        save_station(self.workspace, settings)
        self._wake.set()

    # --- entrada (hilo del monitoreo: solo copia datos, sin E/S) ------------------------------
    def offer(self, snap) -> None:
        if not self.settings.enabled:
            return
        rows = []
        for e in snap.events:
            rows.append(dumps({"ts": round(e.ts, 3), "kind": e.kind, "level": LEVELS.get(e.level, str(e.level)),
                               "rule": e.rule, "var": e.var_id, "msg": e.message, "recipe": snap.recipe}))
        with self._lock:
            self._snap = snap
            self._events = (self._events + rows)[-MAX_PENDING:]
            for vid, st in snap.statuses.items():
                v = _num(st.reading.value)
                if v is not None and st.fresh and st.var.numeric:
                    self._acc.setdefault(vid, []).append(v)

    # --- hilo ---------------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="fleet-export", daemon=True)
        self._thread.start()

    def stop(self, closed: bool = True) -> None:
        """Detiene el hilo; con `closed` deja escrito que el programa se cerró (no es una falla de red)."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(5.0)
        self._thread = None
        if closed and self.line_dir is not None:
            try:
                self.write_once(closed=True)
            except OSError:
                pass

    def _run(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            if self.line_dir is not None:
                try:
                    self.write_once()
                except Exception as exc:  # carpeta no disponible: se reintenta en el siguiente ciclo
                    if str(exc) != self.last_error:
                        log.warning("Exportación al dashboard global: %s", exc)
                    self.last_error = str(exc)
            self._wake.wait(max(0.2, self.settings.interval_s - (time.monotonic() - t0)))
            self._wake.clear()

    def write_once(self, closed: bool = False) -> None:
        d = self.line_dir
        if d is None:
            return
        now = time.time()
        self._roll_trend(now)
        with self._lock:
            snap = self._snap
            events, self._events = self._events, []
            trend, self._trend = self._trend, []
        try:
            (d / EVENTS_DIR).mkdir(parents=True, exist_ok=True)
            (d / TREND_DIR).mkdir(exist_ok=True)
            append_lines(d / EVENTS_DIR / day_name(now), events)
            by_day: dict[str, list[str]] = {}
            for ts, row in trend:
                by_day.setdefault(day_name(ts), []).append(row)
            for name, rows in by_day.items():
                append_lines(d / TREND_DIR / name, rows)
            events, trend = [], []
            write_atomic(d / STATUS_FILE, json.dumps(self.payload(snap, now, closed), ensure_ascii=False,
                                                     separators=(",", ":")).encode("utf-8"))
        finally:
            if events or trend:  # no se pudo escribir: vuelven a la cola
                with self._lock:
                    self._events = (events + self._events)[-MAX_PENDING:]
                    self._trend = (trend + self._trend)[-MAX_PENDING:]
        self.last_ok = now
        self.last_error = ""
        if now - self._last_purge > 6 * 3600:
            self._last_purge = now
            self._purge(d, now)

    def _roll_trend(self, now: float) -> None:
        with self._lock:
            if now - self._acc_start < self.settings.trend_interval_s:
                return
            acc, self._acc = self._acc, {}
            start, self._acc_start = self._acc_start, now
            kpis = {k: round(v, 4) for k, v in (self.engine.kpis or {}).items() if v is not None}
            if acc or kpis:
                v = {vid: [round(sum(xs) / len(xs), 6), min(xs), max(xs), xs[-1]] for vid, xs in acc.items()}
                self._trend.append((now, dumps({"ts": round(now, 1), "from": round(start, 1), "v": v,
                                                "k": kpis})))
                self._trend = self._trend[-MAX_PENDING:]

    def _purge(self, d: Path, now: float) -> None:
        keep = self.settings.retention_days * 86400
        for sub in (EVENTS_DIR, TREND_DIR):
            for f in (d / sub).glob("*.jsonl"):
                try:
                    if now - f.stat().st_mtime > keep:
                        f.unlink()
                except OSError:
                    pass

    # --- contenido de status.json ------------------------------------------------------------
    def _oee_now(self, now: float):
        eng = self.engine
        o = eng.config.oee
        if not (o.enabled and o.speed_var and eng.historian):
            return None
        if self._oee is None or now - self._oee_at >= OEE_EVERY_S:
            a = shift_start(now, o.shift_starts)
            rows = eng.historian.oee_samples(a, now)
            samples = [OeeSample(r[0], r[1], r[2], r[3], r[4], None if r[5] is None else bool(r[5]), r[6] or 0)
                       for r in rows]
            self._oee = compute(samples, a, now, o.microstop_s, o.length_factor,
                                planned=eng.historian.planned_intervals(a, now))
            self._oee_at = now
        return self._oee

    def payload(self, snap, now: float, closed: bool = False) -> dict:
        eng = self.engine
        cfg = eng.config
        s = self.settings
        out = {
            "schema": SCHEMA_VERSION, "line_id": self.line_id, "line_name": s.line_name or cfg.machine_name,
            "machine_name": cfg.machine_name, "area": s.area, "app_version": __version__, "ts": round(now, 3),
            "interval_s": s.interval_s, "closed": closed, "monitoring": bool(eng.running) and not closed,
            "recipe": eng.state.recipe, "auto_recipe": eng.state.auto_recipe,
        }
        if snap is not None:
            counts = {lvl: sum(1 for f in snap.findings if f.level == lvl) for lvl in (Level.WARN, Level.ALARM)}
            out.update({
                "snapshot_ts": round(snap.ts, 3), "overall": LEVELS.get(snap.overall, "OK"), "error": snap.error,
                "pages": sorted(snap.pages), "read": {"ok": snap.read_ok, "total": snap.read_total},
                "n_alarms": counts[Level.ALARM], "n_warnings": counts[Level.WARN],
                "alarms": [{"since": round(f.since, 1), "level": LEVELS.get(f.level, ""), "rule": f.rule,
                            "var": f.var_id, "msg": f.message}
                           for f in sorted(snap.findings, key=lambda f: (-int(f.level), f.since))
                           if f.level >= Level.WARN][:50],
                "variables": [self._var(st, cfg) for st in snap.statuses.values()],
            })
        try:
            res = self._oee_now(now)
        except Exception:
            log.exception("OEE para el dashboard global")
            res = None
        if res is not None:
            cur = res.intervals[-1] if res.intervals else None
            out["machine"] = {"state": cur.state if cur else None,
                              "label": STATE_LABELS.get(cur.state, "") if cur else "",
                              "since": round(cur.start, 1) if cur else None}
            out["oee"] = {k: getattr(res, k) for k in (
                "oee", "availability", "performance", "quality", "length_total", "length_good", "n_stops",
                "n_microstops", "stop_s", "run_s", "avg_speed", "avg_nominal", "mtbf_s", "mttr_s")}
            out["oee"]["shift_start"] = res.start
            out["oee"]["unit"] = cfg.oee.length_unit
        kpis = {k: v for k, v in (eng.kpis or {}).items() if v is not None}
        if res is not None:  # el OEE del momento (no el de hace hasta 30 s)
            for k in ("oee", "availability", "performance", "quality"):
                v = getattr(res, k)
                if v is not None:
                    kpis[k] = 100.0 * v
        out["kpis"] = kpis
        return out

    @staticmethod
    def _var(st, cfg) -> dict:
        v = st.var
        rd = st.reading
        b = st.bounds
        d = {"id": v.id, "name": v.name, "label": cfg.var_label(v), "group": v.group, "unit": v.unit,
             "kind": v.kind, "value": _num(rd.value), "text": rd.text, "fresh": st.fresh,
             "level": LEVELS.get(st.level) if st.level is not None else None,
             "ref": _num(st.reference), "ref_src": st.ref_source or None,
             "limits": [_num(b.wl), _num(b.wh), _num(b.al), _num(b.ah)], "expected": st.expected,
             "decimals": v.decimals if v.decimals is not None else rd.decimals}
        if st.trend is not None:
            d["cpk"] = _num(st.trend.cpk)
            d["slope_min"] = _num(st.trend.slope_per_min)
        return d
