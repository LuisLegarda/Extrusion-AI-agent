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
from .camera import CameraManager
from .capture import FrameSource
from .config import AppConfig, Workspace
from .ocr import OcrEngine
from .analysis.behavior import BehaviorMonitor, BehaviorStore
from .analysis.kpis import KPI_EVERY_S, all_kpis, kpi_var
from .analysis.oee import ASSUMED, RUNNING, SLOW, OeeSample, classify
from .capture import ScreenUnavailable, load_png
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
        self._screen_problem: Optional[str] = None
        self._good_size: Optional[tuple[int, int]] = None
        self._skip_msgs: dict[str, str] = {}
        self.last_tour_result: Optional[TourResult] = None
        # Indicadores generales (OEE, Cpk, conformidad…) calculados cada KPI_EVERY_S y guardados en el historial
        self.kpis: dict[str, Optional[float]] = {}
        self.kpis_ts: Optional[float] = None
        self.kpi_oee = None  # resultado de OEE del turno del último cálculo
        self.scheduler = TourScheduler(config, clock)
        self.reports = ReportManager(workspace, clock)
        self._report_events: list[Event] = []
        self._manual_reports: list[str] = []
        self.cameras = CameraManager(clock=clock)
        self._cam_problems: dict[str, Optional[str]] = {}
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
        self.cameras.configure(self.config.cameras, camera_probes(self.config))

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
            prev = self.state.recipe
            self.state.recipe = name
            self.rules.reset()
            msg = f"Receta activa: {name or 'ninguna'}"
            pending = self.workspace.unassigned_config_flag
            if name and prev is None and pending.exists():
                # La configuración se editó sin receta activa: se asigna a esta receta en vez de
                # reemplazarla por el perfil anterior (así no se pierden recorridos ni ajustes).
                try:
                    save_profile(self.workspace, name, self.config)
                    pending.unlink()
                    msg += " (se le asignó la configuración actual)"
                except OSError:
                    log.exception("No se pudo asignar la configuración a %s", name)
            elif name and load_profile and has_profile(self.workspace, name):
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

    def save_profile(self) -> Optional[str]:
        """Guarda la configuración activa en el perfil de la receta activa. Devuelve el error, si lo hubo."""
        if self.state.recipe:
            try:
                save_profile(self.workspace, self.state.recipe, self.config)
            except OSError as exc:
                log.exception("No se pudo guardar el perfil")
                msg = f"No se pudo guardar la configuración en la receta «{self.state.recipe}»: {exc}"
                self._pending_events.append(Event(self.clock(), "profile", Level.WARN, "RECETA", "", msg))
                return msg
        else:
            # Sin receta activa: la próxima receta que se active tomará esta configuración.
            try:
                self.workspace.unassigned_config_flag.touch()
            except OSError:
                log.exception("No se pudo marcar la configuración")
        return None

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

    def _check_screen(self, frame):
        """La captura debe tener la resolución con la que se configuraron las regiones."""
        # Resolución de referencia: la del configurador o, en configuraciones anteriores, la última
        # con la que se reconocieron las pantallas del HMI.
        size = self.config.general.screen_size or self._good_size
        h, w = frame.shape[:2]
        if size and (w, h) != (size[0], size[1]):
            raise ScreenUnavailable(
                f"la resolución actual es {w}×{h} y las regiones se configuraron en {size[0]}×{size[1]}; "
                "conéctate al HMI con esa resolución (en Escritorio remoto: Mostrar → Configuración de pantalla)")
        return frame

    def _screen_state(self, problem: Optional[str]) -> None:
        """Registra una sola vez cuándo se pierde y cuándo se recupera la pantalla."""
        if problem == self._screen_problem:
            return
        now = self.clock()
        if problem is not None:
            log.warning("Pantalla no disponible: %s", problem)
            self._pending_events.append(Event(now, "screen", Level.WARN, "PANTALLA", "",
                                              f"Pantalla no disponible: {problem}. Se conservan los últimos datos."))
        elif self._screen_problem is not None:
            self._pending_events.append(Event(now, "screen", Level.INFO, "PANTALLA", "",
                                              "Pantalla disponible de nuevo: se reanuda la lectura"))
        self._screen_problem = problem

    def _camera_events(self, cams) -> None:
        """Registra una sola vez cuándo una cámara se queda sin imagen y cuándo vuelve."""
        for cid, view in (cams or {}).items():
            problem = None if view.ok else (view.error or "sin imagen")
            if problem == "conectando…":
                continue
            old = self._cam_problems.get(cid)
            if (problem is None) == (old is None):
                continue
            cam = self.config.camera(cid)
            name = cam.name if cam else cid
            now = self.clock()
            if problem is not None:
                log.warning("Cámara %s sin imagen: %s", cid, problem)
                self._pending_events.append(Event(now, "camera", Level.WARN, "CÁMARA", "",
                                                  f"Cámara «{name}» sin imagen: {problem}. "
                                                  "Se conservan los últimos datos."))
            elif cid in self._cam_problems:
                self._pending_events.append(Event(now, "camera", Level.INFO, "CÁMARA", "",
                                                  f"Cámara «{name}» con imagen de nuevo: se reanuda la lectura"))
            self._cam_problems[cid] = problem

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
                # Con la pantalla no disponible (sesión bloqueada o remota desconectada) no hay recorridos.
                if not self.tour_paused and self._screen_problem is None:
                    with self._data_lock:
                        for msg in self.scheduler.update(now, self._last_pages, readings):
                            self._pending_events.append(Event(now, "tour_prompt", Level.INFO, "RECORRIDO", "", msg))
                        job = self.scheduler.pop()
                if job is not None:
                    tour_result = self._run_job(job, pages)
                if tour_result is not None and not tour_result.skipped:
                    now = self.clock()
                    if self.config.cameras:  # el recorrido solo cambia la pantalla: las cámaras se leen igual
                        cams = self.cameras.views()
                        self.acquirer.read(None, now, cams)
                        self._camera_events(cams)
                    readings = self.acquirer.readings
                else:
                    cams = self.cameras.views() if self.config.cameras else None
                    frame, screen_exc = None, None
                    if self.config.needs_screen:  # con solo cámaras no se captura la pantalla
                        try:
                            frame = self._check_screen(self.source.grab())
                        except ScreenUnavailable as exc:
                            screen_exc = exc  # las cámaras se siguen leyendo
                    pages, readings = self.acquirer.read(frame, now, cams)
                    self._camera_events(cams)
                    if frame is not None and pages and \
                            any(p.anchor is not None for p in self.config.pages if p.id in pages):
                        self._good_size = (frame.shape[1], frame.shape[0])
                    if screen_exc is not None:
                        raise screen_exc
                self._last_pages = set(pages)
                self._screen_state(None)
            except ScreenUnavailable as exc:
                error = f"Pantalla no disponible: {exc}"
                self._screen_state(str(exc))
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
            if self._screen_problem is None:
                # Sin pantalla no hay observación: queda como hueco (productivo si al volver todo está bien).
                self._record_oee(snap)
            self._store(snap)
            self._record_kpis(snap)
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
            # Especificación = límites de alarma (± o mín/máx de la receta).
            out[vid] = VarLimits(lsl=st.bounds.al, usl=st.bounds.ah, target=st.reference, expected=st.expected)
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

    def _record_kpis(self, snap: Snapshot) -> None:
        if self.kpis_ts is not None and snap.ts - self.kpis_ts < KPI_EVERY_S:
            return
        try:
            kpis, res = all_kpis(self, snap, snap.ts)
        except Exception:
            log.exception("No se pudieron calcular los indicadores")
            return
        self.kpis, self.kpi_oee, self.kpis_ts = kpis, res, snap.ts
        if self.historian is not None:
            try:
                self.historian.write_samples([(snap.ts, kpi_var(k), v, None) for k, v in kpis.items()
                                              if v is not None])
            except Exception:
                log.exception("No se pudieron guardar los indicadores")

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
        self.cameras.start()
        self._thread = threading.Thread(target=self._run, name="monitor", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
        self._thread = None
        self.cameras.stop()

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


def camera_probes(config: AppConfig) -> dict:
    """Luces por color de cada cámara: se miden en cada cuadro para detectar parpadeos."""
    out: dict = {}
    for v in config.variables:
        if v.on_camera and v.kind == "selector" and v.state_method == "color":
            out.setdefault(v.source, []).append((v.id, v.region))
    return out


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
            if lim is not None and lim.center() is not None:
                nominal = lim.center()
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
