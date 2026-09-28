"""Orquestación: captura → OCR → reglas → tendencias → historial, en un hilo propio."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .acquisition import Acquirer
from .analysis.rules import Event, Finding, Level, RuleEngine, VarStatus
from .analysis.trends import TrendTracker
from .capture import FrameSource
from .config import AppConfig, Workspace
from .ocr import OcrEngine
from .analysis.behavior import BehaviorMonitor, BehaviorStore
from .analysis.oee import ASSUMED, RUNNING, SLOW, OeeSample, classify
from .capture import load_png
from .navigation import Clicker, TourResult, TourRunner, UnavailableClicker
from .pages import PageDetector
from .profiles import apply_profile, has_profile, save_profile
from .reports import ReportJob, ReportManager, ReportOutput, VarLimits
from .scheduling import TourJob, TourScheduler
from .recipes import Recipe, RecipeStore
from .storage import Historian

log = logging.getLogger(__name__)


@dataclass
class Snapshot:
    ts: float
    cycle_ms: float
    pages: set[str]
    statuses: dict[str, VarStatus]
    findings: list[Finding]
    events: list[Event]
    recipe: Optional[str]
    ocr_engine: str
    error: str = ""
    overall: Level = Level.OK
    read_ok: int = 0
    read_total: int = 0
    tour: Optional[TourResult] = None  # recorrido ejecutado en este ciclo
    # Recorridos anunciados con cuenta regresiva: id -> (hora límite, motivo)
    prompts: dict = field(default_factory=dict)


@dataclass
class EngineState:
    recipe: Optional[str] = None
    auto_recipe: bool = True


class MonitorEngine:
    def __init__(self, workspace: Workspace, config: AppConfig, recipes: RecipeStore,
                 source: FrameSource, ocr: OcrEngine, historian: Optional[Historian] = None,
                 clock: Callable[[], float] = time.time, clicker: Optional[Clicker] = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.workspace = workspace
        self.config = config
        self.recipes = recipes
        self.source = source
        self.ocr = ocr
        self.historian = historian
        self.clock = clock
        self.clicker = clicker or UnavailableClicker()
        self.sleep = sleep
        self.tour_paused = False
        self.state = EngineState()
        self.listeners: list[Callable[[Snapshot], None]] = []
        self.last: Optional[Snapshot] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()  # un ciclo a la vez
        self._data_lock = threading.RLock()  # tendencias/estado, para que la UI no espere al recorrido
        self._pending_events: list[Event] = []
        self.config_version = 0  # cambia al cargar el perfil de una receta (la interfaz se reconstruye)
        self._missing_recipe: Optional[str] = None
        self.behaviors = BehaviorMonitor(BehaviorStore(workspace.behaviors_file))
        self._stored: dict[str, float] = {}
        self._stored_val: dict[str, tuple] = {}
        self._oee_last_ts: Optional[float] = None
        self._last_pages: set[str] = set()
        self._skip_msgs: dict[str, str] = {}
        self.last_tour_result: Optional[TourResult] = None
        self.scheduler = TourScheduler(config, clock)
        self.reports = ReportManager(workspace, clock)
        self._report_events: list[Event] = []
        self._manual_reports: list[str] = []
        self._build()

    def _build(self) -> None:
        g = self.config.general
        old_acq = getattr(self, "acquirer", None)
        old_trends = getattr(self, "trends", None)
        self.pages = PageDetector.from_workspace(self.config, self.workspace)
        self.acquirer = Acquirer(self.config, self.ocr, self.pages, self._selector_images())
        if old_acq is not None:
            # Al cambiar de receta/perfil se conservan las lecturas de las variables que no cambiaron
            # (p. ej. las leídas en el recorrido) y la variante de OCR aprendida.
            for v in self.config.variables:
                ov = old_acq.config.variable(v.id)
                if ov is not None and ov == v and v.id in old_acq.readings:
                    self.acquirer.readings[v.id] = old_acq.readings[v.id]
            if old_acq.ocr is self.ocr:
                self.acquirer.robust = old_acq.robust
        self.rules = RuleEngine(self.config)
        if old_trends is not None and (old_trends.window_s, old_trends.subgroup_s) == \
                (g.trend_window_min * 60, g.spc_subgroup_s):
            self.trends = old_trends
        else:
            self.trends = TrendTracker(g.trend_window_min * 60, g.spc_subgroup_s)
        self.tour_runner = TourRunner(self.config, self.workspace, self.source, self.clicker, self.pages,
                                      clock=self.clock, sleep=self.sleep)
        self.scheduler.reconfigure(self.config)

    def _selector_images(self) -> dict:
        out = {}
        for v in self.config.variables:
            if v.kind == "selector":
                imgs = {st: load_png(self.workspace.selector_state_file(v.id, st)) for st in v.states}
                out[v.id] = {k: img for k, img in imgs.items() if img is not None}
        return out

    def reload_behaviors(self) -> None:
        with self._data_lock:
            self.behaviors.store.load()
            self.behaviors.last.clear()

    def reconfigure(self, config: AppConfig, ocr: Optional[OcrEngine] = None) -> None:
        with self._lock:
            self.config = config
            if ocr is not None:
                self.ocr = ocr
            self._build()

    # --- recetas -----------------------------------------------------------
    @property
    def recipe(self) -> Optional[Recipe]:
        return self.recipes.get(self.state.recipe) if self.state.recipe else None

    def set_recipe(self, name: Optional[str], auto: Optional[bool] = None, load_profile: bool = True) -> None:
        with self._lock:
            if auto is not None:
                self.state.auto_recipe = auto
            if name == self.state.recipe:
                return
            self.state.recipe = name
            self.rules.reset()
            msg = f"Receta activa: {name or 'ninguna'}"
            if name and load_profile and has_profile(self.workspace, name):
                # La receta es un perfil completo: variables, pantallas, recorridos, OEE, reportes…
                try:
                    config = apply_profile(self.workspace, name)
                except Exception:
                    log.exception("No se pudo cargar el perfil de %s", name)
                    config = None
                if config is not None:
                    self.reconfigure(config)
                    self.behaviors.store.load()
                    self.behaviors.last.clear()
                    self.config_version += 1
                    msg += " (configuración completa de la receta cargada)"
            self._pending_events.append(Event(self.clock(), "recipe_change", Level.INFO, "RECETA", "", msg))

    def save_profile(self) -> None:
        """Guarda la configuración activa en el perfil de la receta activa."""
        if self.state.recipe:
            save_profile(self.workspace, self.state.recipe, self.config)

    def _auto_select_recipe(self, readings) -> None:
        var_id = self.config.general.recipe_name_var
        if not var_id:
            return
        rd = readings.get(var_id)
        if rd is None or not rd.ok or not rd.text:
            return
        match = self.recipes.find_by_display_name(rd.text)
        if not self.state.auto_recipe:
            # Modo manual: solo se avisa (una vez) que el HMI muestra otra receta.
            if match is not None and match.name != self.state.recipe and rd.text != self._missing_recipe:
                self._missing_recipe = rd.text
                self._pending_events.append(Event(
                    self.clock(), "recipe_hint", Level.INFO, "RECETA_HMI", var_id,
                    f"El HMI muestra la receta «{rd.text}»; cárgala manualmente (modo manual)"))
            return
        if match is None:
            if rd.text != self._missing_recipe:
                self._missing_recipe = rd.text
                self._pending_events.append(Event(
                    self.clock(), "recipe_missing", Level.WARN, "RECETA_HMI", var_id,
                    f"La receta «{rd.text}» que muestra el HMI no existe en el programa; "
                    f"se mantiene «{self.state.recipe or 'ninguna'}»"))
            return
        self._missing_recipe = None
        if match.name != self.state.recipe:
            self.set_recipe(match.name)

    def series(self, var_id: str):
        with self._data_lock:
            return self.trends.series(var_id)

    def grab_frame(self):
        return self.source.grab()

    def run_tour_now(self, tour_id: Optional[str] = None) -> None:
        """Encola el recorrido (por defecto el de lectura) para el siguiente ciclo."""
        with self._data_lock:
            self.scheduler.run_now(tour_id)

    def confirm_tour(self, tour_id: str) -> None:
        with self._data_lock:
            self.scheduler.confirm(tour_id)

    def snooze_tour(self, tour_id: str) -> None:
        with self._data_lock:
            self.scheduler.snooze(tour_id)

    def pending_prompts(self) -> dict:
        with self._data_lock:
            return self.scheduler.pending_prompts()

    def _run_job(self, job: TourJob, pages: set[str]) -> Optional[TourResult]:
        tour = self.config.get_tour(job.tour_id)
        if tour is None or not tour.steps:
            return None

        def on_frame(frame):
            seen, _ = self.acquirer.read(frame, self.clock())
            pages.update(seen)

        res = self.tour_runner.run(tour, on_frame, stop=self._stop.is_set, skip_idle=job.consent)
        res.trigger = job.reason
        self.last_tour_result = res
        with self._data_lock:
            if res.skipped:
                # Se reintenta en los siguientes ciclos (disparos por flanco incluidos) durante un tiempo.
                if self.clock() - job.created < JOB_RETRY_S:
                    self.scheduler.requeue(job)
            else:
                self.scheduler.mark_run(tour.id, self.clock())
        self._tour_events(tour, res)
        return res

    # --- ciclo ---------------------------------------------------------------
    def step(self) -> Snapshot:
        with self._lock:
            t0 = time.perf_counter()
            now = self.clock()
            error = ""
            tour_result: Optional[TourResult] = None
            pages: set[str] = set()
            readings = self.acquirer.readings
            try:
                job = None
                if not self.tour_paused:
                    with self._data_lock:
                        for msg in self.scheduler.update(now, self._last_pages, readings):
                            self._pending_events.append(Event(now, "tour_prompt", Level.INFO, "RECORRIDO", "", msg))
                        job = self.scheduler.pop()
                if job is not None:
                    tour_result = self._run_job(job, pages)
                if tour_result is not None and not tour_result.skipped:
                    readings = self.acquirer.readings
                    now = self.clock()
                else:
                    frame = self.source.grab()
                    pages, readings = self.acquirer.read(frame, now)
                self._last_pages = set(pages)
            except Exception as exc:
                log.exception("Fallo de captura")
                error = f"Fallo de captura: {exc}"
            self._auto_select_recipe(readings)
            with self._data_lock:
                extra = self.behaviors.evaluate(
                    now, self.rules.fresh_values(now, readings), self.state.recipe,
                    lambda vid: self.config.var_label(self.config.variable(vid)) if self.config.variable(vid) else vid)
                statuses, events = self.rules.evaluate(now, readings, self.recipe, self.trends, extra)
            report_events = []
            while self._report_events:
                report_events.append(self._report_events.pop(0))
            events = self._pending_events + report_events + events
            self._pending_events = []
            findings = self.rules.active_findings()
            overall = max((f.level for f in findings), default=Level.OK)
            visible = [r for r in readings.values() if r.visible]
            snap = Snapshot(
                ts=now, cycle_ms=(time.perf_counter() - t0) * 1000, pages=pages, statuses=statuses,
                findings=findings, events=events, recipe=self.state.recipe, ocr_engine=self.ocr.name,
                error=error, overall=overall, read_ok=sum(r.ok for r in visible), read_total=len(visible),
                tour=tour_result, prompts=self.pending_prompts())
            self._record_oee(snap)
            self._store(snap)
            self.last = snap
            self._check_reports(snap, readings)
        for cb in list(self.listeners):
            try:
                cb(snap)
            except Exception:
                log.exception("Error en listener")
        return snap

    # --- reportes ------------------------------------------------------------------------
    def generate_report(self, report_id: str) -> None:
        """Genera el reporte en el siguiente ciclo (o de inmediato si el monitoreo está detenido)."""
        self._manual_reports.append(report_id)
        if not self.running and self.last is not None:
            with self._lock:
                self._check_reports(self.last, self.acquirer.readings)

    def reset_analysis(self) -> None:
        """Reinicia tendencias, estadística y comportamiento (la ventana empieza de nuevo)."""
        with self._data_lock:
            self.trends.clear()
            self.behaviors.history.clear()
            self.behaviors.last.clear()

    def _check_reports(self, snap: Snapshot, readings) -> None:
        cfg = self.config
        if not cfg.reports:
            return
        fired = self.reports.check(cfg, readings, snap.events)
        manual = [r for rid in self._manual_reports if (r := next((x for x in cfg.reports if x.id == rid), None))]
        self._manual_reports = []
        fired += [(r, "manual") for r in manual if all(r is not f[0] for f in fired)]
        if not fired:
            return
        limits = self._report_limits(snap)
        reset = False
        for rep, reason in fired:
            models = [m.model_copy(deep=True) for mid in rep.behavior_models
                      if (m := self.behaviors.store.get(mid)) is not None and m.trained]
            name_text = None
            if rep.name_var:
                rd = readings.get(rep.name_var)
                if rd is not None:
                    name_text = rd.text if rd.text else (f"{rd.value:g}" if rd.value is not None else None)
            job = self.reports.make_job(rep, cfg, reason, self.state.recipe, limits, models, name_text)
            if self.historian is not None:
                self.reports.submit(job, self.historian, self._report_done)
            reset |= rep.reset_analysis
        if reset:
            self.reset_analysis()

    def _report_limits(self, snap: Snapshot) -> dict[str, VarLimits]:
        out = {}
        for vid, st in snap.statuses.items():
            lim = VarLimits(target=st.reference, expected=st.expected)
            if st.reference is not None and st.alarm_band is not None:
                lim.lsl, lim.usl = st.reference - st.alarm_band, st.reference + st.alarm_band
            out[vid] = lim
        return out

    def _report_done(self, job: ReportJob, out: ReportOutput) -> None:
        # Hilo de reportes: el evento se entrega en el siguiente ciclo.
        if out.error:
            ev = Event(self.clock(), "report", Level.WARN, "REPORTE", "",
                       f"Reporte «{job.report.name}» falló: {out.error}")
        else:
            verdict = {True: "CONFORME", False: "NO CONFORME", None: "sin evaluación"}[out.ok]
            ev = Event(self.clock(), "report", Level.INFO, "REPORTE", "",
                       f"Reporte «{job.report.name}» ({verdict}): {out.pdf}")
        self._report_events.append(ev)

    def _record_oee(self, snap: Snapshot) -> None:
        o = self.config.oee
        if not (o.enabled and o.speed_var and self.historian):
            return
        last = self._oee_last_ts
        sample = oee_sample(self.config, snap, self.recipe, last)
        self._oee_last_ts = snap.ts
        if sample is None:
            return
        gap = snap.ts - last - sample.dt if last is not None else 0.0
        if (gap > 0 and o.gap_productive and gap <= o.gap_productive_max_s
                and sample.state in (RUNNING, SLOW) and sample.good is not False and sample.overall < Level.ALARM):
            # Al volver los datos la línea marcha y todo está en parámetros: el hueco se toma como productivo.
            try:
                self.historian.write_oee((snap.ts - sample.dt, gap, ASSUMED, sample.speed, sample.nominal, 1, 0))
            except Exception:
                log.exception("No se pudo guardar el hueco OEE")
        try:
            self.historian.write_oee((sample.ts, sample.dt, sample.state, sample.speed, sample.nominal,
                                      None if sample.good is None else int(sample.good), sample.overall))
        except Exception:
            log.exception("No se pudo guardar la muestra OEE")

    def _tour_events(self, tour, res: TourResult) -> None:
        name = f"Recorrido «{tour.name}»"
        if res.skipped:
            # Solo se registra cuando cambia el motivo, para no llenar el registro.
            if res.message != self._skip_msgs.get(tour.id):
                self._pending_events.append(Event(self.clock(), "tour", Level.INFO, "RECORRIDO", tour.id,
                                                  f"{name} {res.message}"))
            self._skip_msgs[tour.id] = res.message
            return
        self._skip_msgs.pop(tour.id, None)
        if res.ok:
            # Evento de recorrido ejecutado: puede disparar un reporte.
            self._pending_events.append(Event(self.clock(), "tour_done", Level.INFO, "RECORRIDO", tour.id,
                                              f"{name}: {res.message} ({res.trigger})"))
        else:
            self._pending_events.append(Event(self.clock(), "tour", Level.WARN, "RECORRIDO", tour.id,
                                              f"{name} {res.message}"))

    def _store(self, snap: Snapshot) -> None:
        if not self.historian:
            return
        rows = []
        for vid, st in snap.statuses.items():
            rd = st.reading
            # Con recorrido, cada variable se lee en un instante distinto: se guarda cada lectura nueva.
            if rd.ts is None or rd.ts <= self._stored.get(vid, 0.0):
                continue
            text = rd.text if st.var.kind in ("text", "selector") else None
            last = self._stored_val.get(vid)
            # Banda muerta: solo se guarda si cambió o cada HEARTBEAT_S (el historial no crece sin medida).
            if last is not None and last[1] == (rd.value, text) and rd.ts - last[0] < HEARTBEAT_S:
                continue
            self._stored[vid] = rd.ts
            self._stored_val[vid] = (rd.ts, (rd.value, text))
            rows.append((rd.ts, vid, rd.value, text))
        try:
            self.historian.write_samples(rows)
            self.historian.write_events(
                (e.ts, e.kind, int(e.level), e.rule, e.var_id, e.message, snap.recipe) for e in snap.events)
        except Exception:
            log.exception("No se pudo escribir el historial")

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="monitor", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
        self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                self.step()
            except Exception:
                log.exception("Error en ciclo de monitoreo")
            wait = self.config.general.sample_interval_s - (time.monotonic() - t0)
            self._stop.wait(max(0.05, wait))


# Calidad: mediciones reales fuera de tolerancia y selectores en estado incorrecto
# (un ajuste distinto de receta se reporta aparte; afecta la calidad cuando saca las mediciones).
HEARTBEAT_S = 20.0
JOB_RETRY_S = 600.0  # un recorrido pospuesto (operador activo, otra pantalla) se reintenta hasta 10 min  # un valor sin cambios se vuelve a guardar como máximo cada 20 s

QUALITY_RULES = {"TOLERANCIA", "SELECTOR"}


def oee_sample(config: AppConfig, snap: Snapshot, recipe: Optional[Recipe],
               last_ts: Optional[float]) -> Optional[OeeSample]:
    """Clasifica el ciclo actual para el OEE (estado, velocidad, nominal y conformidad)."""
    o = config.oee
    g = config.general
    # Muestras separadas por más que esto (app cerrada, pausa) no cuentan como tiempo observado.
    max_dt = max(3 * g.sample_interval_s, 10.0)
    if last_ts is None:
        dt = g.sample_interval_s
    else:
        dt = snap.ts - last_ts
        if dt <= 0:
            return None
        dt = min(dt, max_dt)
    st = snap.statuses.get(o.speed_var)
    speed = st.reading.value if st is not None and st.fresh else None
    nominal = None
    var = config.variable(o.speed_var)
    if o.nominal_source == "fixed":
        nominal = o.nominal_value
    elif o.nominal_source == "setpoint" and var and var.setpoint_var:
        sp = snap.statuses.get(var.setpoint_var)
        if sp is not None and sp.fresh:
            nominal = sp.reading.value
    if nominal is None and recipe is not None and var is not None:
        for vid in (var.id, var.setpoint_var):
            lim = recipe.limits.get(vid) if vid else None
            if lim is not None and lim.nominal is not None:
                nominal = lim.nominal
                break
    state = classify(speed, nominal, o.stop_threshold, o.slow_pct)
    min_level = Level.WARN if o.strict_quality else Level.ALARM
    good: Optional[bool] = None
    if o.quality_mode in ("spec", "both"):
        good = not any(f.rule in QUALITY_RULES and f.level >= min_level and f.var_id != o.speed_var
                       for f in snap.findings)
    if o.quality_mode in ("selector", "both") and o.quality_selector:
        sel = snap.statuses.get(o.quality_selector)
        ok = bool(sel and sel.fresh and sel.reading.text == o.quality_good_state)
        good = ok if good is None else (good and ok)
    return OeeSample(snap.ts, dt, state, speed, nominal, good, int(snap.overall))
