"""OEE (disponibilidad × rendimiento × calidad) e indicadores de Industria 5.0.

Cada ciclo del monitoreo se clasifica en un estado (en marcha, lento, detenido, sin datos)
según la velocidad de línea. Los paros más cortos que `microstop_s` son microparos: no
restan disponibilidad pero sí rendimiento (la línea "estaba en marcha" a velocidad 0).
La calidad se mide en longitud: metros producidos en condición conforme / metros totales.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

RUNNING, SLOW, STOPPED, MICROSTOP, UNKNOWN = "running", "slow", "stopped", "microstop", "unknown"
# Hueco sin datos que, al volver la lectura con todo en parámetros, se considera productivo.
ASSUMED = "assumed"
STATE_LABELS = {RUNNING: "En marcha", SLOW: "Lento", MICROSTOP: "Microparo", STOPPED: "Paro",
                ASSUMED: "Sin datos (productivo)", UNKNOWN: "Sin datos"}
STATE_ORDER = [RUNNING, ASSUMED, SLOW, MICROSTOP, STOPPED, UNKNOWN]


@dataclass
class OeeSample:
    ts: float
    dt: float
    state: str  # running | slow | stopped | unknown (el microparo se decide al calcular)
    speed: Optional[float]
    nominal: Optional[float]
    good: Optional[bool]
    overall: int  # nivel general de hallazgos en ese ciclo (0..3)


@dataclass
class Interval:
    state: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class OeeResult:
    start: float
    end: float
    availability: Optional[float] = None
    performance: Optional[float] = None
    quality: Optional[float] = None
    oee: Optional[float] = None
    teep: Optional[float] = None
    planned_s: float = 0.0
    run_s: float = 0.0
    stop_s: float = 0.0
    unknown_s: float = 0.0
    n_stops: int = 0
    n_microstops: int = 0
    mtbf_s: Optional[float] = None
    mttr_s: Optional[float] = None
    length_total: float = 0.0
    length_good: float = 0.0
    avg_speed: Optional[float] = None
    avg_nominal: Optional[float] = None
    normal_pct: Optional[float] = None  # % del tiempo sin avisos/alarmas activos
    intervals: list[Interval] = field(default_factory=list)
    distribution: dict[str, tuple[float, int]] = field(default_factory=dict)  # estado -> (s, ocurrencias)

    @property
    def length_scrap(self) -> float:
        return max(0.0, self.length_total - self.length_good)


def classify(speed: Optional[float], nominal: Optional[float], stop_threshold: float,
             slow_pct: float) -> str:
    if speed is None:
        return UNKNOWN
    if speed <= stop_threshold:
        return STOPPED
    if nominal and speed < nominal * slow_pct / 100.0:
        return SLOW
    return RUNNING


def compute(samples: list[OeeSample], start: float, end: float, microstop_s: float,
            length_factor: float = 1.0, blip_s: float = 8.0) -> OeeResult:
    """KPIs del periodo. `length_factor` convierte velocidad a longitud por minuto (m/min = 1)."""
    res = OeeResult(start=start, end=end)
    rows = [s for s in samples if start <= s.ts <= end]
    if not rows:
        return res
    # Intervalos de estado consecutivos (con la duración de cada muestra hacia atrás).
    raw: list[Interval] = []
    row_iv: list[int] = []  # intervalo al que pertenece cada muestra
    for s in rows:
        a = max(start, s.ts - s.dt)
        if raw and raw[-1].state == s.state and abs(raw[-1].end - a) < 1e-6:
            raw[-1].end = s.ts
        else:
            raw.append(Interval(s.state, a, s.ts))
        row_iv.append(len(raw) - 1)
    # Un arranque/frenado momentáneo entre dos paros (ruido cerca de 0) forma parte del paro.
    for i in range(1, len(raw) - 1):
        if (raw[i].state not in (STOPPED, ASSUMED) and raw[i].duration < blip_s
                and raw[i - 1].state == STOPPED and raw[i + 1].state == STOPPED):
            raw[i].state = STOPPED
    merged: list[Interval] = []
    remap: list[int] = []
    for iv in raw:
        if merged and merged[-1].state == iv.state and abs(merged[-1].end - iv.start) < 1e-6:
            merged[-1].end = iv.end
        else:
            merged.append(Interval(iv.state, iv.start, iv.end))
        remap.append(len(merged) - 1)
    row_iv = [remap[k] for k in row_iv]
    raw = merged
    for iv in raw:
        if iv.state == STOPPED and iv.duration < microstop_s:
            iv.state = MICROSTOP
    res.intervals = raw
    for iv in raw:
        d, n = res.distribution.get(iv.state, (0.0, 0))
        res.distribution[iv.state] = (d + iv.duration, n + 1)

    run_speed = run_nominal = 0.0
    speed_time = normal_time = known_time = 0.0
    for s, k in zip(rows, row_iv):
        state = raw[k].state
        if state == STOPPED and s.state != STOPPED:
            s = OeeSample(s.ts, s.dt, STOPPED, 0.0, s.nominal, s.good, s.overall)
        if state == UNKNOWN:
            res.unknown_s += s.dt
            continue
        known_time += s.dt
        if s.overall < 2:
            normal_time += s.dt
        if state == STOPPED:
            res.stop_s += s.dt
            continue
        res.run_s += s.dt
        speed = s.speed or 0.0
        length = max(speed, 0.0) * length_factor * s.dt / 60.0
        res.length_total += length
        if s.good:
            res.length_good += length
        if s.nominal:
            run_speed += speed * s.dt
            run_nominal += s.nominal * s.dt
            speed_time += s.dt
    res.planned_s = res.run_s + res.stop_s
    res.n_stops = sum(1 for iv in raw if iv.state == STOPPED)
    res.n_microstops = sum(1 for iv in raw if iv.state == MICROSTOP)
    if res.planned_s > 0:
        res.availability = res.run_s / res.planned_s
    if run_nominal > 0:
        res.performance = run_speed / run_nominal
        res.avg_speed, res.avg_nominal = run_speed / speed_time, run_nominal / speed_time
    if res.length_total > 0:
        res.quality = res.length_good / res.length_total
    if None not in (res.availability, res.performance, res.quality):
        res.oee = res.availability * min(res.performance, 1.0) * res.quality
        calendar = end - start
        res.teep = res.oee * res.planned_s / calendar if calendar > 0 else None
    if res.n_stops:
        res.mtbf_s = res.run_s / res.n_stops
        res.mttr_s = res.stop_s / res.n_stops
    elif res.run_s > 0:
        res.mtbf_s = res.run_s
    if known_time > 0:
        res.normal_pct = 100 * normal_time / known_time
    return res


def sparkline(samples: list[OeeSample], start: float, end: float, microstop_s: float,
              length_factor: float, buckets: int = 12) -> dict[str, list[Optional[float]]]:
    """Evolución de cada KPI en `buckets` subperiodos (para las minigráficas)."""
    edges = np.linspace(start, end, buckets + 1)
    out: dict[str, list[Optional[float]]] = {"oee": [], "availability": [], "performance": [], "quality": []}
    for a, b in zip(edges[:-1], edges[1:]):
        r = compute(samples, a, b, microstop_s, length_factor)
        for k in out:
            out[k].append(getattr(r, k))
    return out


@dataclass
class HumanFactors:
    """Indicadores de Industria 5.0 (centrado en las personas, resiliencia, sostenibilidad)."""
    alarms_per_hour: float = 0.0
    interventions_per_hour: float = 0.0
    mean_recovery_s: Optional[float] = None
    human_score: float = 100.0  # carga de alarmas manejable según ISA-18.2
    resilience_score: Optional[float] = None
    sustainability_score: Optional[float] = None
    index: Optional[float] = None


def alarm_load_score(per_hour: float) -> float:
    """ISA-18.2: ≤6 alarmas/h manejable (100), 12/h exigente (50), ≥30/h sobrecarga (0)."""
    if per_hour <= 6:
        return 100.0
    if per_hour <= 12:
        return 100 - (per_hour - 6) / 6 * 50
    return max(0.0, 50 - (per_hour - 12) / 18 * 50)


def human_factors(events: list[tuple], oee: OeeResult) -> HumanFactors:
    """`events`: filas (ts, kind, level, rule, var, message, recipe) del historial."""
    hours = max((oee.end - oee.start) / 3600.0, 1e-6)
    hf = HumanFactors()
    raised = [e for e in events if e[1] == "raised" and e[2] >= 2]
    hf.alarms_per_hour = len(raised) / hours
    hf.interventions_per_hour = sum(1 for e in events if e[1] == "setpoint_change") / hours
    open_: dict[tuple[str, str], float] = {}
    recov = []
    for ts, kind, level, rule, var, *_ in sorted(events, key=lambda e: e[0]):
        key = (rule, var)
        if kind == "raised" and level >= 2:
            open_[key] = ts
        elif kind == "cleared" and key in open_:
            recov.append(ts - open_.pop(key))
    if recov:
        hf.mean_recovery_s = float(np.mean(recov))
    hf.human_score = alarm_load_score(hf.alarms_per_hour)
    hf.resilience_score = oee.normal_pct
    if oee.quality is not None:
        idle = oee.stop_s / oee.planned_s if oee.planned_s else 0.0
        hf.sustainability_score = 100 * oee.quality * (1 - 0.5 * idle)
    parts = [x for x in (hf.human_score, hf.resilience_score, hf.sustainability_score) if x is not None]
    hf.index = float(np.mean(parts)) if parts else None
    return hf
