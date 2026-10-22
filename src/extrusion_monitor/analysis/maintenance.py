"""Administrador de mantenimiento del dashboard: preventivos y correctivos leídos de los paros capturados.

No se captura nada en el dashboard: cada paro que el operador registra en el monitor se clasifica (por su categoría
y causa) como mantenimiento preventivo, correctivo o ninguno. Con eso se cuentan eventos, horas y desperdicio por
línea, cuándo fue el último preventivo y el último correctivo, y si el preventivo ya está atrasado.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

LOOKBACK_S = 365 * 86400  # para «último preventivo / correctivo» se busca hasta un año atrás


@dataclass
class MaintEvent:
    line: str
    kind: str  # preventive | corrective
    start: float
    end: float
    minutes: float
    category: str
    reason: str
    scrap: float
    unit: str
    operator: str
    comment: str


@dataclass
class LineMaint:
    name: str
    has_data: bool = True
    n_prev: int = 0
    n_corr: int = 0
    min_prev: float = 0.0
    min_corr: float = 0.0
    scrap_prev: float = 0.0
    scrap_corr: float = 0.0
    last_prev: Optional[float] = None
    last_corr: Optional[float] = None
    pm_days: float = 30.0
    run_h: float = 0.0
    events: list[MaintEvent] = field(default_factory=list)

    @property
    def days_since_prev(self) -> Optional[float]:
        return None if self.last_prev is None else (time.time() - self.last_prev) / 86400

    @property
    def days_since_corr(self) -> Optional[float]:
        return None if self.last_corr is None else (time.time() - self.last_corr) / 86400

    @property
    def state(self) -> str:
        """«ok», «soon» (≥ 80 % del intervalo), «late» (atrasado) o «none» (nunca hubo preventivo)."""
        d = self.days_since_prev
        if d is None:
            return "none"
        if d > self.pm_days:
            return "late"
        return "soon" if d >= 0.8 * self.pm_days else "ok"

    @property
    def mttr_corr(self) -> Optional[float]:
        return self.min_corr / self.n_corr if self.n_corr else None

    @property
    def mtbf_corr(self) -> Optional[float]:
        return self.run_h / self.n_corr if self.n_corr and self.run_h else None

    @property
    def pm_pct(self) -> Optional[float]:
        total = self.min_prev + self.min_corr
        return 100 * self.min_prev / total if total else None


@dataclass
class MaintSummary:
    since: float
    until: float
    lines: list[LineMaint]

    @property
    def events(self) -> list[MaintEvent]:
        return sorted((e for m in self.lines for e in m.events), key=lambda e: -e.start)

    def total(self, attr: str) -> float:
        return sum(getattr(m, attr) for m in self.lines)

    @property
    def pm_pct(self) -> Optional[float]:
        total = self.total("min_prev") + self.total("min_corr")
        return 100 * self.total("min_prev") / total if total else None

    @property
    def late(self) -> list[LineMaint]:
        return [m for m in self.lines if m.has_data and m.state in ("late", "none")]

    @property
    def mttr_corr(self) -> Optional[float]:
        n = self.total("n_corr")
        return self.total("min_corr") / n if n else None


def summarize_maintenance(hist, plant, since: float, until: float, line: str = "") -> MaintSummary:
    lines_all = [ln.name for ln in hist.lines()]
    names = [n for n in dict.fromkeys(lines_all + list(plant.extra_lines)) if not line or n == line]
    recs = hist.problems(min(since, until - LOOKBACK_S), until, kind="downtime")
    rows = hist.rows_by_line(since, until) if hasattr(hist, "rows_by_line") else {}
    out = []
    for name in names:
        m = LineMaint(name, has_data=name in lines_all, pm_days=plant.pm_every(name))
        m.run_h = run_hours(rows.get(name, []))
        for r in recs:
            if r.get("line") != name:
                continue
            kind = plant.maint_kind(r)
            if kind == "none":
                continue
            start, end = float(r.get("start") or 0), float(r.get("end") or 0)
            if kind == "preventive":
                m.last_prev = max(m.last_prev or 0, start)
            else:
                m.last_corr = max(m.last_corr or 0, start)
            if end < since or start > until:
                continue  # fuera del periodo: solo cuenta para «último»
            mins = max(0.0, min(end, until) - max(start, since)) / 60
            scrap = float(r.get("scrap") or 0)
            if kind == "preventive":
                m.n_prev += 1
                m.min_prev += mins
                m.scrap_prev += scrap
            else:
                m.n_corr += 1
                m.min_corr += mins
                m.scrap_corr += scrap
            m.events.append(MaintEvent(name, kind, start, end, mins, r.get("category") or "", r.get("reason") or "",
                                       scrap, r.get("unit") or "", r.get("operator") or "", r.get("comment") or ""))
        out.append(m)
    return MaintSummary(since, until, out)


def run_hours(rows: list[dict]) -> float:
    """Horas en marcha según el estado publicado cada minuto (o minutos con datos, en monitores anteriores)."""
    from .plant import RUN_STATES
    if any(r.get("s") for r in rows):
        return sum(min(300.0, max(0.0, r["ts"] - (r.get("from") or r["ts"] - 60))) / 3600
                   for r in rows if r.get("s") in RUN_STATES)
    return len(rows) / 60
