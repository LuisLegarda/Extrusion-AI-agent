"""Datos de las líneas del dashboard global para el análisis estadístico y el analizador de planta.

Lee lo que cada monitor publica en la carpeta compartida: tendencia por minuto de cada variable (media),
indicadores por minuto (OEE, estabilidad, índice 5.0…), eventos y capturas de paros y defectos. Ofrece la misma
interfaz que el historial local (`samples`, `events_between`, `problems`) para reutilizar el análisis
estadístico del monitor, con agrupación y filtro por línea.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional

from .fleet import EVENTS_DIR, TREND_DIR, FleetReader, LineState, day_name, read_problems

LEVEL_NUM = {"OK": 0, "INFO": 1, "WARN": 2, "ALARM": 3}
DEFAULT_SHIFTS = ["06:00", "14:00", "22:00"]


def _days(since: float, until: float) -> list[str]:
    out, t = [], since
    while t <= until + 86400:
        out.append(day_name(t))
        t += 86400
    return list(dict.fromkeys(out))


def _rows(line: LineState, sub: str, since: float, until: float):
    for name in _days(since, until):
        path = line.path / sub / name
        try:
            with open(path, "rb") as f:
                for raw in f:
                    try:
                        row = json.loads(raw)
                    except ValueError:
                        continue
                    ts = row.get("ts", 0)
                    if since <= ts <= until:
                        yield row
        except OSError:
            continue


_TREND_IDS: dict[str, tuple[float, list[str]]] = {}  # archivo -> (mtime, ids de variables con datos)
TREND_SCAN_FILES = 7  # archivos diarios recientes en los que se buscan variables


def _trend_ids(line: LineState) -> list[str]:
    """Variables que aparecen en los archivos de tendencia recientes de la línea (aunque no se esté monitoreando)."""
    try:
        files = sorted(p for p in (line.path / TREND_DIR).glob("*.jsonl"))[-TREND_SCAN_FILES:]
    except OSError:
        return []
    ids: dict[str, None] = {}
    for p in files:
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        hit = _TREND_IDS.get(str(p))
        if hit is None or hit[0] != mtime:
            found: dict[str, None] = {}
            try:
                with open(p, "rb") as f:
                    for raw in f:
                        try:
                            found.update(dict.fromkeys((json.loads(raw).get("v") or {})))
                        except (ValueError, AttributeError):
                            continue
            except OSError:
                continue
            hit = _TREND_IDS[str(p)] = (mtime, list(found))
        ids.update(dict.fromkeys(hit[1]))
    return list(ids)


def line_variables(line: LineState) -> list[dict]:
    """Variables de la línea para el análisis: las publicadas en vivo, el catálogo de la receta y, si el monitor no
    está monitoreando (o es de una versión anterior), las que tienen datos en la carpeta de tendencias."""
    st = line.status or {}
    out: dict[str, dict] = {}
    for v in (st.get("variables") or []) + (st.get("catalog") or []):
        if v.get("id") and v["id"] not in out:
            out[v["id"]] = v
    for vid in _trend_ids(line):
        out.setdefault(vid, {"id": vid, "name": vid, "kind": "actual"})
    return list(out.values())


class FleetHistorian:
    """Historial «virtual» de las líneas elegidas (todas, o la que se filtre)."""

    def __init__(self, reader: FleetReader, line: str = ""):
        self.reader = reader
        self.line = line  # nombre de la línea a la que se limita ("" = todas)

    def lines(self) -> list[LineState]:
        lines = sorted(self.reader.lines.values(), key=lambda ln: ln.name)
        return [ln for ln in lines if not self.line or ln.name == self.line or ln.line_id == self.line]

    def samples_by_line(self, vid: str, since: float, until: Optional[float] = None) -> dict[str, list[tuple]]:
        until = until or time.time()
        out: dict[str, list[tuple]] = {}
        for ln in self.lines():
            rows = []
            for row in _rows(ln, TREND_DIR, since, until):
                v = (row.get("v") or {}).get(vid)
                if v:
                    rows.append((row["ts"], v[0] if isinstance(v, list) else v))
            if rows:
                out[ln.name] = rows
        return out

    def samples(self, vid: str, since: float, until: Optional[float] = None) -> list[tuple]:
        rows = [r for rs in self.samples_by_line(vid, since, until).values() for r in rs]
        return sorted(rows)

    def rows_by_line(self, since: float, until: Optional[float] = None) -> dict[str, list[dict]]:
        """Renglones completos de la tendencia por minuto (indicadores, producción, estado, usuario)."""
        until = until or time.time()
        return {ln.name: list(_rows(ln, TREND_DIR, since, until)) for ln in self.lines()}

    def kpis_by_line(self, since: float, until: Optional[float] = None) -> dict[str, list[tuple[float, dict]]]:
        """Indicadores por minuto de cada línea: {línea: [(ts, {oee, availability, …})]}."""
        until = until or time.time()
        out = {}
        for ln in self.lines():
            out[ln.name] = [(row["ts"], row.get("k") or {}) for row in _rows(ln, TREND_DIR, since, until)]
        return out

    def events_between(self, since: float, until: float) -> list[tuple]:
        out = []
        for ln in self.lines():
            for e in _rows(ln, EVENTS_DIR, since, until):
                out.append((e.get("ts", 0), e.get("kind"), LEVEL_NUM.get(str(e.get("level")), 0), e.get("rule"),
                            e.get("var"), e.get("msg"), e.get("recipe"), ln.name))
        return sorted(out, key=lambda r: r[0])

    def problems(self, since: float = 0.0, until: Optional[float] = None, kind: Optional[str] = None,
                 ids=None) -> list[dict]:
        recs = []
        for ln in self.lines():
            recs += [r for r in read_problems(ln, since, until) if not kind or r.get("kind") == kind]
        return sorted(recs, key=lambda r: r.get("start") or 0)


@dataclass
class FleetVar:
    id: str
    name: str
    unit: str = ""
    kind: str = "actual"
    page: Optional[str] = None
    numeric: bool = True
    measured: bool = True
    trend: bool = True
    setpoint_var: Optional[str] = None
    lines: list = field(default_factory=list)


class FleetConfig:
    """Lo mínimo de una configuración de receta que usa el análisis, armado con las variables de las líneas."""

    def __init__(self, reader: FleetReader, shift_starts: Optional[list[str]] = None):
        self.machine_name = "Planta"
        self.pages: list = []
        by_id: dict[str, FleetVar] = {}
        for ln in sorted(reader.lines.values(), key=lambda ln: ln.name):
            for v in line_variables(ln):
                if v.get("kind") in ("text", "selector"):
                    continue
                fv = by_id.get(v["id"])
                if fv is None:
                    fv = by_id[v["id"]] = FleetVar(v["id"], v.get("name") or v["id"], v.get("unit") or "",
                                                   v.get("kind") or "actual")
                if ln.name not in fv.lines:
                    fv.lines.append(ln.name)
        self.variables = list(by_id.values())
        self.oee = SimpleNamespace(shift_starts=shift_starts or DEFAULT_SHIFTS, enabled=False, speed_var=None)
        self.general = SimpleNamespace(sample_interval_s=60.0)

    def variable(self, vid: Optional[str]) -> Optional[FleetVar]:
        return next((v for v in self.variables if v.id == vid), None)

    def var_label(self, v: FleetVar) -> str:
        return v.name

    def page_label(self, _pid) -> str:
        return ""


class FleetStatsContext:
    """Contexto equivalente al del monitor para la página de análisis estadístico del dashboard."""

    def __init__(self, reader_fn: Callable[[], FleetReader], home: Path):
        self._reader_fn = reader_fn
        self.workspace = SimpleNamespace(home=Path(home), default_reports_dir=lambda: Path(home) / "reportes")
        self.recipes = SimpleNamespace(names=self._recipes)
        self.fleet = True
        self.refresh()

    def refresh(self) -> None:
        reader = self._reader_fn()
        self.engine = SimpleNamespace(config=FleetConfig(reader), historian=FleetHistorian(reader), clock=time.time,
                                      last=None, state=SimpleNamespace(recipe=None))

    @property
    def lines(self) -> list[str]:
        return [ln.name for ln in sorted(self._reader_fn().lines.values(), key=lambda ln: ln.name)]

    def _recipes(self) -> list[str]:
        return sorted({ln.status.get("recipe") for ln in self._reader_fn().lines.values() if ln.status.get("recipe")})
