"""Recetas: valores nominales y tolerancias por variable."""
from __future__ import annotations

import csv
import io
import os
import re
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Limit(BaseModel):
    nominal: Optional[float] = None
    warn: Optional[float] = Field(None, ge=0)
    alarm: Optional[float] = Field(None, ge=0)
    # "abs" = tolerancia en unidades de la variable, "pct" = porcentaje del valor de referencia.
    mode: Literal["abs", "pct"] = "abs"
    # Para variables reales: comparar contra la receta o contra la consigna leída del HMI.
    reference: Literal["recipe", "setpoint"] = "recipe"

    def band(self, reference: float) -> tuple[Optional[float], Optional[float]]:
        """Tolerancias absolutas (aviso, alarma) para un valor de referencia."""

        def conv(t: Optional[float]) -> Optional[float]:
            if t is None:
                return None
            return abs(reference) * t / 100.0 if self.mode == "pct" else t

        return conv(self.warn), conv(self.alarm)


class Recipe(BaseModel):
    name: str
    description: str = ""
    # Datos libres del producto: calibre, material, color, etc.
    meta: dict[str, str] = Field(default_factory=dict)
    limits: dict[str, Limit] = Field(default_factory=dict)


CSV_FIELDS = ["variable", "nominal", "warn", "alarm", "mode", "reference"]


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
            reference=(row.get("reference") or "recipe").strip() or "recipe",
        )
    return Recipe(name=name, limits=limits)


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()).strip("_")
    return s or "receta"


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
