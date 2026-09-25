"""Simulador → captura → OCR → reglas → historial."""
from extrusion_monitor.analysis.rules import R_RECIPE, R_TOL, Level
from extrusion_monitor.bootstrap import build
from extrusion_monitor.simulator import HmiSimulator, Scenario, SimulatorSource


def run(tmp_path, seconds, scenario=None):
    t = [1000.0]
    clk = lambda: t[0]  # noqa: E731
    sim = HmiSimulator(scenario=scenario, clock=clk)
    ctx = build(tmp_path, demo=True, source=SimulatorSource(sim))
    ctx.engine.clock = clk
    snaps = []
    for _ in range(seconds):
        snaps.append(ctx.engine.step())
        t[0] += 1
    return ctx, sim, snaps


def test_reads_all_values_and_selects_recipe(tmp_path):
    ctx, sim, snaps = run(tmp_path, 5, scenario=Scenario(period=10_000))
    last = snaps[-1]
    assert last.recipe == "THHN-12AWG-NEGRO"
    assert last.read_ok == last.read_total == len(ctx.config.variables)
    assert last.statuses["z1_sp"].reading.value == 160
    assert abs(last.statuses["diam"].reading.value - 3.20) < 0.05


def test_detects_wrong_setpoint_and_drift(tmp_path):
    ctx, sim, snaps = run(tmp_path, 420)
    events = [e for s in snaps for e in s.events]
    assert any(e.kind == "setpoint_change" and e.var_id == "z3_sp" for e in events)
    raised = {(e.rule, e.var_id) for e in events if e.kind == "raised"}
    assert (R_RECIPE, "z3_sp") in raised
    assert (R_TOL, "z3") in raised
    assert any(r == R_TOL and v == "diam" for r, v in raised)
    # Durante la fase estable inicial no hay alarmas.
    early = [e for s in snaps[:55] for e in s.events if e.level >= Level.WARN]
    assert not early
    rows = ctx.engine.historian.samples("z1", 0)
    assert len(rows) > 400


def test_page_not_visible(tmp_path):
    ctx, sim, _ = run(tmp_path, 3, scenario=Scenario(period=10_000))
    import numpy as np
    ctx.engine.source = type("Blank", (), {"grab": lambda self: np.zeros((800, 1280, 3), np.uint8)})()
    snap = ctx.engine.step()
    assert snap.pages == set()
    assert all(not st.reading.visible for st in snap.statuses.values())
    assert not any(f.rule == R_TOL for f in snap.findings)
