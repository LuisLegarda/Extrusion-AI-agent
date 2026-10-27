"""Respaldos automáticos de la configuración (variables, recetas, recorridos, comportamientos, ajustes).

Se crea uno al abrir una versión nueva del programa (antes de que migre nada) y otro cada `EVERY_DAYS`.
Se guardan fuera de la carpeta del programa, para que sobrevivan si se reemplaza al actualizar.
El historial (`*.sqlite`) y los reportes no se incluyen: son grandes y no se necesitan para volver a operar.
"""
from __future__ import annotations

import json
import os
import time
import zipfile
from pathlib import Path
from typing import Optional

from . import __version__
from .config import APP_NAME

KEEP = 15
EVERY_DAYS = 7
SKIP_SUFFIXES = (".sqlite", ".sqlite-wal", ".sqlite-shm", ".tmp")
SKIP_DIRS = {"reports", "respaldos", "fleet_cache"}
MARKER = "ultima_version.json"


def backups_dir(home: Path) -> Path:
    """%LOCALAPPDATA%\\ExtrusionMonitor\\respaldos (o <datos>/respaldos si no hay LOCALAPPDATA)."""
    env = os.environ.get("EXTRUMON_BACKUPS")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / APP_NAME / "respaldos" if base else Path(home) / "respaldos"


def _files(home: Path):
    for p in sorted(home.rglob("*")):
        rel = p.relative_to(home)
        if not p.is_file() or rel.parts[0] in SKIP_DIRS or p.name.endswith(SKIP_SUFFIXES):
            continue
        yield p, rel


def create_backup(home: Path, reason: str = "manual", dest: Optional[Path] = None) -> Path:
    home = Path(home)
    dest = Path(dest) if dest else backups_dir(home)
    dest.mkdir(parents=True, exist_ok=True)
    name = f"respaldo-{time.strftime('%Y%m%d-%H%M%S')}-v{__version__}-{reason}.zip"
    out = dest / name
    tmp = out.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("respaldo.json", json.dumps({"version": __version__, "reason": reason, "ts": time.time(),
                                                "home": str(home)}, ensure_ascii=False, indent=2))
        for p, rel in _files(home):
            z.write(p, Path("datos") / rel)
    tmp.replace(out)
    return out


def list_backups(home: Path) -> list[Path]:
    d = backups_dir(home)
    return sorted(d.glob("respaldo-*.zip")) if d.is_dir() else []


def prune(home: Path, keep: int = KEEP) -> None:
    for p in list_backups(home)[:-keep]:
        try:
            p.unlink()
        except OSError:
            pass


def restore_backup(zip_path: Path, home: Path) -> int:
    """Copia los archivos del respaldo en la carpeta de datos (con el programa cerrado). Devuelve cuántos."""
    home = Path(home)
    n = 0
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            parts = Path(info.filename).parts
            if info.is_dir() or not parts or parts[0] != "datos" or ".." in parts:
                continue
            target = home.joinpath(*parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(info))
            n += 1
    return n


PENDING = "restaurar_al_abrir.json"


def schedule_restore(zip_path: Path, home: Path) -> None:
    """Deja pendiente la restauración: se aplica al volver a abrir el programa, antes de cargar nada.

    Así ningún archivo que el programa guarda al cerrar (estado, estación…) pisa lo restaurado.
    """
    with zipfile.ZipFile(zip_path) as z:  # que sea un respaldo válido antes de cerrar el programa
        if not any(Path(i.filename).parts[:1] == ("datos",) for i in z.infolist()):
            raise ValueError("el archivo no es un respaldo de la configuración")
    (Path(home) / PENDING).write_text(json.dumps({"zip": str(zip_path), "ts": time.time()}), encoding="utf-8")


def apply_pending_restore(home: Path) -> Optional[int]:
    """Aplica la restauración pendiente (si la hay) con un respaldo previo de lo actual. Devuelve cuántos archivos."""
    marker = Path(home) / PENDING
    if not marker.exists():
        return None
    try:
        zip_path = Path(json.loads(marker.read_text(encoding="utf-8"))["zip"])
        marker.unlink()
        create_backup(home, "antes-de-restaurar")
        return restore_backup(zip_path, home)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        try:
            marker.unlink()
        except OSError:
            pass
        return None


def recover_config(home: Path, valid) -> Optional[Path]:
    """`config.json` no se puede leer: se aparta la copia dañada y se recupera la del respaldo más reciente que
    sí sea válida (`valid(texto)` dice si lo es). Devuelve el respaldo usado, o None si no hubo ninguno."""
    home = Path(home)
    for zp in reversed(list_backups(home)):
        try:
            with zipfile.ZipFile(zp) as z:
                text = z.read("datos/config.json").decode("utf-8")
        except (OSError, KeyError, zipfile.BadZipFile, UnicodeDecodeError):
            continue
        if not valid(text):
            continue
        broken = home / "config.json"
        if broken.exists():
            broken.replace(home / f"config.dañado-{time.strftime('%Y%m%d-%H%M%S')}.json")
        tmp = home / "config.json.tmp"
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(home / "config.json")
        return zp
    return None


def auto_backup(home: Path, now: Optional[float] = None) -> Optional[Path]:
    """Respaldo al cambiar de versión o si el último tiene más de EVERY_DAYS. Nunca detiene el programa."""
    home = Path(home)
    now = time.time() if now is None else now
    marker = home / MARKER
    try:
        last = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
    except (OSError, ValueError):
        last = {}
    has_data = (home / "config.json").exists()
    reason = None
    if has_data and last.get("version") != __version__:
        reason = f"desde-v{last['version']}" if last.get("version") else "inicial"
    elif has_data and now - float(last.get("backup_ts") or 0) > EVERY_DAYS * 86400:
        reason = "semanal"
    out = None
    try:
        if reason:
            out = create_backup(home, reason)
            prune(home)
        marker.write_text(json.dumps({"version": __version__, "backup_ts": now if out else last.get("backup_ts", 0)}),
                          encoding="utf-8")
    except OSError:
        return None
    return out
