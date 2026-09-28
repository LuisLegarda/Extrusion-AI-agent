"""Disparadores de recorridos: intervalo, fuera de una pantalla, cambio de selector y valor a cero.

Con confirmación, el recorrido se anuncia con una cuenta regresiva: el operador puede posponerlo
(vuelve a aparecer tras `snooze_s`) o aceptarlo; si lo ignora, se ejecuta al terminar la cuenta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Callable, Optional

from .config import AppConfig, TourDef


@dataclass
class TourRuntime:
    last_run: Optional[float] = None
    snoozed_until: float = 0.0
    prompt_deadline: Optional[float] = None
    prompt_reason: str = ""
    off_since: Optional[float] = None
    last_state: Optional[str] = None
    above: Optional[bool] = None


@dataclass
class TourJob:
    tour_id: str
    reason: str
    consent: bool  # aceptado o cuenta regresiva cumplida: no se exige inactividad del operador
    created: float = field(default_factory=time.time)


class TourScheduler:
    def __init__(self, config: AppConfig, clock: Callable[[], float]):
        self.config = config
        self.clock = clock
        self.runtime: dict[str, TourRuntime] = {}
        self.queue: list[TourJob] = []

    def reconfigure(self, config: AppConfig) -> None:
        self.config = config
        ids = {t.id for t in config.tours}
        self.runtime = {k: v for k, v in self.runtime.items() if k in ids}
        self.queue = [j for j in self.queue if j.tour_id in ids]

    def rt(self, tour_id: str) -> TourRuntime:
        return self.runtime.setdefault(tour_id, TourRuntime())

    # --- disparadores -------------------------------------------------------------------
    def update(self, now: float, visible_pages: set[str], readings: dict) -> list[str]:
        """Evalúa los disparadores con la lectura del ciclo. Devuelve mensajes para el registro."""
        msgs: list[str] = []
        for t in self.config.tours:
            if not (t.enabled and t.steps):
                continue
            rt = self.rt(t.id)
            reason = self._triggered(t, rt, now, visible_pages, readings)
            if rt.prompt_deadline is not None and now >= rt.prompt_deadline:
                rt.prompt_deadline = None
                self._enqueue(t, rt.prompt_reason + " (cuenta regresiva cumplida)", consent=True)
                continue
            if not reason or self._queued(t.id) or rt.prompt_deadline is not None:
                continue
            if t.confirm:
                if now < rt.snoozed_until:
                    continue
                rt.prompt_deadline = now + t.countdown_s
                rt.prompt_reason = reason
                msgs.append(f"Recorrido «{t.name}» en {t.countdown_s:.0f} s: {reason}")
            else:
                self._enqueue(t, reason, consent=False)
        return msgs

    def _triggered(self, t: TourDef, rt: TourRuntime, now: float, visible: set[str], readings: dict) -> str:
        reasons = []
        if t.interval_s and (rt.last_run is None or now - rt.last_run >= t.interval_s):
            reasons.append(f"cada {t.interval_s:g} s")
        if t.off_page and self.config.page(t.off_page) is not None:
            if t.off_page in visible:
                rt.off_since = None
            else:
                rt.off_since = rt.off_since if rt.off_since is not None else now
                if now - rt.off_since >= t.off_page_s:
                    page = self.config.page(t.off_page)
                    reasons.append(f"fuera de «{page.name}» {now - rt.off_since:.0f} s")
        if t.selector_var:
            rd = readings.get(t.selector_var)
            state = rd.text if rd is not None and rd.ok else None
            if state is not None:
                if rt.last_state is not None and state != rt.last_state and \
                        (t.selector_state is None or state == t.selector_state):
                    reasons.append(f"selector {rt.last_state} → {state}")
                rt.last_state = state
        if t.zero_var:
            rd = readings.get(t.zero_var)
            if rd is not None and rd.ok and rd.value is not None:
                above = rd.value > t.zero_threshold
                if rt.above and not above:
                    reasons.append(f"valor bajó a {rd.value:g}")
                rt.above = above
        return "; ".join(reasons)

    def _queued(self, tour_id: str) -> bool:
        return any(j.tour_id == tour_id for j in self.queue)

    def _enqueue(self, t: TourDef, reason: str, consent: bool) -> None:
        if not self._queued(t.id):
            self.queue.append(TourJob(t.id, reason, consent, self.clock()))

    def requeue(self, job: TourJob) -> None:
        if not self._queued(job.tour_id) and self.config.get_tour(job.tour_id) is not None:
            self.queue.append(job)

    # --- acciones del operador / interfaz ------------------------------------------------
    def pending_prompts(self) -> dict[str, tuple[float, str]]:
        return {tid: (rt.prompt_deadline, rt.prompt_reason) for tid, rt in self.runtime.items()
                if rt.prompt_deadline is not None}

    def confirm(self, tour_id: str) -> None:
        t = self.config.get_tour(tour_id)
        rt = self.rt(tour_id)
        if t and rt.prompt_deadline is not None:
            rt.prompt_deadline = None
            self._enqueue(t, rt.prompt_reason + " (aceptado)", consent=True)

    def snooze(self, tour_id: str) -> None:
        t = self.config.get_tour(tour_id)
        rt = self.rt(tour_id)
        rt.prompt_deadline = None
        if t:
            rt.snoozed_until = self.clock() + t.snooze_s

    def run_now(self, tour_id: Optional[str] = None) -> None:
        tours = [self.config.get_tour(tour_id)] if tour_id else \
            [t for t in self.config.tours if t.enabled and t.read_data] or list(self.config.tours)
        for t in tours[:1]:
            if t:
                self._enqueue(t, "manual", consent=False)

    def pop(self) -> Optional[TourJob]:
        return self.queue.pop(0) if self.queue else None

    def mark_run(self, tour_id: str, now: float) -> None:
        rt = self.rt(tour_id)
        rt.last_run = now
        rt.off_since = None
