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
