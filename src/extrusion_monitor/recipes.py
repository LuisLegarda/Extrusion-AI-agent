"""Recetas: valores nominales y tolerancias por variable."""
from __future__ import annotations

import csv
import io
import os
import re
from pathlib import Path
from typing import Literal, NamedTuple, Optional

from pydantic import BaseModel, Field


class Bounds(NamedTuple):
    """Límites absolutos; None = sin límite de ese lado."""

    wl: Optional[float] = None  # aviso bajo
    wh: Optional[float] = None  # aviso alto
    al: Optional[float] = None  # alarma baja
    ah: Optional[float] = None  # alarma alta

    @property
    def any(self) -> bool:
        return any(v is not None for v in self)


class Limit(BaseModel):
    nominal: Optional[float] = None
    warn: Optional[float] = Field(None, ge=0)
    alarm: Optional[float] = Field(None, ge=0)
    # "abs" = ± en unidades de la variable, "pct" = ± % del valor de referencia,
    # "range" = límites mínimo / máximo absolutos (pueden ser de un solo lado).
    mode: Literal["abs", "pct", "range"] = "abs"
    warn_min: Optional[float] = None
    warn_max: Optional[float] = None
    alarm_min: Optional[float] = None
    alarm_max: Optional[float] = None
    # Para variables reales: comparar contra la receta o contra la consigna leída del HMI.
    reference: Literal["recipe", "setpoint"] = "recipe"
    # Selectores: estado esperado (p. ej. «ON»).
    expected: Optional[str] = None

    def band(self, reference: float) -> tuple[Optional[float], Optional[float]]:
        """Tolerancias ± absolutas (aviso, alarma) para un valor de referencia (modos ±)."""
        if self.mode == "range":
            return None, None

        def conv(t: Optional[float]) -> Optional[float]:
            if t is None:
                return None
            return abs(reference) * t / 100.0 if self.mode == "pct" else t

        return conv(self.warn), conv(self.alarm)

    @property
    def active(self) -> bool:
        """La variable se verifica (tiene nominal o límites)."""
        if self.mode == "range":
            return Bounds(self.warn_min, self.warn_max, self.alarm_min, self.alarm_max).any
        return self.nominal is not None or self.reference == "setpoint"

    def center(self) -> Optional[float]:
        """Valor objetivo: el nominal o, en mín/máx sin nominal, el centro del rango."""
        if self.nominal is not None or self.mode != "range":
            return self.nominal
        for lo, hi in ((self.alarm_min, self.alarm_max), (self.warn_min, self.warn_max)):
            if lo is not None and hi is not None:
                return (lo + hi) / 2
        return None

    def bounds(self, reference: Optional[float]) -> Bounds:
        """Límites absolutos (en mín/máx no dependen de la referencia)."""
        if self.mode == "range":
            return Bounds(self.warn_min, self.warn_max, self.alarm_min, self.alarm_max)
        if reference is None:
            return Bounds()
        warn, alarm = self.band(reference)
        return Bounds(None if warn is None else reference - warn, None if warn is None else reference + warn,
                      None if alarm is None else reference - alarm, None if alarm is None else reference + alarm)

    def check(self) -> Optional[str]:
        """Error de coherencia de los límites (None si están bien)."""
        if self.mode == "range":
            for lo, hi, name in ((self.warn_min, self.warn_max, "aviso"), (self.alarm_min, self.alarm_max, "alarma")):
                if lo is not None and hi is not None and lo > hi:
                    return f"el mínimo de {name} es mayor que el máximo"
            if self.warn_min is not None and self.alarm_min is not None and self.warn_min < self.alarm_min:
                return "el mínimo de aviso debe estar dentro del rango de alarma"
            if self.warn_max is not None and self.alarm_max is not None and self.warn_max > self.alarm_max:
                return "el máximo de aviso debe estar dentro del rango de alarma"
        elif self.warn is not None and self.alarm is not None and self.warn > self.alarm:
            return "la tolerancia de aviso debe ser menor o igual que la de alarma"
        return None


class Recipe(BaseModel):
    name: str
    description: str = ""
    # Datos libres del producto: calibre, material, color, etc.
    meta: dict[str, str] = Field(default_factory=dict)
    limits: dict[str, Limit] = Field(default_factory=dict)


CSV_FIELDS = ["variable", "nominal", "warn", "alarm", "mode", "warn_min", "warn_max", "alarm_min", "alarm_max",
              "reference", "expected"]


def recipe_to_csv(recipe: Recipe) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    w.writeheader()
    for var_id, lim in recipe.limits.items():
        w.writerow({"variable": var_id, **lim.model_dump()})
    return buf.getvalue()


def recipe_from_csv(name: str, text: str) -> Recipe:
    """Importa una receta desde CSV (acepta ',' o ';' como separador y coma decimal)."""
    sample = text[:2048]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    limits: dict[str, Limit] = {}
    for row in reader:
        var_id = (row.get("variable") or "").strip()
        if not var_id:
            continue

        def num(key: str) -> Optional[float]:
            raw = (row.get(key) or "").strip().replace(",", ".")
            return float(raw) if raw else None

        limits[var_id] = Limit(
            nominal=num("nominal"),
            warn=num("warn"),
            alarm=num("alarm"),
            mode=(row.get("mode") or "abs").strip() or "abs",
            warn_min=num("warn_min"), warn_max=num("warn_max"),
            alarm_min=num("alarm_min"), alarm_max=num("alarm_max"),
            reference=(row.get("reference") or "recipe").strip() or "recipe",
            expected=(row.get("expected") or "").strip() or None,
        )
    return Recipe(name=name, limits=limits)


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()).strip("_")
    return s or "receta"


recipe_slug = _slug


def normalize_name(name: str) -> str:
    """Normalización usada para emparejar el nombre leído del HMI con la receta."""
    return re.sub(r"[^A-Z0-9]", "", name.upper())


class RecipeStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._recipes: dict[str, Recipe] = {}
        self.reload()

    def reload(self) -> None:
        self._recipes.clear()
        for f in sorted(self.directory.glob("*.json")):
            try:
                r = Recipe.model_validate_json(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            self._recipes[r.name] = r

    def names(self) -> list[str]:
        return sorted(self._recipes)

    def get(self, name: str) -> Optional[Recipe]:
        return self._recipes.get(name)

    def find_by_display_name(self, text: str) -> Optional[Recipe]:
        key = normalize_name(text)
        if not key:
            return None
        for r in self._recipes.values():
            if normalize_name(r.name) == key:
                return r
        return None

    def save(self, recipe: Recipe) -> None:
        path = self.directory / f"{_slug(recipe.name)}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(recipe.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, path)
        self._recipes[recipe.name] = recipe

    def delete(self, name: str) -> None:
        self._recipes.pop(name, None)
        path = self.directory / f"{_slug(name)}.json"
        if path.exists():
            path.unlink()
        prof = self.directory / f"{_slug(name)}.profile"
        if prof.exists():
            import shutil
            shutil.rmtree(prof)
