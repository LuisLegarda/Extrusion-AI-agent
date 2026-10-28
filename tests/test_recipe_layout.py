"""Posiciones de las variables y recetas: corregir una posición no debe «revertirse» al cargar otra receta."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def ctx(tmp_path):
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.profiles import save_profile
    from extrusion_monitor.recipes import Recipe
    c = build(tmp_path / "home", demo=True)
    c.engine.recipes.save(Recipe(name="OTRA"))
    for n in c.engine.recipes.names():  # como al abrir: cada receta con su copia de la configuración
        save_profile(c.workspace, n, c.engine.config)
    a, b = c.engine.recipes.names()[:2]
    c.engine.set_recipe(a)
    c.other = b
    return c


def _move(ctx, dx=37):
    cfg = ctx.engine.config.model_copy(deep=True)
    cfg.variables[0].region.x += dx
    ctx.workspace.save_config(cfg)
    ctx.engine.reconfigure(cfg)
    return cfg.variables[0].region.x


def test_only_active_recipe_reverts_when_another_is_loaded(ctx):
    """El comportamiento que confundía en el HMI: guardar solo en la receta activa."""
    x = _move(ctx)
    assert ctx.engine.save_profile() is None
    ctx.engine.set_recipe(ctx.other)  # p. ej. el HMI muestra la otra receta (carga automática)
    assert ctx.engine.config.variables[0].region.x == x - 37


def test_saving_to_all_recipes_keeps_the_new_position(ctx):
    e = ctx.engine
    assert e.other_profiles() == [ctx.other]
    x = _move(ctx)
    assert e.save_profile(also=e.other_profiles()) is None
    first = e.state.recipe
    e.set_recipe(ctx.other)
    assert e.config.variables[0].region.x == x
    e.set_recipe(first)
    assert e.config.variables[0].region.x == x


def test_setup_save_asks_and_applies_to_all(ctx):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from extrusion_monitor.ui.main_window import MainWindow
    win = MainWindow(ctx)
    x = _move(ctx)
    win._save_profile(ask_all=True, apply_all=True)
    ctx.engine.set_recipe(ctx.other)
    assert ctx.engine.config.variables[0].region.x == x
    win.close()
