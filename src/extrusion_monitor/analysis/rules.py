"""Reglas de verificación: ajustes vs. receta, tolerancias, lectura y tendencias."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from ..acquisition import Reading
from ..config import AppConfig, Variable
from ..recipes import Recipe, normalize_name
from .trends import TrendStats, TrendTracker


class Level(IntEnum):
    OK = 0
    INFO = 1
    WARN = 2
    ALARM = 3

    @property
    def label(self) -> str:
        return {0: "OK", 1: "INFO", 2: "AVISO", 3: "ALARMA"}[int(self)]


# Reglas
R_RECIPE = "AJUSTE_RECETA"  # consigna distinta de la receta
R_TOL = "TOLERANCIA"  # valor real fuera de tolerancia
R_READ = "LECTURA"  # no se puede leer la variable
R_DRIFT = "TENDENCIA"  # la tendencia alcanzará el límite dentro del horizonte
R_SPC = "SPC"  # reglas de Nelson
R_HMI_RECIPE = "RECETA_HMI"  # el HMI muestra otra receta
R_NO_RECIPE = "SIN_RECETA"
R_SELECTOR = "SELECTOR"  # selector en estado distinto al de la receta
R_BEHAVIOR = "COMPORTAMIENTO"  # comportamiento aprendido

IMMEDIATE_RULES = {R_READ, R_HMI_RECIPE, R_NO_RECIPE}
# Reglas estadísticas: se desactivan con más histéresis y no generan eventos en el registro.
SLOW_CLEAR_RULES = {R_DRIFT, R_SPC, R_BEHAVIOR}
SILENT_RULES = {R_SPC}
SLOW_CLEAR_FACTOR = 3
# Histéresis: un hallazgo de tolerancia activo se mantiene hasta volver por debajo del 90 % de la banda.
HYSTERESIS = 0.9
MIN_TREND_SPAN_S = 60.0


@dataclass
class Finding:
    rule: str
    var_id: str
    level: Level
    message: str
    since: float
    peak: Level = Level.OK

    @property
    def key(self) -> tuple[str, str]:
        return self.rule, self.var_id


@dataclass
class Event:
    ts: float
    kind: str  # raised | escalated | cleared | setpoint_change | recipe_change
    level: Level
    rule: str
    var_id: str
    message: str


@dataclass
class VarStatus:
    var: Variable
    reading: Reading
    reference: Optional[float] = None
    ref_source: str = ""  # "receta" | "consigna"
    deviation: Optional[float] = None
    warn_band: Optional[float] = None
    alarm_band: Optional[float] = None
    level: Optional[Level] = None  # None = sin evaluar (dato viejo o no visible)
    trend: Optional[TrendStats] = None
    fresh: bool = False
    expected: Optional[str] = None  # selector: estado esperado por la receta


@dataclass
class _KeyState:
    hits: int = 0
    misses: int = 0
    finding: Optional[Finding] = None


@dataclass
class _Condition:
    level: Level
    message: str


def fmt(v: Optional[float], var: Optional[Variable] = None, decimals: Optional[int] = None) -> str:
    if v is None:
        return "—"
    if var is not None and var.decimals is not None:
        decimals = var.decimals
    if decimals is not None:
        return f"{v:.{decimals}f}"
    return f"{v:.4g}" if abs(v) < 1e5 else f"{v:.0f}"


class RuleEngine:
    def __init__(self, config: AppConfig):
        self.config = config
        self._state: dict[tuple[str, str], _KeyState] = {}
        self._last_sp: dict[str, float] = {}
        self._last_state: dict[str, str] = {}

    def stale_limit(self, var: Variable) -> float:
        g = self.config.general
        if var.page in self.config.toured_pages():
            return max(g.stale_after_s, self.config.tour.interval_s * 2.5)
        return g.stale_after_s

    def fresh_values(self, now: float, readings: dict[str, Reading]) -> dict[str, float]:
        """Valores numéricos con dato vigente (para el modelo de comportamiento)."""
        out = {}
        for var in self.config.variables:
            rd = readings.get(var.id)
            if var.numeric and rd and rd.value is not None and rd.ts is not None:
                if now - rd.ts <= self.stale_limit(var):
                    out[var.id] = rd.value
        return out

    def active_findings(self) -> list[Finding]:
        out = [s.finding for s in self._state.values() if s.finding]
        return sorted(out, key=lambda f: (-f.level, f.since))

    def evaluate(self, now: float, readings: dict[str, Reading], recipe: Optional[Recipe],
                 trends: TrendTracker, extra: Optional[tuple[dict, set]] = None
                 ) -> tuple[dict[str, VarStatus], list[Event]]:
        """`extra`: condiciones externas ({(regla, clave): (nivel, mensaje)}, claves evaluadas)."""
        g = self.config.general
        conds: dict[tuple[str, str], _Condition] = {}
        evaluated: set[str] = {""}
        events: list[Event] = []
        statuses: dict[str, VarStatus] = {}
        # Las pestañas del recorrido se leen una vez por recorrido: su dato vale hasta el siguiente.
        toured = self.config.toured_pages()
        tour_stale = max(g.stale_after_s, self.config.tour.interval_s * 2.5)

        if recipe is None:
            conds[(R_NO_RECIPE, "")] = _Condition(Level.INFO, "No hay receta activa: solo se registran valores")

        for var in self.config.variables:
            rd = readings.get(var.id) or Reading(var.id)
            st = VarStatus(var=var, reading=rd)
            statuses[var.id] = st
            age = rd.age(now)
            st.fresh = age is not None and age <= (tour_stale if var.page in toured else g.stale_after_s)

            if rd.visible:
                evaluated.add(var.id)
                if rd.fail_count >= g.read_fail_samples or (not st.fresh and rd.ts is not None):
                    conds[(R_READ, var.id)] = _Condition(
                        Level.WARN, f"No se puede leer «{self.config.var_label(var)}» ({rd.reason or 'sin datos recientes'})")

            if var.kind == "selector":
                self._eval_selector(now, var, rd, st, recipe, conds, events)
                if not st.fresh:
                    evaluated.discard(var.id)
                continue

            if var.kind == "text":
                if var.id == g.recipe_name_var and recipe and rd.text and st.fresh and rd.visible:
                    if normalize_name(rd.text) != normalize_name(recipe.name):
                        conds[(R_HMI_RECIPE, var.id)] = _Condition(
                            Level.WARN, f"El HMI muestra la receta «{rd.text}» pero la activa es «{recipe.name}»")
                continue

            if var.kind == "setpoint" and rd.value is not None and rd.ts is not None:
                prev = self._last_sp.get(var.id)
                if prev is not None and prev != rd.value:
                    events.append(self._setpoint_event(now, var, prev, rd.value, recipe))
                self._last_sp[var.id] = rd.value

            if rd.value is not None and rd.ts is not None:
                trends.add(var.id, rd.ts, rd.value)  # ignora lecturas ya agregadas

            if recipe is None or not st.fresh or rd.value is None:
                if not st.fresh:
                    evaluated.discard(var.id)  # sin dato fresco: los hallazgos se mantienen
                continue
            lim = recipe.limits.get(var.id)
            if lim is None:
                st.level = Level.OK
                continue

            ref, src = lim.nominal, "receta"
            if var.kind == "actual" and lim.reference == "setpoint" and var.setpoint_var:
                sp = readings.get(var.setpoint_var)
                if sp is not None and sp.value is not None:
                    ref, src = sp.value, "consigna"
            if ref is None:
                st.level = Level.OK
                continue
            warn, alarm = lim.band(ref)
            st.reference, st.ref_source = ref, src
            st.deviation = rd.value - ref
            st.warn_band, st.alarm_band = warn, alarm
            dev = abs(st.deviation)
            rule = R_RECIPE if var.kind == "setpoint" else R_TOL
            active = self._state.get((rule, var.id))
            active_level = active.finding.level if active and active.finding else Level.OK
            k_alarm = HYSTERESIS if active_level >= Level.ALARM else 1.0
            k_warn = HYSTERESIS if active_level >= Level.WARN else 1.0
            level = Level.OK
            if alarm is not None and dev > alarm * k_alarm:
                level = Level.ALARM
            elif warn is not None and dev > warn * k_warn:
                level = Level.WARN
            st.level = level

            if level > Level.OK:
                band = alarm if level == Level.ALARM else warn
                if var.kind == "setpoint":
                    msg = (f"Ajuste erróneo «{self.config.var_label(var)}»: consigna {fmt(rd.value, var)} {var.unit}, "
                           f"receta {fmt(ref, var)} (Δ {st.deviation:+.4g}, tolerancia ±{band:.4g})")
                    conds[(R_RECIPE, var.id)] = _Condition(level, msg)
                else:
                    msg = (f"«{self.config.var_label(var)}» fuera de tolerancia: {fmt(rd.value, var)} {var.unit} vs {src} "
                           f"{fmt(ref, var)} (Δ {st.deviation:+.4g}, tolerancia ±{band:.4g})")
                    conds[(R_TOL, var.id)] = _Condition(level, msg)

            if var.trend and var.kind == "actual":
                lo = ref - alarm if alarm is not None else None
                hi = ref + alarm if alarm is not None else None
                effect = warn if warn is not None else (alarm / 2 if alarm is not None else 0.0)
                ts = trends.stats(var.id, now, center=ref, lo_limit=lo, hi_limit=hi, min_effect=effect)
                st.trend = ts
                enough = ts is not None and ts.span_s >= max(MIN_TREND_SPAN_S, g.trend_window_min * 15)
                if enough and level < Level.ALARM:
                    if (ts.eta_to_alarm_min is not None and ts.eta_to_alarm_min <= g.trend_horizon_min
                            and dev >= 0.25 * effect):
                        conds[(R_DRIFT, var.id)] = _Condition(
                            Level.WARN,
                            f"«{self.config.var_label(var)}» tiende a salir de tolerancia en ~{ts.eta_to_alarm_min:.1f} min "
                            f"({ts.slope_per_min:+.3g} {var.unit}/min)")
                    if ts.nelson:
                        conds[(R_SPC, var.id)] = _Condition(
                            Level.INFO, f"«{self.config.var_label(var)}»: " + "; ".join(ts.nelson))

        if extra is not None:
            ext_conds, ext_eval = extra
            conds.update({k: _Condition(lv, msg) for k, (lv, msg) in ext_conds.items()})
            evaluated |= ext_eval
        events.extend(self._apply(now, conds, evaluated))
        return statuses, events

    def _eval_selector(self, now, var, rd, st, recipe, conds, events) -> None:
        if rd.text and rd.ts is not None:
            prev = self._last_state.get(var.id)
            if prev is not None and prev != rd.text:
                events.append(Event(now, "setpoint_change", Level.INFO, "CAMBIO_SELECTOR", var.id,
                                    f"Cambio de selector «{self.config.var_label(var)}»: {prev} → {rd.text}"))
            self._last_state[var.id] = rd.text
        lim = recipe.limits.get(var.id) if recipe else None
        if not (lim and lim.expected and st.fresh and rd.text):
            st.level = Level.OK if st.fresh and rd.text else None
            return
        st.ref_source = "receta"
        st.expected = lim.expected
        if rd.text != lim.expected:
            st.level = Level.ALARM
            conds[(R_SELECTOR, var.id)] = _Condition(
                Level.ALARM, f"Selector «{self.config.var_label(var)}» en «{rd.text}»; "
                             f"la receta espera «{lim.expected}»")
        else:
            st.level = Level.OK

    def _setpoint_event(self, now: float, var: Variable, prev: float, new: float,
                        recipe: Optional[Recipe]) -> Event:
        msg = f"Cambio de ajuste «{self.config.var_label(var)}»: {fmt(prev, var)} → {fmt(new, var)} {var.unit}"
        level = Level.INFO
        lim = recipe.limits.get(var.id) if recipe else None
        if lim and lim.nominal is not None:
            warn, alarm = lim.band(lim.nominal)
            tol = warn if warn is not None else alarm
            if tol is not None and abs(new - lim.nominal) > tol:
                level = Level.WARN
                msg += f" (se aleja de la receta: {fmt(lim.nominal, var)})"
            else:
                msg += " (dentro de receta)"
        return Event(now, "setpoint_change", level, "CAMBIO_AJUSTE", var.id, msg)

    def _apply(self, now: float, conds: dict[tuple[str, str], _Condition],
               evaluated: set[str]) -> list[Event]:
        debounce = self.config.general.debounce_samples
        events: list[Event] = []
        for key, cond in conds.items():
            s = self._state.setdefault(key, _KeyState())
            s.hits += 1
            s.misses = 0
            need = 1 if key[0] in IMMEDIATE_RULES else debounce
            log = key[0] not in SILENT_RULES
            if s.finding is None:
                if s.hits >= need:
                    s.finding = Finding(key[0], key[1], cond.level, cond.message, now, cond.level)
                    if log:
                        events.append(Event(now, "raised", cond.level, key[0], key[1], cond.message))
            else:
                if cond.level > s.finding.peak:
                    s.finding.peak = cond.level
                    if log:
                        events.append(Event(now, "escalated", cond.level, key[0], key[1], cond.message))
                s.finding.level, s.finding.message = cond.level, cond.message
        for key, s in list(self._state.items()):
            if key in conds or key[1] not in evaluated:
                continue
            s.hits = 0
            s.misses += 1
            need = 1 if key[0] in IMMEDIATE_RULES else debounce
            if key[0] in SLOW_CLEAR_RULES:
                need *= SLOW_CLEAR_FACTOR
            if s.finding is not None and s.misses >= need:
                if key[0] not in SILENT_RULES:
                    events.append(Event(now, "cleared", Level.OK, key[0], key[1],
                                        f"Normalizado: {s.finding.message}"))
                s.finding = None
            if s.finding is None and s.misses >= need:
                del self._state[key]
        return events

    def reset(self) -> None:
        self._state.clear()
