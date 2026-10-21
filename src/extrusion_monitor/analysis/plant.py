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

KPI_KEYS = ("oee", "availability", "performance", "quality", "stability", "i5", "cpk", "conform")


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
    cost: float = 0.0

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


def line_metrics(name: str, kpi_rows: list[tuple[float, dict]], problems: list[dict], events: list[tuple],
                 since: float, until: float, cost_per_h: float = 0.0) -> LineMetrics:
    m = LineMetrics(name)
    m.minutes = len(kpi_rows)
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
        cause = r.get("reason") or r.get("category") or "(sin causa)"
        m.causes[cause] = m.causes.get(cause, 0.0) + mins
    m.scrap = sum(float(r.get("scrap") or 0) for r in problems)
    if m.n_stops:
        m.mttr_min = m.stop_min / m.n_stops
        run_h = max(0.0, (until - since) / 3600 - (m.stop_min + m.planned_min) / 60)
        m.mtbf_h = run_h / m.n_stops
    m.alarms = sum(1 for e in events if e[2] >= 3 and e[1] in ("raised", "escalated"))
    hours = max(m.minutes / 60, 1e-9)
    m.alarms_h = m.alarms / hours if m.minutes else None
    m.cost = m.stop_min / 60 * cost_per_h
    return m


def summarize(hist, since: float, until: float, cost_per_h: float = 0.0) -> PlantSummary:
    """Métricas y conclusiones de las líneas de `hist` (FleetHistorian) en [since, until]."""
    span = until - since
    kpis = hist.kpis_by_line(since, until)
    prev_kpis = hist.kpis_by_line(since - span, since)
    probs = hist.problems(since, until)
    prev_probs = hist.problems(since - span, since)
    events = hist.events_between(since, until)
    lines = []
    for ln in hist.lines():
        name = ln.name
        m = line_metrics(name, kpis.get(name, []), [r for r in probs if r.get("line") == name],
                         [e for e in events if e[7] == name], since, until, cost_per_h)
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
                                + (f"; su mayor pérdida es la {LOSS_NAMES[loss[0]]} ({loss[1]:.0f} %)." if loss else "."),
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
    if s.cost > 0:
        out.append(Insight(1, f"Costo estimado del tiempo muerto: ${s.cost:,.0f} en el periodo."))
    return sorted(out, key=lambda i: -i.severity)
