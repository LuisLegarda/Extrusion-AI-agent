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


def build(home: Optional[Path] = None, demo: bool = False,
          source: Optional[FrameSource] = None) -> AppContext:
    ws = Workspace(home)
    if demo:
        demo_source = setup_demo(ws)
        source = source or demo_source
    config = ws.load_config()
    recipes = RecipeStore(ws.recipes_dir)
    template = TemplateOcr(ws.glyphs_file)
    ocr = template if config.general.ocr_engine == "template" else create_engine(config.general, ws.glyphs_file)
    source = source or ScreenSource(config.general.monitor)
    engine = MonitorEngine(ws, config, recipes, source, ocr, Historian(ws.history_db))
    state = ws.load_state()
    engine.state.auto_recipe = bool(state.get("auto_recipe", True))
    if state.get("recipe") in recipes.names():
        engine.state.recipe = state["recipe"]
    return AppContext(ws, config, recipes, engine, template, demo)


def make_ocr(ctx: AppContext):
    g = ctx.config.general
    return ctx.template_ocr if g.ocr_engine == "template" else create_engine(g, ctx.workspace.glyphs_file)


def setup_demo(ws: Workspace):
    """Prepara una carpeta de datos con la configuración del HMI simulado."""
    from .simulator import HmiSimulator, SimulatorSource, demo_config, demo_recipe, teach_template

    sim = HmiSimulator()
    config = demo_config()
    if not ws.config_file.exists():
        ws.save_config(config)
    else:
        config = ws.load_config()
    recipes = RecipeStore(ws.recipes_dir)
    if not recipes.names():
        recipes.save(demo_recipe())
    frame = sim.render()
    for page in config.pages:
        if page.anchor is not None and not ws.page_anchor_file(page.id).exists():
            save_png(ws.page_anchor_file(page.id), crop(frame, page.anchor))
    if not ws.glyphs_file.exists():
        teach_template(TemplateOcr(ws.glyphs_file), sim, config.variables[0].ocr)
    return SimulatorSource(sim)
