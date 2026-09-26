import numpy as np
import pytest

from extrusion_monitor.analysis.behavior import (BehaviorModel, BehaviorMonitor, BehaviorStore, TrainingError,
                                                 evaluate, train)


def correlated(n=600, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=float) * 2
    rpm = 45 + np.sin(t / 60) + rng.normal(0, 0.05, n)
    pres = 250 + 12 * (rpm - 45) + rng.normal(0, 0.8, n)
    return {"rpm": (t, rpm), "pres": (t, pres)}


def model():
    return BehaviorModel(id="m", name="Husillo", variables=["rpm", "pres"])


def test_train_learns_correlation():
    m = train(model(), correlated(), 0, 1200, 4, 10)
    assert m.trained and m.corr[0][1] > 0.95
    assert m.mean[0] == pytest.approx(45, abs=0.5)


def test_normal_point_ok_and_broken_relation_detected():
    m = train(model(), correlated(), 0, 1200, 4, 10)
    ok = evaluate(m, {"rpm": 45.5, "pres": 256.0}, 0)
    assert ok.d2 < ok.threshold
    # Ambas dentro de su rango individual, pero la presión no acompaña a las rpm.
    bad = evaluate(m, {"rpm": 44.2, "pres": 258.0}, 0)
    assert bad.d2 > bad.threshold
    assert bad.broken_pairs and bad.contributions["pres"] > 20


def test_monitor_condition_and_recipe_filter(tmp_path):
    store = BehaviorStore(tmp_path / "b.json")
    m = train(model(), correlated(), 0, 1200, 4, 10)
    m.recipe = "R1"
    store.upsert(m)
    mon = BehaviorMonitor(BehaviorStore(tmp_path / "b.json"))
    conds, ev = mon.evaluate(0, {"rpm": 44.2, "pres": 258.0}, "R1", lambda v: v)
    assert ("COMPORTAMIENTO", "@m") in conds and "@m" in ev
    conds, ev = mon.evaluate(0, {"rpm": 44.2, "pres": 258.0}, "OTRA", lambda v: v)
    assert not conds and not ev
    conds, ev = mon.evaluate(0, {"rpm": 44.2}, "R1", lambda v: v)  # falta un dato: no se evalúa
    assert not ev


def test_training_needs_data():
    with pytest.raises(TrainingError):
        train(model(), {"rpm": correlated()["rpm"]}, 0, 1200, 4, 10)
