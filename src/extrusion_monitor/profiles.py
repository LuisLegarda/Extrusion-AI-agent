"""Recetas como perfil completo: cada receta guarda toda la configuración del programa.

Un perfil es la carpeta ``recipes/<receta>.profile/`` con:
config.json (variables, regiones, pestañas, recorridos, OEE, reportes, ajustes),
behaviors.json (comportamientos entrenados), glyphs.json (caracteres enseñados)
y las imágenes de anclas, clics y estados de selector.
Al cargar la receta el perfil reemplaza la configuración activa.
"""
from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Optional

from .config import AppConfig, Workspace
from .recipes import RecipeStore, recipe_slug

log = logging.getLogger(__name__)

ASSET_DIRS = ("pages", "clicks", "selectors")
FILES = ("config.json", "behaviors.json", "glyphs.json")


def profile_dir(ws: Workspace, recipe_name: str) -> Path:
    return ws.recipes_dir / f"{recipe_slug(recipe_name)}.profile"


def has_profile(ws: Workspace, recipe_name: str) -> bool:
    return (profile_dir(ws, recipe_name) / "config.json").exists()


def _replace_dir(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    if src.exists():
        shutil.copytree(src, dst)
    else:
        dst.mkdir(parents=True, exist_ok=True)


def save_profile(ws: Workspace, recipe_name: str, config: Optional[AppConfig] = None) -> Path:
    """Copia la configuración activa (y sus imágenes) al perfil de la receta."""
    dest = profile_dir(ws, recipe_name)
    tmp = dest.with_name(dest.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    if config is not None:
        (tmp / "config.json").write_text(config.model_dump_json(indent=2), encoding="utf-8")
    elif ws.config_file.exists():
        shutil.copy2(ws.config_file, tmp / "config.json")
    for name in ("behaviors.json", "glyphs.json"):
        src = ws.home / name
        if src.exists():
            shutil.copy2(src, tmp / name)
    for d in ASSET_DIRS:
        _replace_dir(ws.home / d, tmp / d)
    (tmp / "profile.json").write_text(json.dumps({"recipe": recipe_name, "saved_at": time.time()}),
                                      encoding="utf-8")
    # Reemplazo en dos pasos: en Windows no se puede renombrar sobre una carpeta existente y
    # borrarla puede fallar si algún archivo está abierto; el perfil nuevo queda siempre en su lugar.
    old = dest.with_name(dest.name + ".old")
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)
    if dest.exists():
        dest.rename(old)
    tmp.rename(dest)
    shutil.rmtree(old, ignore_errors=True)
    return dest


def apply_profile(ws: Workspace, recipe_name: str) -> Optional[AppConfig]:
    """Reemplaza la configuración activa por la del perfil. Devuelve la nueva configuración."""
    src = profile_dir(ws, recipe_name)
    cfg_file = src / "config.json"
    if not cfg_file.exists():
        return None
    config = AppConfig.model_validate_json(cfg_file.read_text(encoding="utf-8"))
    for d in ASSET_DIRS:
        _replace_dir(src / d, ws.home / d)
    for name in ("behaviors.json", "glyphs.json"):
        if (src / name).exists():
            shutil.copy2(src / name, ws.home / name)
    ws.save_config(config)
    return config


def copy_profile(ws: Workspace, src_recipe: str, dst_recipe: str) -> None:
    src, dst = profile_dir(ws, src_recipe), profile_dir(ws, dst_recipe)
    if src.exists():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)


def delete_profile(ws: Workspace, recipe_name: str) -> None:
    d = profile_dir(ws, recipe_name)
    if d.exists():
        shutil.rmtree(d)


def ensure_profiles(ws: Workspace, store: RecipeStore) -> None:
    """Recetas antiguas sin perfil: se les asigna la configuración actual."""
    for name in store.names():
        if not has_profile(ws, name):
            try:
                save_profile(ws, name)
            except OSError:
                log.exception("No se pudo crear el perfil de %s", name)
