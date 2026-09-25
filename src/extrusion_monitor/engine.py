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


@dataclass
class EngineState:
    recipe: Optional[str] = None
    auto_recipe: bool = True


class MonitorEngine:
    def __init__(self, workspace: Workspace, config: AppConfig, recipes: RecipeStore,
                 source: FrameSource, ocr: OcrEngine, historian: Optional[Historian] = None,
                 clock: Callable[[], float] = time.time):
        self.workspace = workspace
        self.config = config
        self.recipes = recipes
        self.source = source
        self.ocr = ocr
        self.historian = historian
        self.clock = clock
        self.state = EngineState()
        self.listeners: list[Callable[[Snapshot], None]] = []
        self.last: Optional[Snapshot] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._pending_events: list[Event] = []
        self._build()

    def _build(self) -> None:
        g = self.config.general
        self.pages = PageDetector.from_workspace(self.config, self.workspace)
        self.acquirer = Acquirer(self.config, self.ocr, self.pages)
        self.rules = RuleEngine(self.config)
        self.trends = TrendTracker(g.trend_window_min * 60, g.spc_subgroup_s)

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
        with self._lock:
            return self.trends.series(var_id)

    def grab_frame(self):
        with self._lock:
            return self.source.grab()

    # --- ciclo ---------------------------------------------------------------
    def step(self) -> Snapshot:
        with self._lock:
            t0 = time.perf_counter()
            now = self.clock()
            error = ""
            try:
                frame = self.source.grab()
                pages, readings = self.acquirer.read(frame, now)
            except Exception as exc:
                log.exception("Fallo de captura")
                error = f"Fallo de captura: {exc}"
                pages, readings = set(), self.acquirer.readings
            self._auto_select_recipe(readings)
            statuses, events = self.rules.evaluate(now, readings, self.recipe, self.trends)
            events = self._pending_events + events
            self._pending_events = []
            findings = self.rules.active_findings()
            overall = max((f.level for f in findings), default=Level.OK)
            visible = [r for r in readings.values() if r.visible]
            snap = Snapshot(
                ts=now, cycle_ms=(time.perf_counter() - t0) * 1000, pages=pages, statuses=statuses,
                findings=findings, events=events, recipe=self.state.recipe, ocr_engine=self.ocr.name,
                error=error, overall=overall, read_ok=sum(r.ok for r in visible), read_total=len(visible))
            self._store(snap)
            self.last = snap
        for cb in list(self.listeners):
            try:
                cb(snap)
            except Exception:
                log.exception("Error en listener")
        return snap

    def _store(self, snap: Snapshot) -> None:
        if not self.historian:
            return
        rows = []
        for vid, st in snap.statuses.items():
            rd = st.reading
            if rd.ok and rd.ts == snap.ts:
                rows.append((snap.ts, vid, rd.value, rd.text if st.var.kind == "text" else None))
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
