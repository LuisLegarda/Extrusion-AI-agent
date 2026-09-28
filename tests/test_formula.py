import pytest

from extrusion_monitor.analysis.formula import FormulaError, compile_formula, evaluation_order


def test_basic_and_braces():
    f = compile_formula("{vel} / rpm * 2", {"vel", "rpm"})
    assert f.deps == ["vel", "rpm"]
    assert f.evaluate({"vel": 350, "rpm": 50}) == pytest.approx(14)


def test_functions_and_conditions():
    f = compile_formula("max(z1, z2, z3) - min(z1, z2, z3)", {"z1", "z2", "z3"})
    assert f.evaluate({"z1": 160, "z2": 175, "z3": 170}) == 15
    g = compile_formula("si(vel > 0, carga / vel, 0)", {"vel", "carga"})
    assert g.evaluate({"vel": 0, "carga": 65}) == 0
    assert compile_formula("vel / rpm", {"vel", "rpm"}).evaluate({"vel": 1, "rpm": 0}) is None


@pytest.mark.parametrize("bad", ["__import__('os')", "open('x')", "vel.real", "[1, 2]", "desconocida + 1", ""])
def test_rejects_unsafe_or_unknown(bad):
    with pytest.raises(FormulaError):
        compile_formula(bad, {"vel"})


def test_order_and_cycles():
    fs = {"a": compile_formula("b + 1", {"b", "x"}), "b": compile_formula("x * 2", {"x"})}
    assert evaluation_order(fs) == ["b", "a"]
    cyc = {"a": compile_formula("b", {"b"}), "b": compile_formula("a", {"a"})}
    with pytest.raises(FormulaError):
        evaluation_order(cyc)


def test_formula_variable_in_engine(tmp_path):
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.config import Rect, Variable
    from extrusion_monitor.recipes import Limit
    from extrusion_monitor.simulator import HmiSimulator, Scenario, SimulatorSource
    t = [1000.0]
    clk = lambda: t[0]  # noqa: E731
    sim = HmiSimulator(scenario=Scenario(period=1e6), clock=clk)
    ctx = build(tmp_path, demo=True, source=SimulatorSource(sim), clock=clk, sleep=lambda s: None)
    cfg = ctx.config
    cfg.variables.append(Variable(id="rango_t", name="Rango temperaturas", kind="formula",
                                  region=Rect(x=0, y=0, w=1, h=1), formula="max(z1, z2, z3) - min(z1, z2, z3)"))
    assert not cfg.validate_references()
    ctx.engine.reconfigure(cfg)
    recipe = ctx.recipes.get(ctx.recipes.names()[0])
    recipe.limits["rango_t"] = Limit(nominal=20, warn=3, alarm=6)
    from extrusion_monitor.profiles import save_profile
    save_profile(ctx.workspace, recipe.name, cfg)  # la receta es un perfil completo: incluye la fórmula
    for _ in range(3):
        snap = ctx.engine.step()
        t[0] += 1
    st = snap.statuses["rango_t"]
    assert st.reading.value == pytest.approx(20, abs=3)
    assert st.reference == 20 and st.level is not None
