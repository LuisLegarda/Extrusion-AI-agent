import pytest

from extrusion_monitor.analysis.oee import (MICROSTOP, RUNNING, SLOW, STOPPED, OeeSample, alarm_load_score,
                                            classify, compute, human_factors)


def series(states):
    """states: lista de (duración_s, estado, velocidad, bueno)."""
    out, t = [], 0.0
    for dur, st, speed, good in states:
        for _ in range(int(dur)):
            t += 1
            out.append(OeeSample(t, 1.0, st, speed, 100.0, good, 0))
    return out


def test_availability_performance_quality():
    s = series([(600, RUNNING, 100, True), (60, STOPPED, 0, True), (300, RUNNING, 80, False),
                (30, STOPPED, 0, True), (10, RUNNING, 100, True)])
    r = compute(s, 0, 1000, microstop_s=45)
    # El paro de 30 s es microparo: cuenta como marcha a velocidad 0.
    assert r.n_stops == 1 and r.n_microstops == 1
    assert r.run_s == pytest.approx(940) and r.stop_s == pytest.approx(60)
    assert r.availability == pytest.approx(0.94)
    assert r.performance == pytest.approx((610 * 100 + 300 * 80) / (940 * 100))
    assert r.quality == pytest.approx(610 * 100 / (610 * 100 + 300 * 80))
    assert r.oee == pytest.approx(r.availability * r.performance * r.quality)
    assert r.mttr_s == pytest.approx(60) and r.mtbf_s == pytest.approx(940)
    assert r.length_total == pytest.approx((610 * 100 + 300 * 80) / 60)


def test_blip_inside_stop_is_merged():
    s = series([(100, RUNNING, 100, True), (40, STOPPED, 0, True), (3, SLOW, 2, True), (60, STOPPED, 0, True),
                (100, RUNNING, 100, True)])
    r = compute(s, 0, 303, microstop_s=30)
    assert r.n_stops == 1 and r.stop_s == pytest.approx(103)


def test_classify():
    assert classify(None, 100, 0.5, 90) == "unknown"
    assert classify(0.2, 100, 0.5, 90) == STOPPED
    assert classify(80, 100, 0.5, 90) == SLOW
    assert classify(95, 100, 0.5, 90) == RUNNING
    assert MICROSTOP


def test_human_factors():
    assert alarm_load_score(4) == 100 and alarm_load_score(12) == 50 and alarm_load_score(40) == 0
    r = compute(series([(3600, RUNNING, 100, True)]), 0, 3600, 60)
    events = [(10, "raised", 3, "TOLERANCIA", "x", "", ""), (70, "cleared", 0, "TOLERANCIA", "x", "", ""),
              (100, "setpoint_change", 1, "CAMBIO_AJUSTE", "y", "", "")]
    hf = human_factors(events, r)
    assert hf.alarms_per_hour == pytest.approx(1) and hf.mean_recovery_s == pytest.approx(60)
    assert hf.human_score == 100 and hf.index is not None


def test_assumed_gap_counts_as_run():
    from extrusion_monitor.analysis.oee import ASSUMED
    s = series([(100, RUNNING, 100, True)])
    s.append(OeeSample(1100.0, 1000.0, ASSUMED, 100.0, 100.0, True, 0))
    s += [OeeSample(1100.0 + i, 1.0, RUNNING, 100.0, 100.0, True, 0) for i in range(1, 101)]
    r = compute(s, 0, 1200, 60)
    assert r.run_s == pytest.approx(1200) and r.availability == pytest.approx(1.0)
    assert r.distribution[ASSUMED][0] == pytest.approx(1000)


def test_engine_fills_gap_only_if_in_spec(tmp_path):
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.simulator import HmiSimulator, Scenario, SimulatorSource
    t = [1000.0]
    clk = lambda: t[0]  # noqa: E731
    sim = HmiSimulator(scenario=Scenario(period=1e6), clock=clk)
    ctx = build(tmp_path, demo=True, source=SimulatorSource(sim), clock=clk, sleep=lambda s: None)
    for _ in range(40):
        ctx.engine.step()
        t[0] += 1
    t[0] += 600  # 10 min sin datos (app cerrada)
    for _ in range(3):
        ctx.engine.step()
        t[0] += 1
    rows = ctx.engine.historian.oee_samples(0, t[0])
    assumed = [r for r in rows if r[2] == "assumed"]
    assert len(assumed) == 1 and assumed[0][1] == pytest.approx(600, abs=12)  # + dt de la muestra
    t[0] += 5000  # hueco mayor al límite (30 min): queda sin datos
    ctx.engine.step()
    assert len([r for r in ctx.engine.historian.oee_samples(0, t[0]) if r[2] == "assumed"]) == 1
