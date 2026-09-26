"""Orquestación: captura → OCR → reglas → tendencias → historial, en un hilo propio."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .acquisition import Acquirer
from .analysis.rules import Event, Finding, Level, RuleEngine, VarStatus
from .analysis.trends import TrendTracker
from .capture import FrameSource
from .config import AppConfig, Workspace
from .ocr import OcrEngine
from .analysis.behavior import BehaviorMonitor, BehaviorStore
from .capture import load_png
from .navigation import Clicker, TourResult, TourRunner, UnavailableClicker
from .pages import PageDetector
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
        self._last_skip = ""
        self.state = EngineState()
        self.listeners: list[Callable[[Snapshot], None]] = []
        self.last: Optional[Snapshot] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()  # un ciclo a la vez
        self._data_lock = threading.RLock()  # tendencias/estado, para que la UI no espere al recorrido
        self._pending_events: list[Event] = []
        self.behaviors = BehaviorMonitor(BehaviorStore(workspace.behaviors_file))
        self._stored: dict[str, float] = {}
        self._build()

    def _build(self) -> None:
        g = self.config.general
        self.pages = PageDetector.from_workspace(self.config, self.workspace)
        self.acquirer = Acquirer(self.config, self.ocr, self.pages, self._selector_images())
        self.rules = RuleEngine(self.config)
        self.trends = TrendTracker(g.trend_window_min * 60, g.spc_subgroup_s)
        last = getattr(self, "tour", None)
        self.tour = TourRunner(self.config, self.workspace, self.source, self.clicker, self.pages,
                               clock=self.clock, sleep=self.sleep)
        if last is not None:
            self.tour.last_run, self.tour.last_result = last.last_run, last.last_result

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

    def set_recipe(self, name: Optional[str], auto: Optional[bool] = None) -> None:
        with self._lock:
            if auto is not None:
                self.state.auto_recipe = auto
            if name != self.state.recipe:
                self.state.recipe = name
                self.rules.reset()
                self._pending_events.append(Event(self.clock(), "recipe_change", Level.INFO, "RECETA", "",
                                                  f"Receta activa: {name or 'ninguna'}"))

    def _auto_select_recipe(self, readings) -> None:
        var_id = self.config.general.recipe_name_var
        if not (self.state.auto_recipe and var_id):
            return
        rd = readings.get(var_id)
        if rd is None or not rd.ok or not rd.text:
            return
        match = self.recipes.find_by_display_name(rd.text)
        if match and match.name != self.state.recipe:
            self.set_recipe(match.name)

    def series(self, var_id: str):
        with self._data_lock:
            return self.trends.series(var_id)

    def grab_frame(self):
        return self.source.grab()

    def run_tour_now(self) -> None:
        """Fuerza el recorrido en el siguiente ciclo."""
        self.tour.last_run = None

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
                if not self.tour_paused and self.tour.due(now):
                    def on_frame(frame):
                        seen, _ = self.acquirer.read(frame, self.clock())
                        pages.update(seen)

                    tour_result = self.tour.run(on_frame, stop=self._stop.is_set)
                    self._tour_events(tour_result)
                    if tour_result.skipped:
                        tour_result_frame = self.source.grab()
                        pages, readings = self.acquirer.read(tour_result_frame, now)
                    now = self.clock()
                else:
                    frame = self.source.grab()
                    pages, readings = self.acquirer.read(frame, now)
            except Exception as exc:
                log.exception("Fallo de captura")
                error = f"Fallo de captura: {exc}"
            self._auto_select_recipe(readings)
            with self._data_lock:
                extra = self.behaviors.evaluate(
                    now, self.rules.fresh_values(now, readings), self.state.recipe,
                    lambda vid: self.config.var_label(self.config.variable(vid)) if self.config.variable(vid) else vid)
                statuses, events = self.rules.evaluate(now, readings, self.recipe, self.trends, extra)
            events = self._pending_events + events
            self._pending_events = []
            findings = self.rules.active_findings()
            overall = max((f.level for f in findings), default=Level.OK)
            visible = [r for r in readings.values() if r.visible]
            snap = Snapshot(
                ts=now, cycle_ms=(time.perf_counter() - t0) * 1000, pages=pages, statuses=statuses,
                findings=findings, events=events, recipe=self.state.recipe, ocr_engine=self.ocr.name,
                error=error, overall=overall, read_ok=sum(r.ok for r in visible), read_total=len(visible),
                tour=tour_result)
            self._store(snap)
            self.last = snap
        for cb in list(self.listeners):
            try:
                cb(snap)
            except Exception:
                log.exception("Error en listener")
        return snap

    def _tour_events(self, res: TourResult) -> None:
        if res.skipped:
            # Solo se registra cuando cambia el motivo, para no llenar el registro.
            if res.message != self._last_skip:
                self._pending_events.append(Event(self.clock(), "tour", Level.INFO, "RECORRIDO", "",
                                                  f"Recorrido {res.message}"))
            self._last_skip = res.message
            return
        self._last_skip = ""
        if not res.ok:
            self._pending_events.append(Event(self.clock(), "tour", Level.WARN, "RECORRIDO", "",
                                              f"Recorrido {res.message}"))

    def _store(self, snap: Snapshot) -> None:
        if not self.historian:
            return
        rows = []
        for vid, st in snap.statuses.items():
            rd = st.reading
            # Con recorrido, cada variable se lee en un instante distinto: se guarda cada lectura nueva.
            if rd.ts is not None and rd.ts > self._stored.get(vid, 0.0):
                self._stored[vid] = rd.ts
                rows.append((rd.ts, vid, rd.value, rd.text if st.var.kind == "text" else None))
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
