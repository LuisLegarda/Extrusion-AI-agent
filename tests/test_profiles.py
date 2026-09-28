from extrusion_monitor import profiles
from extrusion_monitor.bootstrap import build
from extrusion_monitor.recipes import Recipe
from extrusion_monitor.simulator import HmiSimulator, Scenario, SimulatorSource


def make(tmp_path):
    t = [1000.0]
    clk = lambda: t[0]  # noqa: E731
    sim = HmiSimulator(scenario=Scenario(period=1e6), clock=clk)
    ctx = build(tmp_path, demo=True, source=SimulatorSource(sim), clock=clk, sleep=lambda s: None)
    return ctx, sim, t


def test_existing_recipes_get_profile(tmp_path):
    ctx, _, _ = make(tmp_path)
    name = ctx.recipes.names()[0]
    assert profiles.has_profile(ctx.workspace, name)
    assert (profiles.profile_dir(ctx.workspace, name) / "pages").exists()


def test_switching_recipe_restores_full_configuration(tmp_path):
    ctx, sim, t = make(tmp_path)
    ws, eng = ctx.workspace, ctx.engine
    base = ctx.recipes.names()[0]
    eng.set_recipe(base)
    # Receta B: misma línea con otra configuración (menos variables, OEE apagado).
    cfg_b = ctx.config.model_copy(deep=True)
    cfg_b.variables = [v for v in cfg_b.variables if v.page == "principal" or v.id == "receta_hmi"]
    cfg_b.oee.enabled = False
    ctx.recipes.save(Recipe(name="B"))
    profiles.save_profile(ws, "B", cfg_b)
    eng.state.auto_recipe = False
    v0 = eng.config_version
    eng.set_recipe("B")
    assert eng.config_version == v0 + 1
    assert len(eng.config.variables) == len(cfg_b.variables) and not eng.config.oee.enabled
    assert ws.load_config().oee.enabled is False  # la configuración activa quedó reemplazada
    eng.set_recipe(base)
    assert eng.config.oee.enabled and len(eng.config.variables) > len(cfg_b.variables)


def test_auto_recipe_missing_is_notified_and_kept(tmp_path):
    ctx, sim, t = make(tmp_path)
    eng = ctx.engine
    eng.step()
    t[0] += 1
    current = eng.state.recipe
    sim.recipe_name = "NOEXISTE-99"
    events = []
    for _ in range(3):
        events += eng.step().events
        t[0] += 1
    assert eng.state.recipe == current
    missing = [e for e in events if e.kind == "recipe_missing"]
    assert len(missing) == 1 and "NOEXISTE-99" in missing[0].message
