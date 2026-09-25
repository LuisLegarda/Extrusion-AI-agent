"""Tendencias en tiempo real y control estadístico (SPC) por variable."""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

D2 = 1.128  # constante para estimar sigma a partir del rango móvil (n=2)


@dataclass
class TrendStats:
    n: int
    span_s: float  # duración cubierta por los datos
    mean: float
    std: float
    minimum: float
    maximum: float
    slope_per_min: float  # unidades por minuto
    slope_significant: bool
    eta_to_alarm_min: Optional[float] = None  # minutos estimados hasta el límite de alarma
    cpk: Optional[float] = None
    nelson: list[str] = field(default_factory=list)


class TrendTracker:
    def __init__(self, window_s: float, subgroup_s: float):
        self.window_s = window_s
        self.subgroup_s = subgroup_s
        self._data: dict[str, deque[tuple[float, float]]] = {}

    def add(self, var_id: str, ts: float, value: float) -> None:
        dq = self._data.setdefault(var_id, deque())
        if dq and dq[-1][0] >= ts:
            return  # mismo valor aceptado; no se duplica
        dq.append((ts, value))
        while dq and dq[0][0] < ts - self.window_s:
            dq.popleft()

    def series(self, var_id: str) -> tuple[np.ndarray, np.ndarray]:
        dq = self._data.get(var_id)
        if not dq:
            return np.empty(0), np.empty(0)
        arr = np.asarray(dq, dtype=float)
        return arr[:, 0], arr[:, 1]

    def clear(self) -> None:
        self._data.clear()

    def stats(self, var_id: str, now: float, center: Optional[float] = None,
              lo_limit: Optional[float] = None, hi_limit: Optional[float] = None,
              min_effect: float = 0.0) -> Optional[TrendStats]:
        """`min_effect`: magnitud mínima (en unidades) para que una regla SPC se considere relevante."""
        t, y = self.series(var_id)
        if len(y) < 5:
            return None
        mean, std = float(y.mean()), float(y.std(ddof=1))
        slope_s, significant = _slope(t, y)
        slope_min = slope_s * 60.0
        st = TrendStats(n=len(y), span_s=float(t[-1] - t[0]), mean=mean, std=std, minimum=float(y.min()), maximum=float(y.max()),
                        slope_per_min=slope_min, slope_significant=significant)

        if significant and slope_s != 0:
            last = float(y[-3:].mean())
            target = hi_limit if slope_s > 0 else lo_limit
            if target is not None:
                eta = (target - last) / slope_min
                if eta >= 0:
                    st.eta_to_alarm_min = eta

        if lo_limit is not None and hi_limit is not None and std > 0:
            st.cpk = min(hi_limit - mean, mean - lo_limit) / (3 * std)

        st.nelson = _nelson(t, y, now, self.subgroup_s, center, min_effect)
        return st


def _slope(t: np.ndarray, y: np.ndarray) -> tuple[float, bool]:
    """Pendiente por mínimos cuadrados y si es estadísticamente significativa (|t| > 3)."""
    tc = t - t.mean()
    sxx = float(tc @ tc)
    if sxx <= 0:
        return 0.0, False
    slope = float(tc @ (y - y.mean())) / sxx
    resid = y - (y.mean() + slope * tc)
    dof = len(y) - 2
    if dof <= 0:
        return slope, False
    se = math.sqrt(float(resid @ resid) / dof / sxx)
    if se == 0:
        return slope, slope != 0
    return slope, abs(slope / se) > 3.0


def _nelson(t: np.ndarray, y: np.ndarray, now: float, subgroup_s: float,
            center: Optional[float], min_effect: float = 0.0) -> list[str]:
    """Reglas de Nelson sobre medias de subgrupos completos.

    Se exige además un efecto mínimo para no alertar de variaciones estadísticamente
    detectables pero irrelevantes frente a la tolerancia del proceso.
    """
    buckets = np.floor((t - t[0]) / subgroup_s).astype(int)
    current = int(np.floor((now - t[0]) / subgroup_s))
    means = [float(y[buckets == b].mean()) for b in np.unique(buckets) if b < current]
    out: list[str] = []
    if len(means) < 3:
        return out
    m = np.asarray(means)
    mr = np.abs(np.diff(m))
    sigma = float(mr.mean()) / D2 if len(mr) else 0.0
    if sigma > 0 and len(m) >= 5:
        own_center = float(m[:-1].mean())
        if abs(m[-1] - own_center) > max(3 * sigma, min_effect):
            out.append("punto atípico (>3σ)")
    ref = center if center is not None else float(m.mean())
    if len(m) >= 9:
        tail = m[-9:] - ref
        if (np.all(tail > 0) or np.all(tail < 0)) and abs(tail.mean()) >= min_effect * 0.5:
            out.append("9 subgrupos del mismo lado de la referencia")
    if len(m) >= 7:
        d = np.diff(m[-7:])
        rise = abs(m[-1] - m[-7])
        if np.all(d > 0) and rise >= min_effect * 0.5:
            out.append("6 subgrupos en aumento")
        elif np.all(d < 0) and rise >= min_effect * 0.5:
            out.append("6 subgrupos en descenso")
    return out
