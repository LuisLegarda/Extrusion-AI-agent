"""Personal de la estación: operadores y supervisores, turnos y confirmación del usuario (no dependen de la receta).

Se guarda en `<datos>/personal/personal.json` y viaja con los respaldos. El usuario en turno (uno solo:
operador o supervisor) se guarda en el estado del equipo (`state.json` → `crew`).

Las contraseñas no se guardan: solo su huella PBKDF2-SHA256 con sal propia por persona.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

ROLES = {"operator": "Operador", "supervisor": "Supervisor"}
CONFIRM_MODES = {"none": "Sin confirmación", "badge": "Número de empleado",
                 "badge_password": "Número de empleado y contraseña"}
PBKDF2_ROUNDS = 120_000
# Acciones que pueden requerir el inicio de sesión de un supervisor (clave -> descripción)
PROTECTABLE = {
    "personnel": "Lista de personal, turnos y esta protección",
    "recipes": "Cambiar la receta activa, editar recetas y límites",
    "setup": "Variables, pantallas, recorridos, cámaras y configuración del control (Configurar receta)",
    "charts": "Tablero de Inicio y dock (indicadores y gráficos)",
    "analysis": "Selección de variables (SPC, correlación, Variables en vivo) y modelo de estabilidad mostrado",
    "notify": "Notificaciones por correo y mensajes",
    "backups": "Respaldos, guardado y carpeta de datos (ver, crear, restaurar o exportar)",
    "control": "Modo de los lazos de control y activar el control automático",
    "catalogs": "Causas de paro y defectos, y entrenar el comportamiento normal",
    "delete": "Eliminar capturas de paros y defectos",
    "station": "Identidad de la estación, exportación al dashboard global, servidor y vistas del programa",
    "stop": "Detener el monitoreo y cerrar el programa",
}
DEFAULT_PROTECT = ["personnel", "recipes", "setup", "charts", "analysis", "notify", "station", "control", "catalogs",
                   "backups"]
PROTECT_VERSION = 4  # al agregar acciones protegibles nuevas que van protegidas por defecto


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """«sal$huella» en hexadecimal."""
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"{salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        expected = bytes.fromhex(digest_hex)
        got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ROUNDS)
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(got, expected)


def _minutes(hhmm: str) -> Optional[int]:
    try:
        h, m = (int(x) for x in str(hhmm).strip().split(":"))
    except (ValueError, AttributeError):
        return None
    return h * 60 + m if 0 <= h <= 23 and 0 <= m <= 59 else None


@dataclass
class Person:
    name: str
    role: str = "operator"  # operator | supervisor
    badge: str = ""  # número de empleado o gafete
    active: bool = True
    shift: str = ""  # nombre del turno asignado ("" = cualquiera)
    password: str = ""  # huella de la contraseña ("" = sin contraseña)


@dataclass
class Shift:
    name: str
    start: str = "06:00"  # hh:mm
    end: str = "14:00"  # hh:mm; si es menor que el inicio, termina al día siguiente

    def contains(self, t: dt.datetime) -> bool:
        a, b = _minutes(self.start), _minutes(self.end)
        if a is None or b is None or a == b:
            return False
        m = t.hour * 60 + t.minute
        return a <= m < b if a < b else (m >= a or m < b)

    def label(self) -> str:
        return f"{self.name} ({self.start}–{self.end})"


@dataclass
class LoginSettings:
    auto_shift: bool = False  # al empezar cada turno, pedir quién entra
    confirm: str = "none"  # none | badge | badge_password (también al elegir usuario en la barra superior)
    protect: list[str] = field(default_factory=lambda: list(DEFAULT_PROTECT))
    session_min: int = 10  # minutos que dura la sesión de supervisor sin usarse

    def listed(self, key: str) -> bool:
        """La acción está en la lista protegida (la de personal siempre)."""
        return key == "personnel" or key in self.protect


@dataclass
class Personnel:
    people: list[Person] = field(default_factory=list)
    shifts: list[Shift] = field(default_factory=list)
    login: LoginSettings = field(default_factory=LoginSettings)

    @staticmethod
    def file(home: Path) -> Path:
        return Path(home) / "personal" / "personal.json"

    @classmethod
    def load(cls, home: Path) -> "Personnel":
        try:
            data = json.loads(cls.file(home).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        people = []
        for d in data.get("people", []) or []:
            try:
                name = str(d.get("name", "")).strip()
                if name:
                    role = d.get("role") if d.get("role") in ROLES else "operator"
                    people.append(Person(name, role, str(d.get("badge", "")).strip(), bool(d.get("active", True)),
                                         str(d.get("shift", "")), str(d.get("password", ""))))
            except AttributeError:
                continue
        shifts = []
        for d in data.get("shifts", []) or []:
            try:
                if str(d.get("name", "")).strip():
                    shifts.append(Shift(str(d["name"]).strip(), str(d.get("start", "06:00")),
                                        str(d.get("end", "14:00"))))
            except AttributeError:
                continue
        lg = data.get("login") or {}
        protect = lg.get("protect")
        protect = [k for k in protect if k in PROTECTABLE] if isinstance(protect, list) else list(DEFAULT_PROTECT)
        version = int(lg.get("protect_version", 1) or 1)
        for key, since in (("analysis", 2), ("notify", 3), ("station", 4), ("control", 4), ("catalogs", 4),
                           ("backups", 4)):  # nuevas: protegidas por defecto
            if version < since and key not in protect:
                protect.append(key)
        try:
            session_min = max(1, min(240, int(lg.get("session_min", 10))))
        except (TypeError, ValueError):
            session_min = 10
        login = LoginSettings(bool(lg.get("auto_shift", False)),
                              lg.get("confirm") if lg.get("confirm") in CONFIRM_MODES else "none",
                              protect, session_min)
        return cls(people, shifts, login)

    def save(self, home: Path) -> None:
        f = self.file(home)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".json.tmp")
        data = {"people": [asdict(p) for p in self.people], "shifts": [asdict(s) for s in self.shifts],
                "login": {**asdict(self.login), "protect_version": PROTECT_VERSION}}
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(f)

    def names(self, roles: Iterable[str] = ("operator", "supervisor")) -> list[str]:
        roles = set(roles)
        return [p.name for p in self.people if p.active and p.role in roles]

    def find(self, name: str) -> Optional[Person]:
        return next((p for p in self.people if p.name == name), None)

    def protects(self, key: str) -> bool:
        """Protegida: en la lista y hay al menos un supervisor que puede iniciar sesión (si no, nadie podría)."""
        return self.login.listed(key) and bool(self.supervisors_ready())

    def supervisors_ready(self) -> list[Person]:
        """Supervisores activos que pueden iniciar sesión (número de empleado y contraseña)."""
        return [p for p in self.people if p.active and p.role == "supervisor" and p.badge and p.password]

    def supervisor_login(self, badge: str, password: str) -> Optional[Person]:
        p = next((x for x in self.supervisors_ready() if x.badge == badge.strip()), None)
        return p if p is not None and check_password(password, p.password) else None

    def current_shift(self, now: float) -> Optional[Shift]:
        t = dt.datetime.fromtimestamp(now)
        return next((s for s in self.shifts if s.contains(t)), None)

    def shift_people(self, shift: Optional[Shift]) -> list[str]:
        """Personas activas del turno (las que no tienen turno asignado entran en todos)."""
        return [p.name for p in self.people if p.active and (shift is None or p.shift in ("", shift.name))]

    def verify(self, name: str, badge: str, password: str = "") -> Optional[str]:
        """None si la confirmación es válida; si no, el motivo (para mostrarlo)."""
        mode = self.login.confirm
        if mode == "none":
            return None
        p = self.find(name)
        if p is None or not p.active:
            return "Elige a la persona que entra."
        if not p.badge:
            return "Esa persona no tiene número de empleado: asígnalo en Configuración → Personal."
        if badge.strip() != p.badge:
            return "El número de empleado no corresponde."
        if mode == "badge_password":
            if not p.password:
                return "Esa persona no tiene contraseña: asígnala en Configuración → Personal."
            if not check_password(password, p.password):
                return "La contraseña no es correcta."
        return None


def capture_names(home: Path, recipe_operators: Iterable[str]) -> list[str]:
    """Quién puede capturar paros y defectos: el personal activo y, por compatibilidad, la lista de la receta."""
    return list(dict.fromkeys([*Personnel.load(home).names(), *(o for o in recipe_operators if o)]))


def crew(state: dict) -> dict:
    """Usuario en turno (operador o supervisor) y vuelta de turno confirmada, guardados en el estado del equipo."""
    c = state.get("crew") or {}
    user = str(c.get("user") or c.get("operator") or "")  # «operator»: formato anterior
    return {"user": user, "role": str(c.get("role") or ("operator" if user else "")),
            "shift_key": str(c.get("shift_key") or "")}


def shift_key(shift: Shift, now: float) -> str:
    """Identifica una vuelta concreta del turno (el nocturno que cruza la medianoche cuenta desde su inicio)."""
    t = dt.datetime.fromtimestamp(now)
    a = _minutes(shift.start) or 0
    day = t.date() if t.hour * 60 + t.minute >= a else t.date() - dt.timedelta(days=1)
    return f"{shift.name}@{day.isoformat()}"
