"""Estadística de proceso: alineación de series, capacidad, cartas de control y correlación."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

D2 = 1.128


def align(series: dict[str, tuple[np.ndarray, np.ndarray]], step_s: float, max_gap_s: float,
          start: Optional[float] = None, end: Optional[float] = None) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Lleva varias series (t, y) a una rejilla común (último valor conocido, sin exceder `max_gap_s`).

    Devuelve (t_rejilla, matriz filas×variables, nombres) sin filas con huecos. Así se pueden
    comparar variables leídas en instantes distintos (p. ej. pestañas del recorrido).
    """
    names = [k for k, (t, _) in series.items() if len(t)]
    if not names:
        return np.empty(0), np.empty((0, 0)), []
    t0 = start if start is not None else max(series[k][0][0] for k in names)
    t1 = end if end is not None else min(series[k][0][-1] for k in names)
    if t1 <= t0:
        return np.empty(0), np.empty((0, len(names))), names
    grid = np.arange(t0, t1 + 1e-9, step_s)
    cols = []
    for k in names:
        t, y = series[k]
        idx = np.searchsorted(t, grid, side="right") - 1
        col = np.full(len(grid), np.nan)
        ok = idx >= 0
        col[ok] = y[idx[ok]]
        age = np.full(len(grid), np.inf)
        age[ok] = grid[ok] - t[idx[ok]]
        col[age > max_gap_s] = np.nan
        cols.append(col)
    m = np.column_stack(cols)
    keep = ~np.isnan(m).any(axis=1)
    return grid[keep], m[keep], names


@dataclass
class Capability:
    n: int
    mean: float
    std_overall: float
    std_within: float  # corto plazo, rango móvil
    minimum: float
    maximum: float
    lsl: Optional[float] = None
    usl: Optional[float] = None
    cp: Optional[float] = None
    cpk: Optional[float] = None
    pp: Optional[float] = None
    ppk: Optional[float] = None
    pct_out: Optional[float] = None  # % estimado fuera de límites (normal, largo plazo)


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def capability(y: np.ndarray, lsl: Optional[float], usl: Optional[float]) -> Optional[Capability]:
    y = np.asarray(y, float)
    if len(y) < 5:
        return None
    mean = float(y.mean())
    s_all = float(y.std(ddof=1))
    mr = np.abs(np.diff(y))
    s_within = float(mr.mean()) / D2 if len(mr) else 0.0
    c = Capability(n=len(y), mean=mean, std_overall=s_all, std_within=s_within,
                   minimum=float(y.min()), maximum=float(y.max()), lsl=lsl, usl=usl)

    def idx(s: float, two: bool) -> Optional[float]:
        if s <= 0:
            return None
        if two and lsl is not None and usl is not None:
            return (usl - lsl) / (6 * s)
        parts = []
        if usl is not None:
            parts.append((usl - mean) / (3 * s))
        if lsl is not None:
            parts.append((mean - lsl) / (3 * s))
        return min(parts) if parts else None

    c.cp, c.pp = idx(s_within, True), idx(s_all, True)
    c.cpk, c.ppk = idx(s_within, False), idx(s_all, False)
    if s_all > 0 and (lsl is not None or usl is not None):
        p = 0.0
        if usl is not None:
            p += 1 - _norm_cdf((usl - mean) / s_all)
        if lsl is not None:
            p += _norm_cdf((lsl - mean) / s_all)
        c.pct_out = 100 * p
    return c


@dataclass
class XbarChart:
    t: np.ndarray  # instante central de cada subgrupo
    means: np.ndarray
    center: float
    ucl: float
    lcl: float
    out: np.ndarray  # índices fuera de control


def xbar_chart(t: np.ndarray, y: np.ndarray, subgroup_s: float) -> Optional[XbarChart]:
    """Carta X̄ por subgrupos de tiempo; límites a ±3σ estimada con el rango móvil de las medias."""
    if len(y) < 10:
        return None
    b = np.floor((t - t[0]) / subgroup_s).astype(int)
    groups = [g for g in np.unique(b) if (b == g).sum() >= 1]
    tm = np.array([t[b == g].mean() for g in groups])
    m = np.array([y[b == g].mean() for g in groups])
    if len(m) < 4:
        return None
    center = float(m.mean())
    sigma = float(np.abs(np.diff(m)).mean()) / D2
    ucl, lcl = center + 3 * sigma, center - 3 * sigma
    out = np.where((m > ucl) | (m < lcl))[0] if sigma > 0 else np.array([], int)
    return XbarChart(tm, m, center, ucl, lcl, out)


def correlation(m: np.ndarray) -> np.ndarray:
    """Matriz de correlación de Pearson; columnas constantes quedan en 0 (sin información)."""
    if m.shape[0] < 3:
        return np.full((m.shape[1], m.shape[1]), np.nan)
    std = m.std(axis=0)
    z = np.zeros_like(m)
    nz = std > 0
    z[:, nz] = (m[:, nz] - m[:, nz].mean(axis=0)) / std[nz]
    r = (z.T @ z) / m.shape[0]
    np.fill_diagonal(r, 1.0)
    return np.clip(r, -1, 1)


def linear_fit(x: np.ndarray, y: np.ndarray) -> Optional[tuple[float, float, float]]:
    """(pendiente, ordenada, R²)."""
    if len(x) < 3 or float(np.ptp(x)) == 0:
        return None
    b, a = np.polyfit(x, y, 1)
    pred = a + b * x
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return float(b), float(a), r2


def projection(t: np.ndarray, y: np.ndarray, horizon_s: float, fit_s: float) -> Optional[dict]:
    """Proyección lineal con banda de predicción (±2σ del residuo) usando los últimos `fit_s` segundos."""
    if len(t) < 8:
        return None
    sel = t >= t[-1] - fit_s
    tt, yy = t[sel], y[sel]
    if len(tt) < 8 or float(np.ptp(tt)) == 0:
        return None
    b, a = np.polyfit(tt - tt[-1], yy, 1)
    resid = yy - (a + b * (tt - tt[-1]))
    s = float(resid.std(ddof=2)) if len(resid) > 2 else 0.0
    tf = np.linspace(0, horizon_s, 20)
    yf = a + b * tf
    return {"t": tt[-1] + tf, "y": yf, "lo": yf - 2 * s, "hi": yf + 2 * s, "slope_s": float(b)}
