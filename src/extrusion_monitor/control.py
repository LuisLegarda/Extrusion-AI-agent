"""Control PID sobre el HMI con aprendizaje del comportamiento del proceso.

Un lazo ajusta un input del HMI (p. ej. la velocidad del capstan) para llevar una medición (el diámetro) a su
objetivo (el nominal de la receta). Tres modos: *simulación* (calcula y registra, no escribe), *asistido*
(propone y el operador aplica con un clic) y *automático*.

PID incremental (forma de velocidad): cada ciclo calcula cuánto cambiar el input, así arranca sin saltos desde el
valor actual del HMI y el límite del input es también el anti-windup.

Aprendizaje: cada vez que el operador cambia el input, se observa cómo responde la medición durante
`learn_window_s` y se ajusta un modelo de primer orden con retardo (ganancia K, retardo θ, constante τ). Con
varios cambios observados se calcula el PID por la regla SIMC (Skogestad) y se conoce la dirección del efecto.

Seguridad: ver ControlLoop. Ante cualquier duda el lazo no escribe; si el HMI no acepta un valor, se desactiva.
"""
from __future__ import annotations

import json
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Callable, Optional

from .analysis.rules import Event, Level
from .config import AppConfig, ControlLoop, Variable

log = logging.getLogger(__name__)

MODE_LABELS = {"simulate": "Simulación", "assist": "Asistido", "auto": "Automático"}
OWN_CHANGE_S = 30.0  # un cambio del input en este tiempo tras escribirlo es nuestro (no del operador)
MIN_OBS = 3  # observaciones para confiar en el modelo aprendido
MAX_OBS = 12


# --- modelo aprendido -------------------------------------------------------------------------------------
@dataclass
class Observation:
    t0: float
    du: float
    k: float  # ganancia: cambio de la medición por unidad de input
    theta: float  # retardo (s)
    tau: float  # constante de tiempo (s)


@dataclass
class LearnedModel:
    obs: list = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.obs)

    def summary(self) -> Optional[tuple[float, float, float]]:
        if not self.obs:
            return None
        return (median(o.k for o in self.obs), median(o.theta for o in self.obs), median(o.tau for o in self.obs))

    @property
    def consistent(self) -> bool:
        """Todas las observaciones coinciden en la dirección del efecto."""
        return bool(self.obs) and (all(o.k > 0 for o in self.obs) or all(o.k < 0 for o in self.obs))

    @property
    def ready(self) -> bool:
        return self.n >= MIN_OBS and self.consistent

    def pid(self, aggressiveness: float = 1.0) -> Optional[tuple[float, float]]:
        """(Kc con signo, Ti) por SIMC: Kc = τ / (K (λ + θ)), Ti = min(τ, 4 (λ + θ)), λ = agresividad · τ."""
        s = self.summary()
        if s is None or not self.consistent:
            return None
        k, theta, tau = s
        if abs(k) < 1e-12:
            return None
        lam = max(aggressiveness * tau, 0.5 * theta, 1.0)
        return tau / (k * (lam + theta)), min(tau, 4 * (lam + theta))

    def to_json(self) -> list:
        return [o.__dict__ for o in self.obs]

    @classmethod
    def from_json(cls, data) -> "LearnedModel":
        out = cls()
        for d in data or []:
            try:
                out.obs.append(Observation(**d))
            except TypeError:
                pass
        return out


def fit_step(samples: list[tuple[float, float]], t0: float, du: float, window_s: float) -> Optional[Observation]:
    """Ajusta primer orden con retardo a la respuesta de la medición tras un cambio `du` del input en `t0`."""
    before = [v for t, v in samples if t0 - 90 <= t <= t0]
    after = [(t, v) for t, v in samples if t0 < t <= t0 + window_s]
    if len(before) < 3 or len(after) < 6 or abs(du) < 1e-12:
        return None
    base = median(before)
    mean = sum(before) / len(before)
    noise = math.sqrt(sum((v - mean) ** 2 for v in before) / len(before))
    tail = [v for t, v in after if t >= t0 + 0.75 * window_s]
    if len(tail) < 2:
        return None
    final = median(tail)
    dpv = final - base
    if abs(dpv) < max(3 * noise, 1e-9):
        return None  # no se distingue una respuesta del ruido
    def first(frac: float) -> Optional[float]:
        for t, v in after:
            if (v - base) / dpv >= frac:
                return t - t0
        return None
    t10, t63 = first(0.1), first(0.632)
    if t10 is None or t63 is None:
        return None
    # primer orden con retardo: el 10 % llega en θ + 0.105 τ y el 63 % en θ + τ
    tau = max(1.0, (t63 - t10) / 0.895)
    theta = max(0.0, t63 - tau)
    return Observation(t0=t0, du=du, k=dpv / du, theta=theta, tau=tau)


