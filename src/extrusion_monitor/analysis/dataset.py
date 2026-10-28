"""Datos para el análisis estadístico: historial de variables con rango de fechas, filtros y agrupación.

Agrupación y filtros por turno, día, semana, mes, hora, operador (usuario en turno registrado al cambiarlo)
y receta (cambios de receta del historial). Las series muy largas se promedian en tramos para no saturar
la memoria (se indica en el resultado). También arma los datos de paros y defectos capturados.
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..i18n import tr

GROUPS = {"": "Sin agrupar", "shift": "Turno", "day": "Día", "week": "Semana", "month": "Mes", "hour": "Hora del día",
          "operator": "Operador", "recipe": "Receta", "line": "Línea"}  # «Línea»: solo en el dashboard global
MAX_POINTS = 60000


@dataclass
class DataRequest:
    vars: list[str] = field(default_factory=list)
    since: float = 0.0
    until: float = 0.0
    group_by: str = ""
    shift: str = ""  # filtro: solo este turno
    operator: str = ""  # filtro: solo este operador
    recipe: str = ""  # filtro: solo esta receta
    line: str = ""  # filtro: solo esta línea (dashboard global)

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: dict) -> "DataRequest":
        known = {k: d[k] for k in cls().__dict__ if k in d}
        return cls(**known)


@dataclass
class VarData:
    vid: str
    label: str
    unit: str
    t: np.ndarray
    y: np.ndarray
    groups: np.ndarray  # etiqueta de grupo de cada punto ("" si no se agrupa)
    averaged_s: float = 0.0  # > 0: los datos se promediaron en tramos de esta duración

    def by_group(self) -> dict[str, np.ndarray]:
        if not len(self.groups) or not self.groups.any():
            return {self.label: self.y}
        out: dict[str, np.ndarray] = {}
        for g in sorted(set(self.groups.tolist()), key=_natural):
            out[g] = self.y[self.groups == g]
        return out


def _natural(s: str):
    import re
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", str(s))]


class Timeline:
    """Quién estaba en turno y qué receta corría en cada instante (a partir del historial de eventos)."""

    def __init__(self, historian, since: float, until: float):
        self.ops: list[tuple[float, str]] = []
        self.recipes: list[tuple[float, str]] = []
        if historian is None:
            return
        before = historian.events_between(0, since)  # el estado vigente al empezar el rango
        rows = historian.events_between(since, until)
        for row in list(before)[-2000:] + list(rows):
            ts, kind, _lvl, _rule, var, _msg, recipe = row[:7]
            if kind == "crew":
                self.ops.append((ts, var or ""))
            elif kind == "recipe_change":
                self.recipes.append((ts, recipe or ""))

    @staticmethod
    def _at(events: list[tuple[float, str]], t: np.ndarray, default: str) -> np.ndarray:
        if not events:
            return np.full(len(t), default, dtype=object)
        ts = np.array([e[0] for e in events])
        names = np.array([e[1] or default for e in events], dtype=object)
        idx = np.searchsorted(ts, t, side="right") - 1
        out = np.full(len(t), default, dtype=object)
        ok = idx >= 0
        out[ok] = names[idx[ok]]
        return out

    def operators(self, t: np.ndarray) -> np.ndarray:
        return self._at(self.ops, t, tr("(sin usuario)"))

    def recipes_at(self, t: np.ndarray) -> np.ndarray:
        return self._at(self.recipes, t, tr("(sin receta)"))


def shift_names(t: np.ndarray, shifts, starts: list[str]) -> np.ndarray:
    """Turno de cada instante: los de Configuración → Personal (con nombre y horario) o los inicios del OEE."""
    out = np.empty(len(t), dtype=object)
    if shifts:
        for i, ts in enumerate(t):
            d = dt.datetime.fromtimestamp(float(ts))
            out[i] = next((s.name for s in shifts if s.contains(d)), tr("(fuera de turno)"))
        return out
    mins = sorted(int(h) * 60 + int(m) for h, m in (s.split(":") for s in starts if ":" in s)) or [0]
    for i, ts in enumerate(t):
        d = dt.datetime.fromtimestamp(float(ts))
        m = d.hour * 60 + d.minute
        k = max((j for j, s in enumerate(mins) if s <= m), default=len(mins) - 1)
        out[i] = f"Turno {k + 1}"
    return out


def labels(t: np.ndarray, by: str, timeline: Optional[Timeline], shifts, starts: list[str]) -> np.ndarray:
    if not by or not len(t) or by == "line":  # «línea» solo aplica a los datos del dashboard global
        return np.full(len(t), "", dtype=object)
    if by == "shift":
        return shift_names(t, shifts, starts)
    if by == "operator":
        return timeline.operators(t) if timeline else np.full(len(t), tr("(sin usuario)"), dtype=object)
    if by == "recipe":
        return timeline.recipes_at(t) if timeline else np.full(len(t), tr("(sin receta)"), dtype=object)
    fmt = {"day": "%Y-%m-%d", "week": "%Y-S%V", "month": "%Y-%m", "hour": "%H:00"}[by]
    return np.array([time.strftime(fmt, time.localtime(float(x))) for x in t], dtype=object)


def _downsample(t: np.ndarray, y: np.ndarray, max_points: int) -> tuple[np.ndarray, np.ndarray, float]:
    n = len(y)
    if n <= max_points:
        return t, y, 0.0
    k = int(np.ceil(n / max_points))
    m = n // k
    tt = t[:m * k].reshape(m, k).mean(axis=1)
    yy = y[:m * k].reshape(m, k).mean(axis=1)
    return tt, yy, float((t[-1] - t[0]) / max(1, m))


def _filtered(t, y, req: DataRequest, timeline, shifts, starts):
    keep = np.isfinite(y)
    t, y = t[keep], y[keep]
    if req.shift and len(t):
        keep = shift_names(t, shifts, starts) == req.shift
        t, y = t[keep], y[keep]
    if req.operator and len(t):
        keep = timeline.operators(t) == req.operator
        t, y = t[keep], y[keep]
    if req.recipe and len(t):
        keep = timeline.recipes_at(t) == req.recipe
        t, y = t[keep], y[keep]
    return t, y


def fetch(historian, config, req: DataRequest, shifts=(), max_points: int = MAX_POINTS) -> list[VarData]:
    """Series de las variables pedidas, ya filtradas y con su etiqueta de grupo."""
    need_tl = req.group_by in ("operator", "recipe") or req.operator or req.recipe
    timeline = Timeline(historian, req.since, req.until) if need_tl else None
    starts = list(config.oee.shift_starts)
    out = []
    names = [v.name for v in config.variables]
    for vid in req.vars:
        v = config.variable(vid)
        if v is None or historian is None:
            continue
        label = v.name if names.count(v.name) == 1 else config.var_label(v)  # corto si no se repite
        if hasattr(historian, "samples_by_line"):  # dashboard global: varias líneas
            by_line = historian.samples_by_line(vid, req.since, req.until)
            if req.line:
                by_line = {k: r for k, r in by_line.items() if k == req.line}
            parts, avg = [], 0.0
            per = max(1000, max_points // max(1, len(by_line)))
            for ln, rows in by_line.items():
                t = np.array([r[0] for r in rows], float)
                y = np.array([np.nan if r[1] is None else r[1] for r in rows], float)
                t, y = _filtered(t, y, req, timeline, shifts, starts)
                t, y, a = _downsample(t, y, per)  # por línea: no se mezclan líneas al promediar
                avg = max(avg, a)
                parts.append((t, y, np.full(len(t), ln, dtype=object)))
            if parts:
                t = np.concatenate([p[0] for p in parts])
                y = np.concatenate([p[1] for p in parts])
                lines = np.concatenate([p[2] for p in parts])
                order = np.argsort(t, kind="stable")
                t, y, lines = t[order], y[order], lines[order]
            else:
                t, y, lines = np.empty(0), np.empty(0), np.empty(0, dtype=object)
            g = lines if req.group_by == "line" else labels(t, req.group_by, timeline, shifts, starts)
            out.append(VarData(vid, label, v.unit, t, y, g, avg))
            continue
        rows = historian.samples(vid, req.since, req.until)
        rows = [r for r in rows if r[1] is not None]
        t = np.array([r[0] for r in rows], float)
        y = np.array([r[1] for r in rows], float)
        t, y = _filtered(t, y, req, timeline, shifts, starts)
        t, y, avg = _downsample(t, y, max_points)
        g = labels(t, req.group_by, timeline, shifts, starts)
        out.append(VarData(vid, label, v.unit, t, y, g, avg))
    return out


def problems_table(historian, since: float, until: float, kind: str, shifts=(), starts=()) -> list[dict]:
    """Capturas de paros o defectos del rango, con su turno."""
    if historian is None:
        return []
    recs = historian.problems(since, until, kind=kind or None)
    if recs:
        names = shift_names(np.array([r["start"] for r in recs], float), shifts, list(starts))
        for r, s in zip(recs, names):
            r["shift"] = s
            r["day"] = time.strftime("%Y-%m-%d", time.localtime(r["start"]))
            r["month"] = time.strftime("%Y-%m", time.localtime(r["start"]))
    return recs
