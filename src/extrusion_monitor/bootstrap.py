"""Construcción de los objetos de la aplicación a partir de la carpeta de datos."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .capture import FrameSource, ScreenSource, crop, save_png
from .config import AppConfig, Workspace
from .engine import MonitorEngine
from .ocr import TemplateOcr, create_engine
from .profiles import ensure_profiles
from .recipes import RecipeStore
from .storage import Historian

if TYPE_CHECKING:
    from .exporter import FleetExporter

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    workspace: Workspace
    config: AppConfig
    recipes: RecipeStore
    engine: MonitorEngine
    template_ocr: TemplateOcr  # siempre disponible para enseñar caracteres
    demo: bool = False
    exporter: Optional["FleetExporter"] = None  # estado de la línea para el dashboard global
    notifier: Optional[object] = None  # avisos por correo / mensajes (lo crea la ventana principal una sola vez)
    recovered: Optional[str] = None  # respaldo con que se recuperó una configuración dañada (se avisa al abrir)


def build(home: Optional[Path] = None, demo: bool = False, source: Optional[FrameSource] = None,
          clock=None, sleep=None) -> AppContext:
    ws = Workspace(home)
    if not demo:
        from .backup import apply_pending_restore, auto_backup
        apply_pending_restore(ws.home)  # «Restaurar respaldo…» pedido antes de cerrar
        auto_backup(ws.home)  # antes de cargar (y migrar) la configuración
    if demo:
        demo_source = setup_demo(ws)
        source = source or demo_source
    recovered = None
    try:
        config = ws.load_config()
    except ValueError:  # config.json dañado (p. ej. un apagón al guardar): se recupera del último respaldo válido
        if demo:
            raise
        from .backup import recover_config

        def valid(text: str) -> bool:
            try:
                AppConfig.model_validate_json(text)
                return True
            except ValueError:
                return False

        used = recover_config(ws.home, valid)
        if used is None:
            raise
        log.warning("config.json dañado: se recuperó de %s", used)
        recovered = used.name
        config = ws.load_config()
    recipes = RecipeStore(ws.recipes_dir)
    template = TemplateOcr(ws.glyphs_file)
    ocr = template if config.general.ocr_engine == "template" else create_engine(config.general, ws.glyphs_file)
    source = source or ScreenSource(config.general.monitor)
    extra = {k: v for k, v in (("clock", clock), ("sleep", sleep)) if v is not None}
    from .exporter import load_station
    history = Historian(ws.history_db, retention_days=load_station(ws).history_days)
    engine = MonitorEngine(ws, config, recipes, source, ocr, history,
                           clicker=make_clicker(source), **extra)
    ensure_profiles(ws, recipes)
    state = ws.load_state()
    engine.state.auto_recipe = bool(state.get("auto_recipe", True))
    if state.get("recipe") in recipes.names():
        engine.state.recipe = state["recipe"]
    from .exporter import FleetExporter
    return AppContext(ws, config, recipes, engine, template, demo, FleetExporter(engine, ws), recovered=recovered)


def make_clicker(source: FrameSource):
    """Clics del recorrido: sobre el simulador en la demo, reales en Windows, o ninguno."""
    sim = getattr(source, "sim", None)
    if sim is not None:
        from .simulator import SimClicker
        return SimClicker(sim)
    import sys
    if sys.platform == "win32" and isinstance(source, ScreenSource):
        from .navigation import WindowsClicker
        return WindowsClicker(source.offset())
    from .navigation import UnavailableClicker
    return UnavailableClicker()


def make_ocr(ctx: AppContext):
    g = ctx.config.general
    return ctx.template_ocr if g.ocr_engine == "template" else create_engine(g, ctx.workspace.glyphs_file)


def setup_demo(ws: Workspace):
    """Prepara una carpeta de datos con la configuración del HMI simulado."""
    from .simulator import (HmiSimulator, SimulatorSource, demo_click_patches, demo_config, demo_recipe,
                            teach_template)

    sim = HmiSimulator()
    config = demo_config()
    if not ws.config_file.exists():
        ws.save_config(config)
    else:
        config = ws.load_config()
    recipes = RecipeStore(ws.recipes_dir)
    if not recipes.names():
        recipes.save(demo_recipe())
    for page in config.pages:
        if page.anchor is not None and not ws.page_anchor_file(page.id).exists():
            saved, sim.page = sim.page, page.id
            save_png(ws.page_anchor_file(page.id), crop(sim.render(), page.anchor))
            sim.page = saved
    for cid, patch in demo_click_patches(sim, config).items():
        if not ws.click_patch_file(cid).exists():
            save_png(ws.click_patch_file(cid), patch)
    for v in config.variables:
        if v.kind == "selector" and v.id == "inyeccion":
            for st in v.states:
                f = ws.selector_state_file(v.id, st)
                if not f.exists():
                    save_png(f, sim.selector_image(st))
    if not ws.glyphs_file.exists():
        teach_template(TemplateOcr(ws.glyphs_file), sim, config.variables[0].ocr)
    return SimulatorSource(sim)
