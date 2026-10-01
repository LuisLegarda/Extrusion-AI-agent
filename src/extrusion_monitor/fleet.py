"""Formato de intercambio con el dashboard global (varias líneas) a través de una carpeta compartida.

Cada línea escribe en ``<carpeta>/<id de línea>/``:

* ``status.json``: estado actual (se reemplaza completo cada pocos segundos, escritura atómica).
* ``events/AAAA-MM-DD.jsonl``: un evento por renglón (alarmas, recetas, recorridos, reportes…).
* ``trend/AAAA-MM-DD.jsonl``: un renglón por minuto con media, mínimo, máximo y último valor de cada variable.

El dashboard global solo vuelve a leer ``status.json`` cuando cambia su fecha de modificación y lee los
archivos de eventos de forma incremental (desde donde se quedó), así el costo no crece con el historial.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1
STATUS_FILE = "status.json"
EVENTS_DIR = "events"
TREND_DIR = "trend"


class StationSettings(BaseModel):
    """Exportación de esta línea al dashboard global (propia del equipo, no de la receta)."""

    enabled: bool = False
    line_id: str = ""  # carpeta de la línea dentro de la carpeta compartida
    line_name: str = ""  # nombre que muestra el dashboard global (vacío = nombre de la máquina)
    area: str = ""  # área o nave (agrupa las líneas en el dashboard global)
    export_dir: str = ""  # p. ej. \\SERVIDOR\lineas
    interval_s: float = Field(5.0, ge=1, le=60)
    trend_interval_s: float = Field(60.0, ge=10, le=600)
    retention_days: int = Field(30, ge=1, le=3650)


# --- configuración del dashboard global (fleet.json en la PC de supervisión) ------------------------
MAX_LINE_TILES = 5
FleetTileKind = Literal["kpi", "var", "production", "alarms"]
FleetChart = Literal["value", "gauge", "bar", "trend"]


class FleetTile(BaseModel):
    """Indicador de la tarjeta de una línea."""

    id: str
    kind: FleetTileKind = "kpi"
    kpi: str = "oee"  # clave de analysis.kpis.KPIS
    var: str = ""  # id (o nombre) de la variable; las líneas del mismo tipo comparten ids
    chart: FleetChart = "gauge"
    width: int = Field(1, ge=1, le=4)  # columnas de la tarjeta
    height: int = Field(1, ge=1, le=3)  # filas de la tarjeta
    range_s: float = Field(0.0, ge=0, le=86400)  # gráfica de tiempo: 0 = turno actual
    title: str = ""


def default_fleet_tiles() -> list[FleetTile]:
    return [FleetTile(id="oee_g", kind="kpi", kpi="oee", chart="gauge"),
            FleetTile(id="oee_t", kind="kpi", kpi="oee", chart="trend"),
            FleetTile(id="prod", kind="production", chart="value", width=2)]


class FleetSettings(BaseModel):
    dir: str = ""
    poll_s: float = Field(5.0, ge=1, le=60)
    offline_s: float = Field(30.0, ge=10, le=3600)  # sin actualizar más de esto = sin comunicación
    card_columns: int = Field(2, ge=1, le=4)  # columnas internas de cada tarjeta
    tiles: list[FleetTile] = Field(default_factory=default_fleet_tiles, max_length=MAX_LINE_TILES)
    overrides: dict[str, list[FleetTile]] = Field(default_factory=dict)  # id de línea -> indicadores propios
    areas: dict[str, str] = Field(default_factory=dict)  # id de línea -> área (vacío = la que publica la línea)
    group_by_area: bool = True
    sound: bool = True
    notify_alarm: bool = True
    notify_stop: bool = True
    notify_offline: bool = True
    tv_rotate_s: float = Field(20.0, ge=5, le=600)

    def tiles_for(self, line_id: str) -> list[FleetTile]:
        return self.overrides.get(line_id) or self.tiles

    def area_of(self, line: "LineState") -> str:
        return self.areas.get(line.line_id) or line.status.get("area") or ""


def load_fleet_settings(path: Path) -> FleetSettings:
    try:
        return FleetSettings.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return FleetSettings()


def save_fleet_settings(path: Path, st: FleetSettings) -> None:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(st.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)


def find_var(status: dict, ref: str) -> Optional[dict]:
    """Variable de una línea por id o, si no, por nombre (sin distinguir mayúsculas)."""
    vars_ = status.get("variables") or []
    v = next((x for x in vars_ if x.get("id") == ref), None)
    if v is None and ref:
        low = ref.strip().lower()
        v = next((x for x in vars_ if (x.get("name") or "").lower() == low
                  or (x.get("label") or "").lower() == low), None)
    return v


def line_slug(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")  # «Línea» → «Linea»
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip()).strip("-.")
    return s[:60] or "linea"


def day_name(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts)) + ".jsonl"


def write_atomic(path: Path, data: bytes, retries: int = 6) -> None:
    """Escribe en un temporal y lo renombra: quien lee nunca ve un archivo a medias.

    En Windows el renombrado falla si el dashboard justo está leyendo el archivo; se reintenta.
    """
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    for i in range(retries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == retries - 1:
                try:
                    tmp.unlink()
                except OSError:
                    pass
                raise
            time.sleep(0.05 * (i + 1))


def append_lines(path: Path, lines: list[str]) -> None:
    if not lines:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write("".join(line + "\n" for line in lines))


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# --- lectura (dashboard global) -----------------------------------------------------------------
@dataclass
class LineState:
    line_id: str
    path: Path
    status: dict = field(default_factory=dict)
    mtime: float = 0.0
    error: str = ""
    events: list = field(default_factory=list)  # eventos recientes (los últimos MAX_EVENTS)
    _ev_file: str = ""
    _ev_pos: int = 0
    # tendencias en memoria: ("v", id) o ("k", clave) -> (tiempos, valores); solo las que piden los indicadores
    series: dict = field(default_factory=dict)
    _tr_keys: frozenset = frozenset()
    _tr_since: float = 0.0
    _tr_pos: dict = field(default_factory=dict)  # archivo -> posición leída

    @property
    def name(self) -> str:
        return self.status.get("line_name") or self.line_id

    def age(self, now: float) -> Optional[float]:
        ts = self.status.get("ts")
        return None if ts is None else max(0.0, now - ts)

    def connection(self, now: float, offline_s: Optional[float] = None) -> str:
        """«online», «stale» (sin actualizar), «closed» (programa cerrado) u «offline»."""
        if not self.status:
            return "offline"
        if self.status.get("closed"):
            return "closed"
        age = self.age(now)
        interval = float(self.status.get("interval_s") or 5.0)
        if age is None or age > (offline_s if offline_s else max(30.0, interval * 6)):
            return "offline"
        if age > interval * 2.5:
            return "stale"
        return "online"


MAX_EVENTS = 300


class FleetReader:
    """Lee la carpeta compartida: estado de cada línea y eventos nuevos, con el mínimo de E/S."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.lines: dict[str, LineState] = {}
        self.error = ""

    def scan(self, read_events: bool = True) -> list[dict]:
        """Actualiza las líneas. Devuelve los eventos nuevos de todas las líneas (con `line_id`)."""
        new_events: list[dict] = []
        try:
            entries = [e for e in os.scandir(self.root) if e.is_dir()]
            self.error = ""
        except OSError as exc:
            self.error = str(exc)
            return new_events
        seen = set()
        for e in entries:
            st_path = Path(e.path) / STATUS_FILE
            try:
                mtime = st_path.stat().st_mtime
            except OSError:
                continue
            seen.add(e.name)
            line = self.lines.get(e.name)
            if line is None:
                line = self.lines[e.name] = LineState(e.name, Path(e.path))
            if mtime != line.mtime:
                try:
                    line.status = json.loads(st_path.read_bytes().decode("utf-8"))
                    line.mtime = mtime
                    line.error = ""
                except (OSError, ValueError) as exc:  # se reintenta en el siguiente ciclo
                    line.error = str(exc)
            if read_events:
                new_events += self._tail_events(line)
        for gone in [k for k in self.lines if k not in seen]:
            del self.lines[gone]
        return new_events

    def _tail_events(self, line: LineState) -> list[dict]:
        name = day_name(time.time())
        path = line.path / EVENTS_DIR / name
        if line._ev_file != name:
            # Al abrir (o al cambiar de día) solo se cargan los últimos eventos del archivo.
            line._ev_file, line._ev_pos = name, 0
            first = True
        else:
            first = False
        try:
            size = path.stat().st_size
        except OSError:
            return []
        if size < line._ev_pos:
            line._ev_pos = 0
        if size == line._ev_pos:
            return []
        try:
            with open(path, "rb") as f:
                if first and size > 256_000:
                    f.seek(size - 256_000)
                    f.readline()
                else:
                    f.seek(line._ev_pos)
                chunk = f.read()
        except OSError:
            return []
        # Solo renglones completos; un renglón a medias se lee en el siguiente ciclo.
        end = chunk.rfind(b"\n") + 1
        start_pos = (size - len(chunk)) if first and size > 256_000 else line._ev_pos
        line._ev_pos = start_pos + end
        out = []
        for raw in chunk[:end].splitlines():
            try:
                ev = json.loads(raw.decode("utf-8"))
            except ValueError:
                continue
            ev["line_id"] = line.line_id
            out.append(ev)
        line.events = (line.events + out)[-MAX_EVENTS:]
        return out

    def update_series(self, line: LineState, keys: set, since: float) -> None:
        """Tendencias de los indicadores de la tarjeta: carga inicial y luego solo los renglones nuevos."""
        keys = frozenset(keys)
        if not keys:
            line.series, line._tr_keys = {}, keys
            return
        if keys != line._tr_keys or since < line._tr_since - 60:
            line.series = {k: ([], []) for k in keys}
            line._tr_keys, line._tr_since, line._tr_pos = keys, since, {}
        names = list(dict.fromkeys(day_name(t) for t in (since, time.time())))
        for name in names:
            path = line.path / TREND_DIR / name
            pos = line._tr_pos.get(name, 0)
            try:
                size = path.stat().st_size
                if size <= pos:
                    continue
                with open(path, "rb") as f:
                    f.seek(pos)
                    chunk = f.read()
            except OSError:
                continue
            end = chunk.rfind(b"\n") + 1
            line._tr_pos[name] = pos + end
            for raw in chunk[:end].splitlines():
                try:
                    row = json.loads(raw)
                except ValueError:
                    continue
                ts = row.get("ts", 0)
                if ts < since:
                    continue
                for kind, key in keys:
                    v = row.get(kind, {}).get(key)
                    if v is None:
                        continue
                    t, y = line.series[(kind, key)]
                    t.append(ts)
                    y.append(v[0] if isinstance(v, list) else v)
        for name in [n for n in line._tr_pos if n not in names]:
            del line._tr_pos[name]  # días anteriores ya no se leen
        cut = since
        for t, y in line.series.values():  # se descarta lo que quedó fuera del periodo
            i = 0
            while i < len(t) and t[i] < cut:
                i += 1
            if i:
                del t[:i], y[:i]
        line._tr_since = since

    def trend(self, line_id: str, var_id: str, since: float) -> tuple[list[float], list[float], list[float], list[float]]:
        """Serie por minuto de una variable (t, media, mín, máx) desde `since` (lee los archivos de cada día)."""
        line = self.lines.get(line_id)
        t, mean, lo, hi = [], [], [], []
        if line is None:
            return t, mean, lo, hi
        day = since
        days = []
        while day <= time.time() + 86400:
            days.append(day_name(day))
            day += 86400
        for name in dict.fromkeys(days):
            path = line.path / TREND_DIR / name
            try:
                with open(path, "rb") as f:
                    for raw in f:
                        try:
                            row = json.loads(raw)
                        except ValueError:
                            continue
                        if row.get("ts", 0) < since:
                            continue
                        v = row.get("v", {}).get(var_id)
                        if v:
                            t.append(row["ts"])
                            mean.append(v[0])
                            lo.append(v[1])
                            hi.append(v[2])
            except OSError:
                continue
        return t, mean, lo, hi
