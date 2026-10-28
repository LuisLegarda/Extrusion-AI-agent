"""Analizador de planta (dashboard global): problemas, fallas, tiempos muertos, estabilidad y tendencia por línea.

Junta lo que publican las líneas (indicadores por minuto, eventos, capturas de paros y defectos) en métricas
para ingeniería y gerencia: OEE y sus pérdidas, paros y su costo, MTBF y MTTR, causas principales, estabilidad
y su tendencia, índice 5.0 (factor humano: carga de alarmas), desperdicio, y la comparación con el periodo
anterior. Con eso arma conclusiones ordenadas por importancia.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..i18n import tr

KPI_KEYS = ("oee", "availability", "performance", "quality", "stability", "i5", "cpk", "conform")
RUN_STATES = ("running", "slow", "assumed")
DEFAULT_SHIFTS = ["06:00", "14:00", "22:00"]


@dataclass
class LineMetrics:
    name: str
    minutes: int = 0  # minutos con datos
    kpis: dict = field(default_factory=dict)  # promedio del periodo (en %, salvo Cpk)
    daily: dict = field(default_factory=dict)  # kpi -> [(día, promedio)]
    slope: dict = field(default_factory=dict)  # kpi -> puntos por día
    stop_min: float = 0.0
    planned_min: float = 0.0
    n_stops: int = 0
    mttr_min: Optional[float] = None
    mtbf_h: Optional[float] = None
    causes: dict = field(default_factory=dict)  # causa -> minutos
    scrap: float = 0.0
    alarms: int = 0
    alarms_h: Optional[float] = None
    prev_oee: Optional[float] = None
    prev_stop_min: Optional[float] = None
    cost: float = 0.0  # costo del paro
    scrap_cost: float = 0.0  # costo del desperdicio
    produced: float = 0.0  # producción del periodo (suma por turno)
    good: float = 0.0
    expected: float = 0.0  # meta de producción para el tiempo transcurrido del periodo
    n_shifts: int = 0
    prod_daily: list = field(default_factory=list)  # [(día, producción)]
    run_h: float = 0.0  # horas en marcha
    by_shift: dict = field(default_factory=dict)  # turno -> {oee, minutes, stop_min, scrap}
    by_user: dict = field(default_factory=dict)  # usuario en turno -> {oee, minutes, stop_min, scrap}
    failures: dict = field(default_factory=dict)  # causa -> {n, min, mttr, mtbf}
    targets: object = None  # metas de la línea (PlantSettings.target)

    @property
    def compliance(self) -> Optional[float]:
        return 100.0 * self.produced / self.expected if self.expected > 0 else None

    @property
    def quality_cost(self) -> float:
        return self.cost + self.scrap_cost

    @property
    def main_cause(self) -> Optional[tuple[str, float]]:
        return max(self.causes.items(), key=lambda kv: kv[1]) if self.causes else None

    @property
    def main_loss(self) -> Optional[tuple[str, float]]:
        loss = {k: self.kpis[k] for k in ("availability", "performance", "quality") if self.kpis.get(k) is not None}
        return min(loss.items(), key=lambda kv: kv[1]) if loss else None


@dataclass
class Insight:
    severity: int  # 3 grave · 2 atención · 1 informativo · 0 positivo
    text: str
    line: str = ""


@dataclass
class PlantSummary:
    since: float
    until: float
    lines: list[LineMetrics]
    causes: dict  # causa -> minutos (toda la planta)
    insights: list[Insight]
    unit: str = ""

    @property
    def stop_min(self) -> float:
        return sum(m.stop_min for m in self.lines)

    @property
    def cost(self) -> float:
        return sum(m.cost for m in self.lines)


def _avg(vals: list[float]) -> Optional[float]:
    vals = [v for v in vals if v is not None and math.isfinite(v)]
    return float(np.mean(vals)) if vals else None


def _pct(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    return 100.0 * v if abs(v) <= 1.5 else v  # algunas versiones publican fracciones


def _shift_label(ts: float, starts: list[str]) -> str:
    from .dataset import shift_names
    return str(shift_names(np.array([ts]), (), starts)[0])


def _bucket(d: dict, key: str) -> dict:
    return d.setdefault(key, {"oee_sum": 0.0, "oee_n": 0, "minutes": 0, "stop_min": 0.0, "scrap": 0.0, "stops": 0})


def _finish(d: dict) -> dict:
    for b in d.values():
        b["oee"] = b["oee_sum"] / b["oee_n"] if b["oee_n"] else None
    return d


def line_metrics(name: str, kpi_rows: list, problems: list[dict], events: list[tuple],
                 since: float, until: float, cost_per_h: float = 0.0, cost_scrap: float = 0.0,
                 target_shift: float = 0.0, shift_starts: Optional[list[str]] = None) -> LineMetrics:
    """`kpi_rows`: renglones completos de la tendencia (dict con ts, k, p, s, u) o pares (ts, k)."""
    rows = [r if isinstance(r, dict) else {"ts": r[0], "k": r[1]} for r in kpi_rows]
    kpi_rows = [(r["ts"], r.get("k") or {}) for r in rows]
    starts = shift_starts or DEFAULT_SHIFTS
    m = LineMetrics(name)
    m.minutes = len(kpi_rows)
    # producción por turno (acumulada dentro de cada turno), horas en marcha y turnos / usuarios
    shifts: dict[float, list] = {}
    for r in rows:
        p = r.get("p")
        if p:
            cur = shifts.get(p[0])
            if cur is None or p[1] >= cur[0]:
                shifts[p[0]] = [float(p[1]), float(p[2])]
        if r.get("s") in RUN_STATES:
            m.run_h += min(300.0, max(0.0, r["ts"] - (r.get("from") or r["ts"] - 60))) / 3600
        oee = (r.get("k") or {}).get("oee")
        for d, key in ((m.by_shift, _shift_label(r["ts"], starts)), (m.by_user, r.get("u") or "(sin usuario)")):
            b = _bucket(d, key)
            b["minutes"] += 1
            if oee is not None:
                b["oee_sum"] += _pct(oee)
                b["oee_n"] += 1
    if not any(r.get("s") for r in rows):
        m.run_h = max(0.0, m.minutes / 60)  # monitores anteriores: sin estado de la máquina
    m.n_shifts = len(shifts)
    m.produced = sum(v[0] for v in shifts.values())
    m.good = sum(v[1] for v in shifts.values())
    days: dict[str, float] = {}
    for st, (tot, _g) in shifts.items():
        day = time.strftime("%Y-%m-%d", time.localtime(st))
        days[day] = days.get(day, 0.0) + tot
    m.prod_daily = sorted(days.items())
    if target_shift > 0 and shifts:
        shift_len = 86400 / max(1, len(starts))
        frac = sum(min(1.0, max(0.0, (min(until, st + shift_len) - max(since, st)) / shift_len)) for st in shifts)
        m.expected = target_shift * frac
    for k in KPI_KEYS:
        vals = [r.get(k) for _, r in kpi_rows]
        v = _avg(vals)
        m.kpis[k] = v if k == "cpk" else _pct(v)
        days: dict[str, list] = {}
        for ts, r in kpi_rows:
            if r.get(k) is not None:
                days.setdefault(time.strftime("%Y-%m-%d", time.localtime(ts)), []).append(r[k])
        series = [(d, _avg(vs)) for d, vs in sorted(days.items())]
        series = [(d, v if k == "cpk" else _pct(v)) for d, v in series if v is not None]
        m.daily[k] = series
        if len(series) >= 3:
            m.slope[k] = float(np.polyfit(np.arange(len(series)), [v for _, v in series], 1)[0])
    stops = [r for r in problems if r.get("kind") == "downtime"]
    for r in stops:
        a, b = max(r.get("start") or 0, since), min(r.get("end") or 0, until)
        mins = max(0.0, b - a) / 60
        if r.get("planned"):
            m.planned_min += mins
            continue
        m.stop_min += mins
        m.n_stops += 1
        cause = r.get("reason") or r.get("category") or tr("(sin causa)")
        m.causes[cause] = m.causes.get(cause, 0.0) + mins
        f = m.failures.setdefault(cause, {"n": 0, "min": 0.0})
        f["n"] += 1
        f["min"] += mins
        start = r.get("start") or since
        for d, key in ((m.by_shift, _shift_label(start, starts)), (m.by_user, r.get("operator") or "(sin usuario)")):
            b = _bucket(d, key)
            b["stop_min"] += mins
            b["stops"] += 1
    m.scrap = sum(float(r.get("scrap") or 0) for r in problems)
    for r in problems:
        if r.get("scrap"):
            start = r.get("start") or since
            _bucket(m.by_shift, _shift_label(start, starts))["scrap"] += float(r["scrap"])
            _bucket(m.by_user, r.get("operator") or "(sin usuario)")["scrap"] += float(r["scrap"])
    _finish(m.by_shift)
    _finish(m.by_user)
    if m.n_stops:
        m.mttr_min = m.stop_min / m.n_stops
        run_h = max(0.0, (until - since) / 3600 - (m.stop_min + m.planned_min) / 60)
        m.mtbf_h = run_h / m.n_stops
    m.alarms = sum(1 for e in events if e[2] >= 3 and e[1] in ("raised", "escalated"))
    hours = max(m.minutes / 60, 1e-9)
    m.alarms_h = m.alarms / hours if m.minutes else None
    m.cost = m.stop_min / 60 * cost_per_h
    m.scrap_cost = m.scrap * cost_scrap
    for f in m.failures.values():
        f["mttr"] = f["min"] / f["n"] if f["n"] else None
        f["mtbf"] = m.run_h / f["n"] if f["n"] and m.run_h else None
    return m


def summarize(hist, since: float, until: float, cost_per_h: float = 0.0, plant=None,
              shift_starts: Optional[list[str]] = None) -> PlantSummary:
    """Métricas y conclusiones de las líneas de `hist` (FleetHistorian) en [since, until].

    `plant` (PlantSettings) aporta costos y metas por línea."""
    span = until - since
    if plant is not None:
        cost_per_h = plant.cost_stop_h or cost_per_h
    cost_scrap = plant.cost_scrap_unit if plant is not None else 0.0
    kpis = hist.rows_by_line(since, until) if hasattr(hist, "rows_by_line") else hist.kpis_by_line(since, until)
    prev_kpis = hist.kpis_by_line(since - span, since)
    probs = hist.problems(since, until)
    prev_probs = hist.problems(since - span, since)
    events = hist.events_between(since, until)
    lines = []
    for ln in hist.lines():
        name = ln.name
        tg = plant.target(name) if plant is not None else None
        m = line_metrics(name, kpis.get(name, []), [r for r in probs if r.get("line") == name],
                         [e for e in events if e[7] == name], since, until, cost_per_h, cost_scrap,
                         tg.production_shift if tg else 0.0, shift_starts)
        m.targets = tg
        pm = line_metrics(name, prev_kpis.get(name, []), [r for r in prev_probs if r.get("line") == name], [],
                          since - span, since)
        m.prev_oee = pm.kpis.get("oee")
        m.prev_stop_min = pm.stop_min if pm.minutes or pm.n_stops else None
        lines.append(m)
    causes: dict[str, float] = {}
    for m in lines:
        for c, v in m.causes.items():
            causes[c] = causes.get(c, 0.0) + v
    units = {r.get("unit") for r in probs if r.get("unit")}
    s = PlantSummary(since, until, lines, causes, [], units.pop() if len(units) == 1 else "")
    s.currency = plant.currency if plant is not None else "$"
    s.insights = insights(s)
    return s


LOSS_NAMES = {"availability": "disponibilidad (paros)", "performance": "rendimiento (velocidad)",
              "quality": "calidad (desperdicio)"}


def insights(s: PlantSummary) -> list[Insight]:
    out: list[Insight] = []
    with_data = [m for m in s.lines if m.minutes]
    for m in s.lines:
        if not m.minutes:
            out.append(Insight(2, f"{m.name}: sin datos en el periodo (¿monitor apagado o sin exportar?).", m.name))
    oees = [m for m in with_data if m.kpis.get("oee") is not None]
    if oees:
        worst = min(oees, key=lambda m: m.kpis["oee"])
        best = max(oees, key=lambda m: m.kpis["oee"])
        loss = worst.main_loss
        sev = 3 if worst.kpis["oee"] < 60 else (2 if worst.kpis["oee"] < 75 else 1)
        out.append(Insight(sev, f"{worst.name} tiene el OEE más bajo ({worst.kpis['oee']:.0f} %)"
                                + (f"; su mayor pérdida es la {LOSS_NAMES[loss[0]]}, con {loss[1]:.0f} %." if loss else "."),
                           worst.name))
        if best is not worst:
            out.append(Insight(0, f"{best.name} es la mejor línea del periodo (OEE {best.kpis['oee']:.0f} %): "
                                  "úsala de referencia para las demás.", best.name))
    total = sum(s.causes.values())
    if total > 0:
        cause, mins = max(s.causes.items(), key=lambda kv: kv[1])
        share = 100 * mins / total
        out.append(Insight(3 if share >= 40 else 2, f"«{cause}» causa el {share:.0f} % del tiempo muerto de la planta "
                                                    f"({mins:.0f} min): es la primera causa a atacar."))
    for m in with_data:
        if m.prev_stop_min and m.prev_stop_min > 5 and m.stop_min > 1.3 * m.prev_stop_min:
            out.append(Insight(2, f"{m.name}: el tiempo de paro subió {100 * (m.stop_min / m.prev_stop_min - 1):.0f} % "
                                  f"contra el periodo anterior ({m.prev_stop_min:.0f} → {m.stop_min:.0f} min).", m.name))
        if m.prev_oee is not None and m.kpis.get("oee") is not None and m.kpis["oee"] < m.prev_oee - 5:
            out.append(Insight(2, f"{m.name}: el OEE bajó {m.prev_oee - m.kpis['oee']:.0f} puntos contra el periodo "
                                  "anterior.", m.name))
        st = m.kpis.get("stability")
        if st is not None and st < 80:
            out.append(Insight(2, f"{m.name}: estabilidad baja ({st:.0f} % del tiempo con comportamiento normal).",
                               m.name))
        if m.slope.get("stability") is not None and m.slope["stability"] < -1:
            out.append(Insight(2, f"{m.name}: la estabilidad va a la baja ({m.slope['stability']:.1f} puntos por día): "
                                  "revisa desgaste, material o ajustes recientes.", m.name))
        if m.slope.get("oee") is not None and m.slope["oee"] > 1:
            out.append(Insight(0, f"{m.name}: el OEE mejora {m.slope['oee']:.1f} puntos por día.", m.name))
        i5 = m.kpis.get("i5")
        if i5 is not None and i5 < 70:
            out.append(Insight(2, f"{m.name}: índice 5.0 bajo ({i5:.0f}): mucha carga de alarmas para el operador"
                                  + (f" ({m.alarms_h:.1f} alarmas/h)" if m.alarms_h else "") + "; revisa límites y "
                                  "alarmas repetitivas.", m.name))
        cpk = m.kpis.get("cpk")
        if cpk is not None and cpk < 1.0:
            out.append(Insight(2, f"{m.name}: el Cpk promedio es {cpk:.2f}: el proceso no es capaz en alguna variable.",
                               m.name))
    mttrs = [m.mttr_min for m in with_data if m.mttr_min is not None]
    if len(mttrs) >= 2:
        avg = float(np.mean(mttrs))
        for m in with_data:
            if m.mttr_min is not None and m.mttr_min > 1.5 * avg and m.mttr_min > 10:
                out.append(Insight(2, f"{m.name}: los paros tardan mucho en resolverse (MTTR {m.mttr_min:.0f} min "
                                      f"contra {avg:.0f} min de la planta).", m.name))
    cur = getattr(s, "currency", "$")
    for m in with_data:
        comp = m.compliance
        if comp is not None and comp < 90:
            out.append(Insight(3 if comp < 75 else 2, f"{m.name}: produjo {m.produced:,.0f} {s.unit} contra una meta de "
                                                      f"{m.expected:,.0f} ({comp:.0f} % de cumplimiento).", m.name))
        elif comp is not None and comp >= 100:
            out.append(Insight(0, f"{m.name}: cumplió la meta de producción ({comp:.0f} %).", m.name))
        tg = getattr(m, "targets", None)
        if tg is not None:
            if tg.oee > 0 and m.kpis.get("oee") is not None and m.kpis["oee"] < tg.oee:
                out.append(Insight(2, f"{m.name}: OEE {m.kpis['oee']:.0f} % por debajo de su meta ({tg.oee:.0f} %).",
                                   m.name))
            if tg.mttr_min > 0 and m.mttr_min is not None and m.mttr_min > tg.mttr_min:
                out.append(Insight(2, f"{m.name}: MTTR {m.mttr_min:.0f} min arriba de la meta ({tg.mttr_min:.0f} min).",
                                   m.name))
        shifts = {k: v for k, v in m.by_shift.items() if v.get("oee") is not None and v["minutes"] >= 60}
        if len(shifts) >= 2:
            lo = min(shifts.items(), key=lambda kv: kv[1]["oee"])
            hi = max(shifts.items(), key=lambda kv: kv[1]["oee"])
            if hi[1]["oee"] - lo[1]["oee"] >= 8:
                out.append(Insight(2, f"{m.name}: el {lo[0]} rinde menos (OEE {lo[1]['oee']:.0f} %) que el {hi[0]} "
                                      f"({hi[1]['oee']:.0f} %): compara cómo trabajan.", m.name))
    qcost = sum(m.quality_cost for m in s.lines)
    if qcost > 0:
        scrap_c = sum(m.scrap_cost for m in s.lines)
        out.append(Insight(1, f"Costo de paros y desperdicio: {cur}{qcost:,.0f} en el periodo "
                              f"(paros {cur}{s.cost:,.0f} · desperdicio {cur}{scrap_c:,.0f})."))
    return sorted(out, key=lambda i: -i.severity)
