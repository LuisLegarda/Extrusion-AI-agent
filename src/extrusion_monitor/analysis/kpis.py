"""Indicadores generales de la línea (OEE, índice 5.0, estabilidad, Cpk, conformidad, lectura).

El motor los calcula cada `KPI_EVERY_S` y los guarda en el historial como muestras con id `kpi:<clave>`,
para poder graficarlos en el tiempo (tablero de Inicio y dashboard global).
"""
from __future__ import annotations

from typing import Optional

from .oee import OeeSample, compute, human_factors, shift_start
from .rules import Level

KPI_EVERY_S = 30.0
STABILITY_WINDOW_S = 1800.0
KPI_PREFIX = "kpi:"

# clave -> (título, unidad, (umbral rojo, umbral verde), (mín, máx), decimales)
KPIS: dict[str, tuple[str, str, tuple[float, float], tuple[float, float], int]] = {
    "oee": ("OEE (turno)", "%", (60, 85), (0, 100), 1),
    "availability": ("Disponibilidad (turno)", "%", (70, 90), (0, 100), 1),
    "performance": ("Rendimiento (turno)", "%", (70, 95), (0, 100), 1),
    "quality": ("Calidad (turno)", "%", (90, 99), (0, 100), 1),
    "i5": ("Índice 5.0", "/ 100", (60, 80), (0, 100), 0),
    "stability": ("Estabilidad", "%", (80, 95), (0, 100), 0),
    "cpk": ("Cpk mínimo (proceso)", "Cpk", (1.0, 1.33), (0, 2), 2),
    "conform": ("En especificación", "%", (90, 99), (0, 100), 0),
    "read": ("Calidad de lectura", "%", (90, 98), (0, 100), 0),
}


def kpi_var(key: str) -> str:
    return KPI_PREFIX + key


def snapshot_kpis(engine, snap) -> dict[str, Optional[float]]:
    """Indicadores que salen del ciclo actual (sin historial)."""
    cfg = engine.config
    out: dict[str, Optional[float]] = {}
    speed = cfg.oee.speed_var if cfg.oee.enabled else None
    cpks = [st.trend.cpk for vid, st in snap.statuses.items()
            if vid != speed and st.var.measured and st.trend is not None and st.trend.cpk is not None]
    out["cpk"] = min(cpks) if cpks else None
    checked = [st for st in snap.statuses.values() if st.fresh and st.level is not None
               and (st.bounds.any or st.expected)]
    out["conform"] = 100.0 * sum(st.level < Level.WARN for st in checked) / len(checked) if checked else None
    out["read"] = 100.0 * snap.read_ok / snap.read_total if snap.read_total else None
    out["stability"] = stability(engine, snap.ts)[0]
    return out


def stability(engine, now: float) -> tuple[Optional[float], Optional[str], int]:
    """% del tiempo normal del peor comportamiento entrenado (últimos 30 min), su nombre y cuántos hay."""
    mons = engine.behaviors
    scores = []
    for m in mons.active(engine.state.recipe):
        h = [x for x in mons.history.get(m.id, ()) if x[0] >= now - STABILITY_WINDOW_S]
        if h:
            scores.append((100.0 * sum(d2 <= thr for _, d2, thr in h) / len(h), m.name))
    if not scores:
        return None, None, 0
    worst = min(scores)
    return worst[0], worst[1], len(scores)


def shift_oee(engine, now: float):
    """OEE del turno en curso (None si el OEE no está configurado)."""
    o = engine.config.oee
    speed_var = engine.config.variable(o.speed_var) if o.speed_var else None
    if not (o.enabled and speed_var and engine.historian):
        return None
    a = shift_start(now, o.shift_starts)
    rows = engine.historian.oee_samples(a, now)
    samples = [OeeSample(r[0], r[1], r[2], r[3], r[4], None if r[5] is None else bool(r[5]), r[6] or 0)
               for r in rows]
    return compute(samples, a, now, o.microstop_s, o.length_factor)


def all_kpis(engine, snap, now: float) -> tuple[dict[str, Optional[float]], object]:
    """Todos los indicadores (en % salvo Cpk) y el resultado de OEE del turno."""
    out = snapshot_kpis(engine, snap)
    res = shift_oee(engine, now)
    for k in ("oee", "availability", "performance", "quality"):
        v = getattr(res, k, None) if res is not None else None
        out[k] = None if v is None else 100.0 * v
    out["i5"] = None
    if res is not None:
        try:
            out["i5"] = human_factors(engine.historian.events_between(res.start, now), res).index
        except Exception:
            out["i5"] = None
    return out, res
