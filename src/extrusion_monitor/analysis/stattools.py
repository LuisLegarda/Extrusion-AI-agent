"""Herramientas estadísticas para el análisis (solo numpy; sin dependencias pesadas).

Distribuciones (normal, t, F), estadística descriptiva, normalidad (Anderson-Darling), capacidad (Cp, Cpk, Pp,
Ppk, Cpm, PPM), cartas de control (I-MR y X̄-R), comparación de grupos (t de Welch y ANOVA de un factor),
regresión lineal múltiple (con términos cuadráticos e interacciones) con predicción e intervalos, y Pareto.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

# --- distribuciones ----------------------------------------------------------------------------------


def norm_cdf(x):
    x = np.asarray(x, float)
    return 0.5 * (1.0 + np.vectorize(math.erf, otypes=[float])(x / math.sqrt(2.0))) if x.ndim else \
        0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Inversa de la normal estándar (Acklam, error < 1.2e-9)."""
    if not 0.0 < p < 1.0:
        return -math.inf if p <= 0 else math.inf
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00)
    lo = 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - lo:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def _betacf(a: float, b: float, x: float) -> float:
    tiny, eps = 1e-300, 3e-14
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        dl = d * c
        h *= dl
        if abs(dl - 1.0) < eps:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Beta incompleta regularizada I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    bt = math.exp(lbt)
    if x < (a + 1) / (a + b + 2):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1 - x) / b


def t_sf2(t: float, df: float) -> float:
    """p de dos colas para t con df grados de libertad."""
    if not np.isfinite(t):
        return 0.0
    return betainc(df / 2.0, 0.5, df / (df + t * t))


def t_ppf(q: float, df: float) -> float:
    """Cuantil de t (q en (0, 1)), por bisección."""
    if q == 0.5:
        return 0.0
    sign = 1.0 if q > 0.5 else -1.0
    target = 2 * (1 - q) if q > 0.5 else 2 * q  # p de dos colas
    lo, hi = 0.0, 1e3
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_sf2(mid, df) > target:
            lo = mid
        else:
            hi = mid
    return sign * (lo + hi) / 2


def f_sf(f: float, d1: float, d2: float) -> float:
    """P(F > f)."""
    if f <= 0:
        return 1.0
    return betainc(d2 / 2.0, d1 / 2.0, d2 / (d2 + d1 * f))


# --- descriptiva ------------------------------------------------------------------------------------


def clean(y) -> np.ndarray:
    y = np.asarray(y, float)
    return y[np.isfinite(y)]


def describe(y) -> dict:
    """Estadística descriptiva completa de una muestra."""
    y = clean(y)
    n = len(y)
    if n == 0:
        return {"n": 0}
    mean = float(y.mean())
    sd = float(y.std(ddof=1)) if n > 1 else 0.0
    q1, med, q3 = (float(v) for v in np.percentile(y, [25, 50, 75]))
    ss = float(((y - mean) ** 2).sum())
    out = {"n": n, "mean": mean, "sd": sd, "var": sd * sd, "se": sd / math.sqrt(n) if n else 0.0,
           "min": float(y.min()), "q1": q1, "median": med, "q3": q3, "max": float(y.max()),
           "range": float(y.max() - y.min()), "iqr": q3 - q1, "sum": float(y.sum()), "ss": ss,
           "uss": float((y * y).sum()), "cv": 100 * sd / mean if mean else None}
    if n > 2 and sd > 0:
        z = (y - mean) / sd
        out["skew"] = float(n / ((n - 1) * (n - 2)) * (z ** 3).sum())
        if n > 3:
            out["kurt"] = float(n * (n + 1) / ((n - 1) * (n - 2) * (n - 3)) * (z ** 4).sum()
                                - 3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))
    return out


