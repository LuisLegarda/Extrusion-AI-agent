"""Construcción de los objetos de la aplicación a partir de la carpeta de datos."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .capture import FrameSource, ScreenSource, crop, save_png
from .config import AppConfig, Workspace
from .engine import MonitorEngine
from .ocr import TemplateOcr, create_engine
from .recipes import RecipeStore
from .storage import Historian


@dataclass
class AppContext:
    workspace: Workspace
    config: AppConfig
    recipes: RecipeStore
    engine: MonitorEngine
    template_ocr: TemplateOcr  # siempre disponible para enseñar caracteres
    demo: bool = False


def build(home: Optional[Path] = None, demo: bool = False, source: Optional[FrameSource] = None,
          clock=None, sleep=None) -> AppContext:
    ws = Workspace(home)
    if demo:
        demo_source = setup_demo(ws)
        source = source or demo_source
    config = ws.load_config()
    recipes = RecipeStore(ws.recipes_dir)
    template = TemplateOcr(ws.glyphs_file)
    ocr = template if config.general.ocr_engine == "template" else create_engine(config.general, ws.glyphs_file)
    source = source or ScreenSource(config.general.monitor)
    extra = {k: v for k, v in (("clock", clock), ("sleep", sleep)) if v is not None}
    engine = MonitorEngine(ws, config, recipes, source, ocr, Historian(ws.history_db),
                           clicker=make_clicker(source), **extra)
    state = ws.load_state()
    engine.state.auto_recipe = bool(state.get("auto_recipe", True))
    if state.get("recipe") in recipes.names():
        engine.state.recipe = state["recipe"]
    return AppContext(ws, config, recipes, engine, template, demo)


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
    if not ws.glyphs_file.exists():
        teach_template(TemplateOcr(ws.glyphs_file), sim, config.variables[0].ocr)
    return SimulatorSource(sim)
