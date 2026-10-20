"""Personal de la estación: operadores y supervisores (no dependen de la receta).

Se guarda en `<datos>/personal/personal.json` y viaja con los respaldos. El usuario en turno (uno solo:
operador o supervisor) se guarda en el estado del equipo (`state.json` → `crew`).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

ROLES = {"operator": "Operador", "supervisor": "Supervisor"}


@dataclass
class Person:
    name: str
    role: str = "operator"  # operator | supervisor
    badge: str = ""  # número de empleado o gafete (opcional)
    active: bool = True


@dataclass
class Personnel:
    people: list[Person] = field(default_factory=list)

    @staticmethod
    def file(home: Path) -> Path:
        return Path(home) / "personal" / "personal.json"

    @classmethod
    def load(cls, home: Path) -> "Personnel":
        try:
            data = json.loads(cls.file(home).read_text(encoding="utf-8"))
            people = []
            for d in data.get("people", []):
                name = str(d.get("name", "")).strip()
                if name:
                    role = d.get("role") if d.get("role") in ROLES else "operator"
                    people.append(Person(name, role, str(d.get("badge", "")), bool(d.get("active", True))))
            return cls(people)
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()

    def save(self, home: Path) -> None:
        f = self.file(home)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"people": [asdict(p) for p in self.people]}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(f)

    def names(self, roles: Iterable[str] = ("operator", "supervisor")) -> list[str]:
        roles = set(roles)
        return [p.name for p in self.people if p.active and p.role in roles]

    def find(self, name: str) -> Optional[Person]:
        return next((p for p in self.people if p.name == name), None)


def capture_names(home: Path, recipe_operators: Iterable[str]) -> list[str]:
    """Quién puede capturar paros y defectos: el personal activo y, por compatibilidad, la lista de la receta."""
    return list(dict.fromkeys([*Personnel.load(home).names(), *(o for o in recipe_operators if o)]))


def crew(state: dict) -> dict:
    """Usuario en turno (operador o supervisor) guardado en el estado del equipo."""
    c = state.get("crew") or {}
    user = str(c.get("user") or c.get("operator") or "")  # «operator»: formato anterior
    return {"user": user, "role": str(c.get("role") or ("operator" if user else ""))}