DESCRIBE_LABELS = [("n", "N"), ("mean", "Media"), ("sd", "Desv. estándar"), ("var", "Varianza"),
                   ("se", "Error estándar de la media"), ("cv", "Coef. de variación (%)"), ("min", "Mínimo"),
                   ("q1", "Q1"), ("median", "Mediana"), ("q3", "Q3"), ("max", "Máximo"), ("range", "Rango"),
                   ("iqr", "Rango intercuartil"), ("sum", "Suma"), ("ss", "Suma de cuadrados (corregida)"),
                   ("uss", "Suma de cuadrados (sin corregir)"), ("skew", "Asimetría"), ("kurt", "Curtosis")]


# --- normalidad -------------------------------------------------------------------------------------


@dataclass
class Normality:
    n: int
    a2: float  # Anderson-Darling
    a2_star: float
    p: float
    mean: float
    sd: float
    x: np.ndarray  # datos ordenados
    z: np.ndarray  # cuantiles normales teóricos

    @property
    def normal(self) -> bool:
        return self.p >= 0.05


def anderson_darling(y) -> Optional[Normality]:
    y = np.sort(clean(y))
    n = len(y)
    if n < 8:
        return None
    mean, sd = float(y.mean()), float(y.std(ddof=1))
    if sd <= 0:
        return None
    cdf = np.clip(norm_cdf((y - mean) / sd), 1e-15, 1 - 1e-15)
    i = np.arange(1, n + 1)
    a2 = float(-n - np.sum((2 * i - 1) * (np.log(cdf) + np.log(1 - cdf[::-1]))) / n)
    a2s = a2 * (1 + 0.75 / n + 2.25 / n ** 2)
    if a2s >= 0.6:
        p = math.exp(1.2937 - 5.709 * a2s + 0.0186 * a2s ** 2)
    elif a2s >= 0.34:
        p = math.exp(0.9177 - 4.279 * a2s - 1.38 * a2s ** 2)
    elif a2s >= 0.2:
        p = 1 - math.exp(-8.318 + 42.796 * a2s - 59.938 * a2s ** 2)
    else:
        p = 1 - math.exp(-13.436 + 101.14 * a2s - 223.73 * a2s ** 2)
    z = np.array([norm_ppf((k - 0.375) / (n + 0.25)) for k in i])  # posiciones de Blom
    return Normality(n, a2, a2s, max(0.0, min(1.0, p)), mean, sd, y, z)


# --- capacidad --------------------------------------------------------------------------------------


def sigma_within(y) -> float:
    """σ de corto plazo por rango móvil promedio (MR̄ / d2, d2 = 1.128)."""
    y = clean(y)
    if len(y) < 2:
        return 0.0
    return float(np.abs(np.diff(y)).mean() / 1.128)


@dataclass
class CapabilityReport:
    n: int
    mean: float
    sd_within: float
    sd_overall: float
    lsl: Optional[float]
    usl: Optional[float]
    target: Optional[float]
    cp: Optional[float] = None
    cpl: Optional[float] = None
    cpu: Optional[float] = None
    cpk: Optional[float] = None
    pp: Optional[float] = None
    ppl: Optional[float] = None
    ppu: Optional[float] = None
    ppk: Optional[float] = None
    cpm: Optional[float] = None
    ppm_obs: float = 0.0
    ppm_within: float = 0.0
    ppm_overall: float = 0.0
    z_bench: Optional[float] = None


