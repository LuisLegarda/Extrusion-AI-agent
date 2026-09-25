import numpy as np

from extrusion_monitor.analysis.trends import TrendTracker


def test_slope_and_eta():
    tr = TrendTracker(window_s=900, subgroup_s=30)
    rng = np.random.default_rng(0)
    for i in range(150):  # 5 min subiendo 0.006 mm/min desde 3.20
        tr.add("d", float(i * 2), 3.20 + 0.0001 * i * 2 + rng.normal(0, 0.001))
    st = tr.stats("d", now=300, center=3.2, lo_limit=3.15, hi_limit=3.25)
    assert st.slope_significant
    assert abs(st.slope_per_min - 0.006) < 0.001
    assert st.eta_to_alarm_min is not None and 2.5 < st.eta_to_alarm_min < 4.5


def test_stable_process_no_rules():
    tr = TrendTracker(window_s=900, subgroup_s=30)
    rng = np.random.default_rng(1)
    for i in range(400):
        tr.add("t", float(i * 2), 180 + rng.normal(0, 0.5))
    st = tr.stats("t", now=800, center=180, lo_limit=174, hi_limit=186, min_effect=3)
    assert not st.nelson
    assert st.cpk > 2


def test_window_trims_old_points():
    tr = TrendTracker(window_s=60, subgroup_s=10)
    for i in range(200):
        tr.add("x", float(i), 1.0)
    t, _ = tr.series("x")
    assert t[0] >= 199 - 60
