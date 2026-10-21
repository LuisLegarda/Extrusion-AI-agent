"""Ajustes de planta del dashboard global: metas por línea, costos, plan de mantenimiento, mapa y reporte semanal.

Se guardan en `<datos del dashboard>/planta.json` (no dependen de los monitores de las líneas).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Targets:
    production_shift: float = 0.0  # producción por turno (unidad de longitud del monitor; 0 = sin meta)
    oee: float = 0.0  # %
    availability: float = 0.0  # %
    mttr_min: float = 0.0  # minutos (máximo)
    scrap_day: float = 0.0  # desperdicio por día (máximo)

    def any(self) -> bool:
        return any(v > 0 for v in asdict(self).values())


@dataclass
class Equipment:
    name: str
    interval_h: float = 500.0  # horas de operación entre servicios
    last_service: float = 0.0  # fecha del último servicio (epoch)
    note: str = ""


@dataclass
class Weekly:
    enabled: bool = False
    weekday: int = 0  # 0 = lunes
    hour: int = 7
    last: float = 0.0  # cuándo se envió el último


@dataclass
class PlantSettings:
    currency: str = "$"
    cost_stop_h: float = 0.0  # costo de una hora de paro
    cost_scrap_unit: float = 0.0  # costo por unidad de desperdicio (m, kg…)
    default_targets: Targets = field(default_factory=Targets)
    targets: dict[str, Targets] = field(default_factory=dict)  # por línea (nombre)
    equipment: dict[str, list[Equipment]] = field(default_factory=dict)  # por línea
    map_pos: dict[str, list[float]] = field(default_factory=dict)  # línea -> [x, y] en el mapa
    map_image: str = ""  # plano de la planta (ruta de imagen)
    weekly: Weekly = field(default_factory=Weekly)

    @staticmethod
    def file(home: Path) -> Path:
        return Path(home) / "planta.json"

    @classmethod
    def load(cls, home: Path) -> "PlantSettings":
        s = cls()
        try:
            d = json.loads(cls.file(home).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
            try:  # costo de paro guardado por la versión anterior del analizador
                old = json.loads((Path(home) / "analizador.json").read_text(encoding="utf-8"))
                s.cost_stop_h = float(old.get("cost_per_h", 0.0))
            except (OSError, ValueError, TypeError):
                pass
            return s
        try:
            s.currency = str(d.get("currency", "$"))
            s.cost_stop_h = float(d.get("cost_stop_h", 0.0))
            s.cost_scrap_unit = float(d.get("cost_scrap_unit", 0.0))
            s.default_targets = _targets(d.get("default_targets"))
            s.targets = {k: _targets(v) for k, v in (d.get("targets") or {}).items()}
            s.equipment = {k: [Equipment(str(e.get("name", "")), float(e.get("interval_h", 500)),
                                         float(e.get("last_service", 0)), str(e.get("note", "")))
                               for e in v if str(e.get("name", "")).strip()]
                           for k, v in (d.get("equipment") or {}).items()}
            s.map_pos = {k: [float(v[0]), float(v[1])] for k, v in (d.get("map_pos") or {}).items() if len(v) == 2}
            s.map_image = str(d.get("map_image", ""))
            w = d.get("weekly") or {}
            s.weekly = Weekly(bool(w.get("enabled")), int(w.get("weekday", 0)) % 7, int(w.get("hour", 7)) % 24,
                              float(w.get("last", 0)))
        except (TypeError, ValueError, AttributeError):
            pass
        return s

    def save(self, home: Path) -> None:
        f = self.file(home)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(f)

    def target(self, line: str) -> Targets:
        t = self.targets.get(line)
        return t if t is not None and t.any() else self.default_targets


def _targets(d: Optional[dict]) -> Targets:
    d = d or {}
    t = Targets()
    for k in asdict(t):
        try:
            setattr(t, k, float(d.get(k, 0.0)))
        except (TypeError, ValueError):
            pass
    return t
