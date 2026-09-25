from extrusion_monitor.acquisition import Reading
from extrusion_monitor.analysis.rules import R_READ, R_RECIPE, R_TOL, Level, RuleEngine
from extrusion_monitor.analysis.trends import TrendTracker
from extrusion_monitor.config import AppConfig, GeneralSettings, Rect, Variable
from extrusion_monitor.recipes import Limit, Recipe

R = Rect(x=0, y=0, w=10, h=10)


def make():
    cfg = AppConfig(
        general=GeneralSettings(debounce_samples=2, read_fail_samples=3),
        variables=[
            Variable(id="sp", name="Zona SP", kind="setpoint", region=R),
            Variable(id="pv", name="Zona", kind="actual", setpoint_var="sp", region=R),
        ])
    recipe = Recipe(name="R1", limits={
        "sp": Limit(nominal=180, warn=1, alarm=3),
        "pv": Limit(nominal=180, warn=3, alarm=6),
    })
    return cfg, recipe, RuleEngine(cfg), TrendTracker(600, 30)


def readings(now, sp, pv, ok=True):
    return {"sp": Reading("sp", value=sp, ts=now, ok=ok), "pv": Reading("pv", value=pv, ts=now, ok=ok)}


def test_setpoint_mismatch_debounced_and_cleared():
    cfg, recipe, eng, tr = make()
    _, ev = eng.evaluate(0, readings(0, 186, 180), recipe, tr)
    assert not eng.active_findings()  # aún sin confirmar
    _, ev = eng.evaluate(1, readings(1, 186, 180), recipe, tr)
    f = eng.active_findings()
    assert [x.rule for x in f] == [R_RECIPE] and f[0].level == Level.ALARM
    assert any(e.kind == "raised" for e in ev)
    eng.evaluate(2, readings(2, 180, 180), recipe, tr)
    _, ev = eng.evaluate(3, readings(3, 180, 180), recipe, tr)
    assert not eng.active_findings()
    assert any(e.kind == "cleared" for e in ev)


def test_setpoint_change_event():
    cfg, recipe, eng, tr = make()
    eng.evaluate(0, readings(0, 180, 180), recipe, tr)
    _, ev = eng.evaluate(1, readings(1, 185, 180), recipe, tr)
    ch = [e for e in ev if e.kind == "setpoint_change"]
    assert ch and ch[0].level == Level.WARN and "180 → 185" in ch[0].message


def test_actual_against_live_setpoint():
    cfg, recipe, eng, tr = make()
    recipe.limits["pv"].reference = "setpoint"
    recipe.limits["sp"] = Limit(nominal=190, warn=100, alarm=100)
    for t in range(3):
        st, _ = eng.evaluate(t, readings(t, 190, 189), recipe, tr)
    assert st["pv"].ref_source == "consigna" and st["pv"].level == Level.OK
    for t in range(3, 6):
        st, _ = eng.evaluate(t, readings(t, 190, 182), recipe, tr)
    assert st["pv"].level == Level.ALARM
    assert any(f.rule == R_TOL for f in eng.active_findings())


def test_percent_tolerance():
    lim = Limit(nominal=200, warn=2, alarm=5, mode="pct")
    assert lim.band(200) == (4.0, 10.0)


def test_read_failure_and_stale():
    cfg, recipe, eng, tr = make()
    rd = readings(0, 180, 180)
    rd["pv"].fail_count = 3
    rd["pv"].ok = False
    eng.evaluate(0, rd, recipe, tr)
    assert any(f.rule == R_READ and f.var_id == "pv" for f in eng.active_findings())


def test_not_visible_keeps_finding():
    cfg, recipe, eng, tr = make()
    for t in range(2):
        eng.evaluate(t, readings(t, 186, 180), recipe, tr)
    assert eng.active_findings()
    for t in range(2, 100, 10):
        rd = readings(0, 186, 180)  # dato viejo
        for r in rd.values():
            r.visible = False
        eng.evaluate(t, rd, recipe, tr)
    assert any(f.rule == R_RECIPE for f in eng.active_findings())
