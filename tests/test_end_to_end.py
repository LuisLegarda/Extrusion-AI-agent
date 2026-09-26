"""Simulador → recorrido por pestañas → OCR → reglas → historial."""
import numpy as np

from extrusion_monitor.analysis.rules import R_RECIPE, R_TOL, Level
from extrusion_monitor.bootstrap import build
from extrusion_monitor.simulator import HmiSimulator, Scenario, SimulatorSource


class FakeTime:
    def __init__(self):
        self.t = 1000.0

    def clock(self):
        return self.t

    def sleep(self, s):
        self.t += s


def run(tmp_path, seconds, scenario=None):
    ft = FakeTime()
    sim = HmiSimulator(scenario=scenario, clock=ft.clock)
    ctx = build(tmp_path, demo=True, source=SimulatorSource(sim), clock=ft.clock, sleep=ft.sleep)
    snaps = []
    while ft.t < 1000 + seconds:
        snaps.append(ctx.engine.step())
        ft.t += 1
    return ctx, sim, snaps, ft


def test_tour_reads_every_page_and_returns_home(tmp_path):
    ctx, sim, snaps, _ = run(tmp_path, 5, scenario=Scenario(period=10_000))
    first = snaps[0]
    assert first.tour is not None and first.tour.ok, first.tour
    assert first.tour.pages_read == ["ext1", "linea"]
    assert sim.page == "principal"
    last = snaps[-1]
    assert last.recipe == "THHN-12AWG-NEGRO"
    for v in ctx.config.variables:
        assert last.statuses[v.id].reading.ts is not None, v.id
        assert last.statuses[v.id].fresh, v.id
    assert last.statuses["z1_sp"].reading.value == 160
    assert abs(last.statuses["diam"].reading.value - 3.20) < 0.05
    assert last.pages == {"principal"}


def test_detects_wrong_setpoint_and_drift(tmp_path):
    ctx, sim, snaps, _ = run(tmp_path, 430)
    events = [e for s in snaps for e in s.events]
    assert any(e.kind == "setpoint_change" and e.var_id == "z3_sp" for e in events)
    raised = {(e.rule, e.var_id) for e in events if e.kind == "raised"}
    assert (R_RECIPE, "z3_sp") in raised
    assert (R_TOL, "z3") in raised
    assert any(r == R_TOL and v == "diam" for r, v in raised)
    early = [e for s in snaps[:50] for e in s.events if e.level >= Level.WARN]
    assert not early, early
    assert len(ctx.engine.historian.samples("diam", 0)) > 300  # pantalla principal: cada ciclo
    assert 15 < len(ctx.engine.historian.samples("z1", 0)) < 60  # pestaña del recorrido


def test_tour_postponed_when_operator_active(tmp_path):
    ctx, sim, snaps, ft = run(tmp_path, 2, scenario=Scenario(period=10_000))
    ctx.engine.clicker.operator_input()
    ctx.engine.run_tour_now()
    snap = ctx.engine.step()
    assert snap.tour.skipped and "operador" in snap.tour.message
    assert sim.page == "principal"


def test_tour_aborts_if_button_changed(tmp_path):
    ctx, sim, snaps, ft = run(tmp_path, 2, scenario=Scenario(period=10_000))
    ft.t += 100
    orig = sim.render

    def tampered():
        img = orig()
        if sim.page == "principal":
            img[740:780, 230:330] = 255  # el botón EXT1 ya no se ve igual
        return img

    sim.render = tampered
    ctx.engine.run_tour_now()
    n = len(sim.clicks)
    snap = ctx.engine.step()
    assert not snap.tour.ok and "no coincide" in snap.tour.message
    assert len(sim.clicks) == n  # no se hizo ningún clic
    assert any(e.level == Level.WARN and e.rule == "RECORRIDO" for e in snap.events)


def test_tour_not_started_outside_home(tmp_path):
    ctx, sim, snaps, ft = run(tmp_path, 2, scenario=Scenario(period=10_000))
    ft.t += 100
    sim.page = "linea"  # el operador dejó otra pantalla
    ctx.engine.run_tour_now()
    n = len(sim.clicks)
    snap = ctx.engine.step()
    assert snap.tour.skipped and "principal" in snap.tour.message
    assert len(sim.clicks) == n


def test_page_not_visible(tmp_path):
    ctx, sim, _, _ = run(tmp_path, 3, scenario=Scenario(period=10_000))
    ctx.engine.source = type("Blank", (), {"grab": lambda self: np.zeros((800, 1280, 3), np.uint8)})()
    ctx.engine._build()
    snap = ctx.engine.step()
    assert snap.pages == set()
    assert not any(f.rule == R_TOL for f in snap.findings)


def test_selector_state_against_recipe(tmp_path):
    ctx, sim, snaps, _ = run(tmp_path, 600)
    events = [e for s in snaps for e in s.events]
    assert snaps[10].statuses["inyeccion"].reading.text == "ON"
    raised = [e for e in events if e.kind == "raised" and e.rule == "SELECTOR"]
    assert raised and "OFF" in raised[0].message and 540 <= raised[0].ts - 1000 < 560
    assert any(e.kind == "cleared" and e.rule == "SELECTOR" for e in events)


def test_behavior_model_detects_pressure_rise(tmp_path):
    from extrusion_monitor.analysis.behavior import BehaviorModel, train
    ctx, sim, snaps, ft = run(tmp_path, 400)
    h = ctx.engine.historian
    vids = ["rpm", "carga", "presion"]
    series = {v: tuple(np.array(x) for x in zip(*h.samples(v, 0, ft.t))) for v in vids}
    m = train(BehaviorModel(id="m1", name="Husillo", variables=vids), series, 1020, 1400, 5, 40)
    ctx.engine.behaviors.store.upsert(m)
    events = []
    while ft.t < 1000 + 500:
        events += ctx.engine.step().events
        ft.t += 1
    beh = [e for e in events if e.rule == "COMPORTAMIENTO" and e.kind in ("raised", "escalated")]
    assert beh and "Presion" in beh[-1].message
