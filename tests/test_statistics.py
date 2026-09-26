import numpy as np
import pytest

from extrusion_monitor.analysis.statistics import align, capability, correlation, projection, xbar_chart


def test_align_forward_fill_and_gaps():
    s = {"a": (np.array([0.0, 10, 20, 30]), np.array([1.0, 2, 3, 4])),
         "b": (np.array([0.0, 30]), np.array([10.0, 40]))}
    t, m, names = align(s, 5, max_gap_s=12)
    assert names == ["a", "b"]
    # b solo vale hasta 12 s después de cada lectura: los huecos se descartan
    assert list(t) == [0, 5, 10, 30]
    assert m[1].tolist() == [1, 10] and m[-1].tolist() == [4, 40]


def test_capability_indices():
    rng = np.random.default_rng(0)
    y = rng.normal(100, 1, 2000)
    c = capability(y, 94, 106)
    assert c.cp == pytest.approx(2.0, rel=0.1)
    assert c.cpk == pytest.approx(2.0, rel=0.1)
    assert c.pct_out < 0.01
    off = capability(y + 4, 94, 106)
    assert off.cpk < 1 and off.pct_out > 1


def test_xbar_flags_shift():
    t = np.arange(0, 600, 1.0)
    y = np.where(t < 500, 50.0, 60.0) + np.random.default_rng(1).normal(0, 0.5, len(t))
    xb = xbar_chart(t, y, 30)
    assert len(xb.out) >= 1 and xb.means[xb.out[-1]] > xb.ucl


def test_correlation_and_projection():
    x = np.linspace(0, 10, 100)
    m = np.column_stack([x, 2 * x + 1, -x])
    r = correlation(m)
    assert r[0, 1] == pytest.approx(1) and r[0, 2] == pytest.approx(-1)
    pr = projection(np.arange(100.0), 0.5 * np.arange(100.0), horizon_s=60, fit_s=50)
    assert pr["y"][-1] == pytest.approx(0.5 * 159, rel=1e-3)