class ModelStore:
    """Modelos aprendidos por receta y lazo (control_models.json en la carpeta de datos)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict[str, list] = {}
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    @staticmethod
    def key(recipe: Optional[str], loop_id: str) -> str:
        return f"{recipe or '_'}::{loop_id}"

    def get(self, recipe: Optional[str], loop_id: str) -> LearnedModel:
        return LearnedModel.from_json(self.data.get(self.key(recipe, loop_id)))

    def put(self, recipe: Optional[str], loop_id: str, model: LearnedModel) -> None:
        self.data[self.key(recipe, loop_id)] = model.to_json()
        try:
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.exception("No se pudo guardar el modelo de control")


# --- estado de cada lazo ------------------------------------------------------------------------------------
@dataclass
class Proposal:
    u_from: float
    u_to: float
    pv: float
    target: float
    ts: float


@dataclass
class LoopState:
    active: bool = False  # el usuario lo activó (al abrir el programa queda desactivado)
    status: str = "Desactivado"
    detail: str = ""
    level: int = 0  # 0 normal · 1 en espera · 2 detenido por falla
    u_c: Optional[float] = None  # salida interna del PID
    e1: Optional[float] = None
    e2: Optional[float] = None
    last_t: Optional[float] = None
    last_write: float = 0.0
    writes: deque = field(default_factory=lambda: deque(maxlen=200))  # (ts, cambio)
    proposal: Optional[Proposal] = None
    accept: bool = False  # el operador aplicó la propuesta (modo asistido)
    hold_until: float = 0.0
    last_u: Optional[float] = None  # último valor del input visto en el HMI
    own_until: float = 0.0
    own_value: Optional[float] = None
    recipe: Optional[str] = None
    pv: Optional[float] = None
    target: Optional[float] = None
    u: Optional[float] = None
    pending_obs: list = field(default_factory=list)  # [(t0, du)] cambios del operador en observación
    pv_hist: deque = field(default_factory=lambda: deque(maxlen=4000))
    last_sim_msg: float = 0.0
    fault: str = ""


@dataclass
class WriteRequest:
    loop_id: str
    u_from: float
    u_to: float
    reason: str


def _decimals(var: Optional[Variable], fallback: int = 2) -> int:
    return var.decimals if var is not None and var.decimals is not None else fallback


def resolution(lp: ControlLoop, var: Optional[Variable], last_decimals: Optional[int] = None) -> float:
    if lp.write.method == "buttons":
        return lp.write.step
    if lp.resolution:
        return lp.resolution
    return 10 ** -(_decimals(var, last_decimals if last_decimals is not None else 2))


def quantize(u: float, res: float) -> float:
    return round(round(u / res) * res, 10)


class ControlManager:
    def __init__(self, store: ModelStore, clock: Callable[[], float] = time.time):
        self.store = store
        self.clock = clock
        self.states: dict[str, LoopState] = {}

    def state(self, loop_id: str) -> LoopState:
        return self.states.setdefault(loop_id, LoopState())

    def model(self, recipe: Optional[str], loop_id: str) -> LearnedModel:
        return self.store.get(recipe, loop_id)

    # --- órdenes del usuario --------------------------------------------------------------------------
    def set_active(self, loop_id: str, on: bool) -> None:
        st = self.state(loop_id)
        st.active = on
        st.u_c = st.e1 = st.e2 = st.last_t = None  # arranque sin saltos desde el valor del HMI
        st.proposal, st.accept, st.fault = None, False, ""
        if on:
            st.hold_until = 0.0

    def stop_all(self) -> None:
        for lid in list(self.states):
            self.set_active(lid, False)

    def accept_proposal(self, loop_id: str) -> None:
        st = self.state(loop_id)
        if st.proposal is not None:
            st.accept = True

    def reject_proposal(self, loop_id: str) -> None:
        st = self.state(loop_id)
        st.proposal, st.accept = None, False
        st.last_write = self.clock()  # no vuelve a proponer de inmediato

    # --- ciclo ------------------------------------------------------------------------------------------
    def evaluate(self, cfg: AppConfig, now: float, readings, statuses, findings, recipe, recipe_obj,
                 line_stopped: bool, idle_s: float, behavior_ok: Callable[[str], Optional[bool]]):
        events: list[Event] = []
        writes: list[WriteRequest] = []
        for lp in cfg.controls:
            st = self.state(lp.id)
            try:
                w = self._loop(cfg, lp, st, now, readings, statuses, findings, recipe, recipe_obj, line_stopped,
                               idle_s, behavior_ok, events)
            except Exception as exc:  # un lazo con falla no detiene el monitoreo
                log.exception("Control %s", lp.id)
                st.active, st.status, st.level, st.fault = False, "Detenido por error", 2, str(exc)
                events.append(Event(now, "control", Level.ALARM, "CONTROL", lp.pv_var or "",
                                    f"Control «{lp.name}» detenido: {exc}"))
                w = None
            if w is not None:
                writes.append(w)
        for lid in [k for k in self.states if cfg.control(k) is None]:
            del self.states[lid]
        return events, writes

    def _status(self, st: LoopState, text: str, detail: str = "", level: int = 1) -> None:
        st.status, st.detail, st.level = text, detail, level

    def _loop(self, cfg, lp: ControlLoop, st: LoopState, now, readings, statuses, findings, recipe, recipe_obj,
              line_stopped, idle_s, behavior_ok, events) -> Optional[WriteRequest]:
        pv_var, in_var = cfg.variable(lp.pv_var or ""), cfg.variable(lp.input_var or "")
        rd_pv = readings.get(lp.pv_var) if lp.pv_var else None
        rd_u = readings.get(lp.input_var) if lp.input_var else None
        pv = rd_pv.value if rd_pv is not None else None
        pv_age = rd_pv.age(now) if rd_pv is not None else None
        u = rd_u.value if rd_u is not None else None
        st.pv, st.u = pv, u
        if pv is not None and pv_age is not None and pv_age <= lp.max_pv_age_s:
            st.pv_hist.append((rd_pv.ts or now, pv))
        # objetivo
        target = lp.target_value if lp.target == "fixed" else None
        if lp.target == "recipe" and recipe_obj is not None and lp.pv_var:
            lim = recipe_obj.limits.get(lp.pv_var)
            target = lim.center() if lim is not None else None
        st.target = target
        if recipe != st.recipe:  # receta nueva: otro objetivo y otro modelo; se reinicia sin saltos
            if st.recipe is not None and st.active:
                st.hold_until = now + lp.operator_hold_s
                events.append(Event(now, "control", Level.INFO, "CONTROL", lp.pv_var or "",
                                    f"Control «{lp.name}»: cambio de receta, espera antes de ajustar"))
            st.recipe = recipe
            st.u_c = st.e1 = st.e2 = st.last_t = None
            st.pending_obs.clear()
        self._watch_input(lp, st, now, u, events)
        self._learn(lp, st, now, recipe)
        if not st.active:
            self._status(st, "Desactivado", "", 0)
            st.u_c = st.e1 = st.e2 = st.last_t = None
            st.proposal = None
            return None
        # --- compuertas de seguridad (sin ellas no se calcula ni se escribe) ---
        why = None
        if pv_var is None or in_var is None:
            why = "falta configurar la medición o el input"
        elif in_var.on_camera:
            why = "el input debe leerse de la pantalla del HMI"
        elif target is None:
            why = "sin objetivo (la receta no tiene nominal para la medición)"
        elif pv is None or pv_age is None or pv_age > lp.max_pv_age_s:
            why = "la medición no está actualizada"
        elif u is None or rd_u.age(now) is None or rd_u.age(now) > max(lp.max_pv_age_s, cfg.tour_stale_s()
                                                                        if lp.write.route_tour else 0):
            why = "el valor del input no está actualizado"
        elif lp.stop_when_line_stopped and line_stopped:
            why = "la línea está detenida"
        elif lp.stop_on_alarm and any(f.level >= Level.ALARM and f.var_id not in (lp.pv_var, lp.input_var)
                                      for f in findings):
            why = "hay una alarma activa"
        elif now < st.hold_until:
            why = f"espera tras un cambio del operador ({st.hold_until - now:.0f} s)"
        elif lp.gate_behavior and behavior_ok(lp.gate_behavior) is False:
            why = "el comportamiento del proceso no es normal"
        if why:
            self._status(st, "En espera", why, 1)
            st.u_c = st.e1 = st.e2 = st.last_t = None  # al reanudar, sin saltos ni integral acumulada
            st.proposal = None
            return None
        if st.accept:  # el operador aplicó la propuesta: se ejecuta tal cual (si sigue vigente)
            return self._pending_write(lp, st, now, events)
        # --- PID incremental ---
        gains = self.gains(lp, recipe)
        if gains is None:
            self._status(st, "En espera", "el PID aprendido aún no tiene suficientes observaciones "
                                          f"({self.model(recipe, lp.id).n} de {MIN_OBS})", 1)
            return None
        kc, ti, td = gains
        e = target - pv
        if abs(e) <= lp.deadband:
            e = 0.0
        if st.u_c is None or st.last_t is None:
            st.u_c, st.e1, st.e2, st.last_t = u, e, e, now
        ts = min(max(now - st.last_t, 0.5), 3 * lp.interval_s)
        du = kc * (e - st.e1)
        if ti > 0 and e != 0.0:
            du += kc * ts / ti * e
        if td > 0:
            du += kc * td / ts * (e - 2 * st.e1 + st.e2)
        st.e2, st.e1, st.last_t = st.e1, e, now
        lo = lp.u_min if lp.u_min is not None else -math.inf
        hi = lp.u_max if lp.u_max is not None else math.inf
        st.u_c = min(hi, max(lo, st.u_c + du))  # el límite del input es el anti-windup
        res = resolution(lp, in_var, getattr(rd_u, "decimals", None))
        # --- propuesta de ajuste ---
        if now - st.last_write < lp.interval_s:
            self._status(st, "Activo", f"próximo ajuste en {lp.interval_s - (now - st.last_write):.0f} s", 0)
            return self._pending_write(lp, st, now, events)
        delta = st.u_c - u
        if lp.max_step:
            delta = max(-lp.max_step, min(lp.max_step, delta))
        if lp.max_rate_min:
            used = sum(abs(d) for t, d in st.writes if t >= now - 60)
            room = max(0.0, lp.max_rate_min - used)
            delta = max(-room, min(room, delta))
        new = quantize(min(hi, max(lo, u + delta)), res)
        if abs(new - u) < res * 0.5:
            self._status(st, "Activo", "en el objetivo" if e == 0 else "sin ajuste necesario", 0)
            st.proposal = None
            return self._pending_write(lp, st, now, events)
        reason = (f"{pv_var.name} {pv:.{_decimals(pv_var, 3)}f} vs objetivo {target:.{_decimals(pv_var, 3)}f}")
        dec = _decimals(in_var, 2)
        if lp.mode == "simulate":
            st.last_write = now
            st.writes.append((now, new - u))
            self._status(st, "Simulación", f"ajustaría {u:.{dec}f} → {new:.{dec}f}", 0)
            events.append(Event(now, "control", Level.INFO, "CONTROL", lp.input_var or "",
                                f"Control «{lp.name}» (simulación): ajustaría «{in_var.name}» {u:.{dec}f} → "
                                f"{new:.{dec}f} ({reason})"))
            return None
        if lp.mode == "assist":
            if st.proposal is None or abs(st.proposal.u_to - new) >= res * 0.5:
                st.proposal = Proposal(u, new, pv, target, now)
                st.accept = False
            self._status(st, "Propuesta", f"{u:.{dec}f} → {new:.{dec}f}: aplica o ignora", 0)
            return self._pending_write(lp, st, now, events)
        if idle_s < lp.operator_idle_s:
            self._status(st, "En espera", "el operador está usando el HMI", 1)
            return None
        return WriteRequest(lp.id, u, new, reason)

    def _pending_write(self, lp, st: LoopState, now, events) -> Optional[WriteRequest]:
        """Propuesta aceptada por el operador (modo asistido)."""
        if lp.mode != "assist" or st.proposal is None or not st.accept:
            return None
        p = st.proposal
        st.proposal, st.accept = None, False
        if now - p.ts > max(2 * lp.interval_s, 120) or st.u is None or abs(st.u - p.u_from) > 1e-9:
            events.append(Event(now, "control", Level.INFO, "CONTROL", lp.input_var or "",
                                f"Control «{lp.name}»: la propuesta ya no es vigente; se recalcula"))
            return None
        return WriteRequest(lp.id, p.u_from, p.u_to, "aplicado por el operador")

    def gains(self, lp: ControlLoop, recipe) -> Optional[tuple[float, float, float]]:
        """(Kc con signo, Ti, Td). Con el error = objetivo − medición, Kc negativo sube el input si la medición
        está alta («inc_when_high»)."""
        if lp.tuning == "learned":
            m = self.model(recipe, lp.id)
            if not m.ready:
                return None
            kc, ti = m.pid(lp.aggressiveness)
            return kc, ti, 0.0
        sign = -1.0 if lp.action == "inc_when_high" else 1.0
        return sign * lp.kp, lp.ti_s, lp.td_s

    # --- escritura confirmada -----------------------------------------------------------------------------
    def wrote(self, lp: ControlLoop, req: WriteRequest, ok: bool, msg: str, now: float, events) -> None:
        st = self.state(lp.id)
        if ok:
            st.last_write = now
            st.writes.append((now, req.u_to - req.u_from))
            st.own_until, st.own_value = now + OWN_CHANGE_S, req.u_to
            st.last_u = req.u_to
            st.u_c = req.u_to if st.u_c is None else st.u_c
            self._status(st, "Activo", f"ajustado a {req.u_to:g}", 0)
            events.append(Event(now, "control", Level.INFO, "CONTROL", lp.input_var or "",
                                f"Control «{lp.name}»: «{lp.input_var}» {req.u_from:g} → {req.u_to:g} ({req.reason})"))
        else:
            st.active = False
            st.fault = msg
            self._status(st, "Detenido por falla", msg, 2)
            events.append(Event(now, "control", Level.ALARM, "CONTROL", lp.input_var or "",
                                f"Control «{lp.name}» detenido: {msg}. Revisa el HMI y vuelve a activarlo."))

    # --- cambios del operador y aprendizaje ---------------------------------------------------------------
    def _watch_input(self, lp: ControlLoop, st: LoopState, now: float, u: Optional[float], events) -> None:
        if u is None:
            return
        prev = st.last_u
        st.last_u = u
        if prev is None or abs(u - prev) < 1e-9:
            return
        if now <= st.own_until and st.own_value is not None and abs(u - st.own_value) < 1e-6:
            return  # es el valor que escribimos
        # cambio del operador: el control espera y el cambio se usa para aprender
        if st.active:
            st.hold_until = now + lp.operator_hold_s
            st.u_c = st.e1 = st.e2 = st.last_t = None
            st.proposal = None
            events.append(Event(now, "control", Level.INFO, "CONTROL", lp.input_var or "",
                                f"Control «{lp.name}»: el operador cambió «{lp.input_var}» {prev:g} → {u:g}; "
                                f"espera {lp.operator_hold_s:.0f} s"))
        if lp.learn:
            st.pending_obs = [o for o in st.pending_obs if now - o[0] < lp.learn_window_s]
            st.pending_obs.append((now, u - prev))

    def _learn(self, lp: ControlLoop, st: LoopState, now: float, recipe) -> None:
        if not st.pending_obs:
            return
        done = []
        for t0, du in list(st.pending_obs):
            if now < t0 + lp.learn_window_s:
                continue
            done.append((t0, du))
            # otro cambio durante la ventana mezcla respuestas: no se usa
            others = [o for o in st.pending_obs if o[0] != t0 and t0 < o[0] <= t0 + lp.learn_window_s]
            own = [t for t, _ in st.writes if t0 < t <= t0 + lp.learn_window_s]
            if others or own:
                continue
            obs = fit_step(list(st.pv_hist), t0, du, lp.learn_window_s)
            if obs is None:
                continue
            m = self.model(recipe, lp.id)
            m.obs = (m.obs + [obs])[-MAX_OBS:]
            self.store.put(recipe, lp.id, m)
            log.info("Control %s: observación aprendida K=%.4g θ=%.0f s τ=%.0f s (%d)", lp.id, obs.k, obs.theta,
                     obs.tau, m.n)
        st.pending_obs = [o for o in st.pending_obs if o not in done]

    def snapshot(self, cfg: AppConfig) -> dict:
        out = {}
        for lp in cfg.controls:
            st = self.state(lp.id)
            out[lp.id] = {"name": lp.name, "mode": lp.mode, "active": st.active, "status": st.status,
                          "detail": st.detail, "level": st.level, "pv": st.pv, "target": st.target, "u": st.u,
                          "proposal": (st.proposal.u_from, st.proposal.u_to) if st.proposal else None}
        return out


# --- escritura en el HMI ----------------------------------------------------------------------------------------
class ControlWriter:
    """Escribe el valor en el HMI con clics verificados (como los recorridos) y comprueba que el HMI lo aceptó."""

    def __init__(self, runner, acquirer_read: Callable, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep):
        self.runner = runner  # TourRunner: clics verificados por imagen, llegada a pantallas y regreso
        self.read = acquirer_read  # frame -> lecturas (actualiza las variables)
        self.clock = clock
        self.sleep = sleep

    def write(self, cfg: AppConfig, lp: ControlLoop, value: float, u_now: float, decimals: int,
              decimal_sep: str = ".") -> tuple[bool, str]:
        from .navigation import TourAborted
        r = self.runner
        w = lp.write
        tour = cfg.get_tour(w.route_tour) if w.route_tour else None
        moved = False
        try:
            frame = r.source.grab()
            r._mark_own_input()
            if tour is not None:
                r._tour = tour
                for i, step in enumerate(tour.steps, 1):
                    frame = r._clicks(step.clicks, frame, f"ruta {i}")
                    moved = True
                    frame = r._arrive(step.page, step.settle_s, f"ruta {i}", tour.page_retries)
            in_var = cfg.variable(lp.input_var or "")
            if in_var is not None and in_var.page and in_var.page not in r.pages.visible_pages(frame):
                page = cfg.page(in_var.page)
                raise TourAborted(f"el HMI no está en la pantalla del input («{page.name if page else in_var.page}»)")
            if w.method == "type":
                # El campo muestra el valor que cambia: no se verifica por imagen sino por la pantalla (arriba).
                r._check_operator()
                clk = r.clicker
                clk.click(w.field.x, w.field.y)
                r._mark_own_input()
                self.sleep(0.3)
                if w.select_all:
                    clk.key("ctrl+a")
                text = f"{value:.{decimals}f}"
                if decimal_sep == ",":
                    text = text.replace(".", ",")
                clk.type_text(text)
                clk.key("enter")
                r._mark_own_input()
                if w.confirm is not None:
                    self.sleep(0.6)
                    r._clicks([w.confirm], r.source.grab(), "confirmación")
            else:
                n = int(round((value - u_now) / w.step))
                n = max(-w.max_clicks, min(w.max_clicks, n))
                btn = w.inc if n > 0 else w.dec
                for k in range(abs(n)):
                    r._clicks([btn], r.source.grab() if k else frame, "botón del input")
                    self.sleep(0.25)
            ok, seen = self._verify(cfg, lp, value)
            if tour is not None and tour.return_clicks:
                f2 = r._clicks(tour.return_clicks, r.source.grab(), "regreso")
                if tour.return_page:
                    r._arrive(tour.return_page, tour.return_settle_s, "regreso", tour.page_retries)
                del f2
            moved = False
            if not ok:
                return False, (f"el HMI no muestra el valor escrito ({value:g}; se lee "
                               f"{'—' if seen is None else f'{seen:g}'})")
            return True, ""
        except TourAborted as exc:
            msg = str(exc)
            if moved and tour is not None and tour.return_clicks:
                msg += r._try_return_home()
            return False, msg

    def _verify(self, cfg: AppConfig, lp: ControlLoop, value: float) -> tuple[bool, Optional[float]]:
        tol = max(resolution(lp, cfg.variable(lp.input_var or "")) * 0.51, 1e-9)
        deadline = self.clock() + lp.write.verify_s
        self.sleep(lp.write.settle_s)
        seen = None
        while True:
            readings = self.read(self.runner.source.grab())
            rd = readings.get(lp.input_var) if readings else None
            if rd is not None and rd.ok and rd.value is not None:
                seen = rd.value
                if abs(rd.value - value) <= tol:
                    return True, seen
            if self.clock() >= deadline:
                return False, seen
            self.sleep(1.0)