def capability_report(y, lsl: Optional[float], usl: Optional[float],
                      target: Optional[float] = None) -> Optional[CapabilityReport]:
    y = clean(y)
    n = len(y)
    if n < 5 or (lsl is None and usl is None):
        return None
    mean = float(y.mean())
    sw, so = sigma_within(y), float(y.std(ddof=1))
    r = CapabilityReport(n, mean, sw, so, lsl, usl, target)

    def idx(s):
        lo = (mean - lsl) / (3 * s) if lsl is not None and s > 0 else None
        hi = (usl - mean) / (3 * s) if usl is not None and s > 0 else None
        both = (usl - lsl) / (6 * s) if lsl is not None and usl is not None and s > 0 else None
        k = min(v for v in (lo, hi) if v is not None) if (lo is not None or hi is not None) else None
        return both, lo, hi, k

    r.cp, r.cpl, r.cpu, r.cpk = idx(sw)
    r.pp, r.ppl, r.ppu, r.ppk = idx(so)
    if lsl is not None and usl is not None and so > 0:
        t = target if target is not None else (lsl + usl) / 2
        r.cpm = (usl - lsl) / (6 * math.sqrt(so ** 2 + (mean - t) ** 2))
    out = ((y < lsl).sum() if lsl is not None else 0) + ((y > usl).sum() if usl is not None else 0)
    r.ppm_obs = 1e6 * float(out) / n

    def ppm(s):
        if s <= 0:
            return 0.0
        p = (norm_cdf((lsl - mean) / s) if lsl is not None else 0.0) + \
            (1 - norm_cdf((usl - mean) / s) if usl is not None else 0.0)
        return 1e6 * float(p)

    r.ppm_within, r.ppm_overall = ppm(sw), ppm(so)
    p_out = r.ppm_overall / 1e6
    r.z_bench = norm_ppf(1 - p_out) if 0 < p_out < 1 else None
    return r


# --- cartas de control ------------------------------------------------------------------------------

# n: (A2, D3, D4, d2)
XBAR_R = {2: (1.880, 0, 3.267, 1.128), 3: (1.023, 0, 2.574, 1.693), 4: (0.729, 0, 2.282, 2.059),
          5: (0.577, 0, 2.114, 2.326), 6: (0.483, 0, 2.004, 2.534), 7: (0.419, 0.076, 1.924, 2.704),
          8: (0.373, 0.136, 1.864, 2.847), 9: (0.337, 0.184, 1.816, 2.970), 10: (0.308, 0.223, 1.777, 3.078)}


@dataclass
class ControlChart:
    values: np.ndarray
    center: float
    ucl: float
    lcl: float
    out: np.ndarray = field(default_factory=lambda: np.empty(0, int))  # puntos fuera de control (índices)
    runs: np.ndarray = field(default_factory=lambda: np.empty(0, int))  # 9 seguidos de un lado
    label: str = ""


def _flags(v: np.ndarray, center: float, ucl: float, lcl: float) -> tuple[np.ndarray, np.ndarray]:
    out = np.where((v > ucl) | (v < lcl))[0]
    side = np.sign(v - center)
    runs = []
    count = 0
    for i in range(len(v)):
        count = count + 1 if i and side[i] == side[i - 1] and side[i] != 0 else 1
        if count >= 9:
            runs.append(i)
    return out, np.array(runs, int)


def imr_charts(y) -> Optional[tuple[ControlChart, ControlChart]]:
    y = clean(y)
    if len(y) < 3:
        return None
    mr = np.abs(np.diff(y))
    mrbar = float(mr.mean())
    c = float(y.mean())
    sigma = mrbar / 1.128
    i_chart = ControlChart(y, c, c + 3 * sigma, c - 3 * sigma, label="I")
    i_chart.out, i_chart.runs = _flags(y, c, i_chart.ucl, i_chart.lcl)
    mr_chart = ControlChart(mr, mrbar, 3.267 * mrbar, 0.0, label="MR")
    mr_chart.out, _ = _flags(mr, mrbar, mr_chart.ucl, -1.0)
    return i_chart, mr_chart


def xbar_r_charts(y, n: int) -> Optional[tuple[ControlChart, ControlChart]]:
    y = clean(y)
    n = max(2, min(10, int(n)))
    k = len(y) // n
    if k < 2:
        return None
    g = y[:k * n].reshape(k, n)
    means, ranges = g.mean(axis=1), g.max(axis=1) - g.min(axis=1)
    a2, d3, d4, _d2 = XBAR_R[n]
    xbb, rbar = float(means.mean()), float(ranges.mean())
    xc = ControlChart(means, xbb, xbb + a2 * rbar, xbb - a2 * rbar, label="X̄")
    xc.out, xc.runs = _flags(means, xbb, xc.ucl, xc.lcl)
    rc = ControlChart(ranges, rbar, d4 * rbar, d3 * rbar, label="R")
    rc.out, _ = _flags(ranges, rbar, rc.ucl, rc.lcl)
    return xc, rc


