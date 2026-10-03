"""Problemas de proceso: paros detectados, capturas del operador (causas y defectos) y Paretos.

Lo comparten el monitor de la línea y el dashboard global; no depende de la interfaz.
"""
from __future__ import annotations

import csv
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .oee import MICROSTOP, STOPPED, Interval, OeeSample, compute

STOP_STATES = (STOPPED, MICROSTOP)
COVERED = 0.95  # un paro con este porcentaje clasificado se considera clasificado


@dataclass
class StopEvent:
    """Paro detectado (por la velocidad de línea) y cuánto de él ya se clasificó."""

    start: float
    end: float
    state: str
    classified_s: float = 0.0
    records: list = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def pending_s(self) -> float:
        return max(0.0, self.duration - self.classified_s)

    @property
    def classified(self) -> bool:
        return self.classified_s >= COVERED * self.duration


def overlap(a: float, b: float, c: float, d: float) -> float:
    return max(0.0, min(b, d) - max(a, c))


def machine_intervals(historian, config, since: float, until: float) -> list[Interval]:
    """Estado de la máquina (en marcha, lento, paro…) en el periodo, a partir del historial del OEE."""
    o = config.oee
    rows = historian.oee_samples(since, until)
    samples = [OeeSample(r[0], r[1], r[2], r[3], r[4], None if r[5] is None else bool(r[5]), r[6] or 0) for r in rows]
    return compute(samples, since, until, o.microstop_s, o.length_factor).intervals


def stop_events(intervals: Iterable[Interval], records: Iterable[dict], min_s: float = 0.0,
                include_micro: bool = False) -> list[StopEvent]:
    """Paros del periodo con la parte ya clasificada por las capturas de paro."""
    downs = [r for r in records if r.get("kind") == "downtime"]
    out = []
    for iv in intervals:
        if iv.state not in STOP_STATES or (iv.state == MICROSTOP and not include_micro):
            continue
        if iv.duration < min_s:
            continue
        ev = StopEvent(iv.start, iv.end, iv.state)
        for r in downs:
            ov = overlap(iv.start, iv.end, r["start"], r["end"])
            if ov > 0:
                ev.classified_s += ov
                ev.records.append(r)
        ev.classified_s = min(ev.classified_s, ev.duration)
        out.append(ev)
    return out


def free_spans(ev: StopEvent) -> list[tuple[float, float]]:
    """Partes del paro que aún no tienen causa (para proponer el siguiente tramo)."""
    spans = [(ev.start, ev.end)]
    for r in sorted(ev.records, key=lambda r: r["start"]):
        nxt = []
        for a, b in spans:
            if r["end"] <= a or r["start"] >= b:
                nxt.append((a, b))
                continue
            if r["start"] > a:
                nxt.append((a, r["start"]))
            if r["end"] < b:
                nxt.append((r["end"], b))
        spans = nxt
    return [(a, b) for a, b in spans if b - a >= 1.0]


# --- Paretos ---------------------------------------------------------------------------------------
@dataclass
class ParetoRow:
    label: str
    value: float
    count: int
    cum_pct: float
    planned: bool = False


def pareto(records: Iterable[dict], kind: str, by: str = "reason", metric: str = "time",
           include_planned: bool = True) -> list[ParetoRow]:
    """Agrupa las capturas por causa (o categoría) y las ordena de mayor a menor con su % acumulado.

    metric: «time» (minutos detenidos), «count» (número de eventos) o «scrap» (cantidad de scrap).
    """
    groups: dict[str, list] = {}
    for r in records:
        if r.get("kind") != kind or (not include_planned and r.get("planned")):
            continue
        key = (r.get("category") or "—") if by == "category" else \
            f"{r.get('reason') or '—'}" if by == "reason" else (r.get("operator") or "—")
        g = groups.setdefault(key, [0.0, 0, False])
        g[0] += (r.get("duration_s") or 0.0) / 60.0 if metric == "time" else \
            (r.get("scrap") or 0.0) if metric == "scrap" else 1
        g[1] += 1
        g[2] = g[2] or bool(r.get("planned"))
    rows = sorted(((k, v[0], v[1], v[2]) for k, v in groups.items()), key=lambda x: -x[1])
    total = sum(v for _, v, _, _ in rows) or 1.0
    out, acc = [], 0.0
    for label, value, count, planned in rows:
        acc += value
        out.append(ParetoRow(label, value, count, 100.0 * acc / total, planned))
    return out


@dataclass
class Summary:
    stop_min: float = 0.0
    planned_min: float = 0.0
    unplanned_min: float = 0.0
    n_downtime: int = 0
    n_quality: int = 0
    scrap: float = 0.0
    quality_min: float = 0.0
    pending_n: int = 0
    pending_min: float = 0.0


def summary(records: Iterable[dict], events: Optional[list[StopEvent]] = None) -> Summary:
    s = Summary()
    for r in records:
        d = (r.get("duration_s") or 0.0) / 60.0
        if r.get("kind") == "downtime":
            s.n_downtime += 1
            s.stop_min += d
            if r.get("planned"):
                s.planned_min += d
            else:
                s.unplanned_min += d
        else:
            s.n_quality += 1
            s.quality_min += d
        s.scrap += r.get("scrap") or 0.0
    for ev in events or []:
        if not ev.classified:
            s.pending_n += 1
            s.pending_min += ev.pending_s / 60.0
    return s


# --- CSV -------------------------------------------------------------------------------------------
CSV_COLUMNS = ["linea", "tipo", "inicio", "fin", "minutos", "categoria", "causa_o_defecto", "planeado", "scrap",
               "unidad", "operador", "comentario", "receta", "capturado"]


def _stamp(ts: Optional[float]) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else ""


def csv_row(r: dict, line: str = "") -> list:
    return [line or r.get("line", ""), "paro" if r.get("kind") == "downtime" else "calidad", _stamp(r.get("start")),
            _stamp(r.get("end")), f"{(r.get('duration_s') or 0) / 60:.2f}".replace(".", ","), r.get("category") or "",
            r.get("reason") or "", "sí" if r.get("planned") else "no",
            f"{r.get('scrap') or 0:g}".replace(".", ","), r.get("unit") or "", r.get("operator") or "",
            r.get("comment") or "", r.get("recipe") or "", _stamp(r.get("captured_at"))]


def export_csv(path, records: Iterable[dict], line: str = "", headers: Optional[list[str]] = None) -> int:
    n = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # Excel abre bien los acentos
        w = csv.writer(f, delimiter=";")
        w.writerow(headers or CSV_COLUMNS)
        for r in sorted(records, key=lambda r: r.get("start") or 0):
            w.writerow(csv_row(r, line))
            n += 1
    return n