# --- comparación de grupos --------------------------------------------------------------------------


@dataclass
class GroupStat:
    name: str
    n: int
    mean: float
    sd: float
    ci_lo: float
    ci_hi: float


def group_stats(groups: dict[str, np.ndarray], conf: float = 0.95) -> list[GroupStat]:
    out = []
    for name, y in groups.items():
        y = clean(y)
        n = len(y)
        if n == 0:
            continue
        m = float(y.mean())
        sd = float(y.std(ddof=1)) if n > 1 else 0.0
        h = t_ppf(0.5 + conf / 2, n - 1) * sd / math.sqrt(n) if n > 1 else 0.0
        out.append(GroupStat(name, n, m, sd, m - h, m + h))
    return out


@dataclass
class Anova:
    k: int
    n: int
    ss_between: float
    ss_within: float
    df_between: int
    df_within: int
    f: float
    p: float
    r2: float

    @property
    def ms_between(self) -> float:
        return self.ss_between / self.df_between if self.df_between else 0.0

    @property
    def ms_within(self) -> float:
        return self.ss_within / self.df_within if self.df_within else 0.0


def anova_oneway(groups: dict[str, np.ndarray]) -> Optional[Anova]:
    gs = [clean(g) for g in groups.values()]
    gs = [g for g in gs if len(g)]
    k = len(gs)
    n = sum(len(g) for g in gs)
    if k < 2 or n <= k:
        return None
    grand = float(np.concatenate(gs).mean())
    ssb = float(sum(len(g) * (g.mean() - grand) ** 2 for g in gs))
    ssw = float(sum(((g - g.mean()) ** 2).sum() for g in gs))
    dfb, dfw = k - 1, n - k
    f = (ssb / dfb) / (ssw / dfw) if ssw > 0 else math.inf
    return Anova(k, n, ssb, ssw, dfb, dfw, f, f_sf(f, dfb, dfw) if np.isfinite(f) else 0.0,
                 ssb / (ssb + ssw) if ssb + ssw > 0 else 0.0)


@dataclass
class TTest:
    t: float
    df: float
    p: float
    diff: float
    ci_lo: float
    ci_hi: float


def welch_t(a, b, conf: float = 0.95) -> Optional[TTest]:
    a, b = clean(a), clean(b)
    if len(a) < 2 or len(b) < 2:
        return None
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    se = math.sqrt(va + vb)
    diff = float(a.mean() - b.mean())
    if se == 0:
        return TTest(math.inf if diff else 0.0, len(a) + len(b) - 2, 0.0 if diff else 1.0, diff, diff, diff)
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
    t = diff / se
    h = t_ppf(0.5 + conf / 2, df) * se
    return TTest(float(t), float(df), t_sf2(t, df), diff, diff - h, diff + h)


# --- regresión --------------------------------------------------------------------------------------


@dataclass
class Regression:
    terms: list[str]
    coef: np.ndarray
    se: np.ndarray
    t: np.ndarray
    p: np.ndarray
    r2: float
    r2_adj: float
    s: float
    n: int
    df_resid: int
    f: float
    p_model: float
    xtx_inv: np.ndarray
    predictors: list[str]
    quadratic: bool
    interactions: bool
    x_min: np.ndarray
    x_max: np.ndarray
    fitted: np.ndarray
    resid: np.ndarray

    def row(self, x: Sequence[float]) -> np.ndarray:
        return design_row(np.asarray(x, float), self.quadratic, self.interactions)

    def predict(self, x: Sequence[float], conf: float = 0.95) -> tuple[float, float, float, float, float]:
        """(predicción, IC de la media bajo, alto, IP de una observación bajo, alto)."""
        r = self.row(x)
        yhat = float(r @ self.coef)
        tq = t_ppf(0.5 + conf / 2, self.df_resid) if self.df_resid > 0 else 0.0
        h = float(r @ self.xtx_inv @ r)
        ci = tq * self.s * math.sqrt(max(h, 0.0))
        pi = tq * self.s * math.sqrt(1 + max(h, 0.0))
        return yhat, yhat - ci, yhat + ci, yhat - pi, yhat + pi


def design_row(x: np.ndarray, quadratic: bool, interactions: bool) -> np.ndarray:
    cols = [1.0, *x]
    if quadratic:
        cols += [v * v for v in x]
    if interactions:
        cols += [x[i] * x[j] for i in range(len(x)) for j in range(i + 1, len(x))]
    return np.array(cols, float)


def term_names(names: list[str], quadratic: bool, interactions: bool) -> list[str]:
    terms = ["Constante", *names]
    if quadratic:
        terms += [f"{n}²" for n in names]
    if interactions:
        terms += [f"{names[i]} × {names[j]}" for i in range(len(names)) for j in range(i + 1, len(names))]
    return terms


def ols(x: np.ndarray, y: np.ndarray, names: list[str], quadratic: bool = False,
        interactions: bool = False) -> Optional[Regression]:
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if x.ndim == 1:
        x = x[:, None]
    ok = np.isfinite(y) & np.isfinite(x).all(axis=1)
    x, y = x[ok], y[ok]
    design = np.array([design_row(r, quadratic, interactions) for r in x])
    n, p = design.shape
    if n <= p:
        return None
    # columnas escaladas: con términos cuadráticos (p. ej. 350 y 350²) la matriz queda casi singular
    norms = np.linalg.norm(design, axis=0)
    norms[norms == 0] = 1.0
    ds = design / norms
    try:
        sol, *_ = np.linalg.lstsq(ds, y, rcond=None)
        inv_s = np.linalg.pinv(ds.T @ ds)
    except np.linalg.LinAlgError:
        return None
    coef = sol / norms
    xtx_inv = inv_s / np.outer(norms, norms)
    fitted = design @ coef
    resid = y - fitted
    sse = float(resid @ resid)
    sst = float(((y - y.mean()) ** 2).sum())
    dfr = n - p
    mse = sse / dfr
    s = math.sqrt(mse)
    se = np.sqrt(np.maximum(np.diag(xtx_inv) * mse, 0))
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(se > 0, coef / se, np.inf)
    pv = np.array([t_sf2(abs(v), dfr) for v in t])
    r2 = 1 - sse / sst if sst > 0 else 0.0
    r2a = 1 - (1 - r2) * (n - 1) / dfr if dfr > 0 else r2
    dfm = p - 1
    f = ((sst - sse) / dfm) / mse if dfm and mse > 0 else math.inf
    return Regression(term_names(names, quadratic, interactions), coef, se, t, pv, r2, r2a, s, n, dfr, f,
                      f_sf(f, dfm, dfr) if np.isfinite(f) and dfm else 0.0, xtx_inv, list(names), quadratic,
                      interactions, x.min(axis=0), x.max(axis=0), fitted, resid)


# --- Pareto -----------------------------------------------------------------------------------------


def pareto(values: dict[str, float], max_bars: int = 12) -> tuple[list[str], np.ndarray, np.ndarray]:
    """(categorías, valores, % acumulado) de mayor a menor; lo que sobra se agrupa en «Otros»."""
    items = sorted(((k, float(v)) for k, v in values.items() if v > 0), key=lambda kv: -kv[1])
    if len(items) > max_bars:
        other = sum(v for _, v in items[max_bars - 1:])
        items = items[:max_bars - 1] + [("Otros", other)]
    names = [k for k, _ in items]
    vals = np.array([v for _, v in items], float)
    cum = 100 * np.cumsum(vals) / vals.sum() if len(vals) and vals.sum() > 0 else np.empty(0)
    return names, vals, cum
