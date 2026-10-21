"""Análisis estadístico: cálculos (contra valores de referencia) y cada tipo de análisis con datos del historial."""
import math
import os
import time

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_distributions_match_reference_values():
    from extrusion_monitor.analysis import stattools as st
    assert st.norm_ppf(0.975) == pytest.approx(1.959964, abs=1e-6)
    assert st.t_sf2(2.0, 10) == pytest.approx(0.07339, abs=1e-4)
    assert st.t_ppf(0.975, 10) == pytest.approx(2.228, abs=1e-3)
    assert st.f_sf(4, 2, 20) == pytest.approx(0.03457, abs=1e-4)


def test_descriptive_capability_normality_and_regression():
    from extrusion_monitor.analysis import stattools as st
    d = st.describe([1, 2, 3, 4, 10])
    assert d["mean"] == 4 and d["median"] == 3 and d["range"] == 9 and d["ss"] == 50 and d["sum"] == 20
    rng = np.random.default_rng(3)
    y = rng.normal(10, 2, 2000)
    assert st.anderson_darling(y).normal and not st.anderson_darling(rng.exponential(1, 500)).normal
    cap = st.capability_report(y, 4, 16, 10)
    assert cap.pp == pytest.approx(1.0, abs=0.06) and cap.ppm_overall == pytest.approx(2700, rel=0.5)
    x = rng.normal(size=(300, 2))
    yy = 3 + 2 * x[:, 0] - x[:, 1] + rng.normal(0, 0.5, 300)
    reg = st.ols(x, yy, ["a", "b"])
    assert reg.coef == pytest.approx([3, 2, -1], abs=0.15) and reg.r2 > 0.9 and (reg.p[1:] < 0.001).all()
    yhat, clo, chi, plo, phi = reg.predict([1, 1])
    assert plo < clo < yhat < chi < phi and yhat == pytest.approx(4, abs=0.2)
    an = st.anova_oneway({"A": rng.normal(0, 1, 60), "B": rng.normal(1, 1, 60), "C": rng.normal(0, 1, 60)})
    assert an.p < 0.01 and an.df_between == 2
    i_chart, mr = st.imr_charts(np.r_[rng.normal(0, 1, 100), [9.0]])
    assert 100 in i_chart.out
    xb, r = st.xbar_r_charts(rng.normal(0, 1, 100), 5)
    assert len(xb.values) == 20 and r.ucl > r.center
    names, vals, cum = st.pareto({"a": 5, "b": 10, "c": 1})
    assert names == ["b", "a", "c"] and cum[-1] == pytest.approx(100)


@pytest.fixture
def ctx(tmp_path):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.bootstrap import build
    QApplication.instance() or QApplication([])
    c = build(tmp_path, demo=True)
    h = c.engine.historian
    rng = np.random.default_rng(7)
    now = time.time()
    t = np.arange(now - 3 * 86400, now, 60.0)
    vel = 350 + rng.normal(0, 2, len(t))
    diam = 3.2 + 0.002 * (vel - 350) + rng.normal(0, 0.01, len(t))
    exc = 5 + rng.normal(0, 0.8, len(t)) + (np.array([time.localtime(x).tm_hour for x in t]) >= 14) * 0.6
    rows = []
    for vid, ys in (("vel", vel), ("diam", diam), ("exc", exc)):
        rows += [(float(a), vid, float(b), None) for a, b in zip(t, ys)]
    h.write_samples(rows)
    h.write_events([(now - 2 * 86400, "crew", 1, "USUARIO", "Ana", "Usuario en turno: Ana", None),
                    (now - 86400, "crew", 1, "USUARIO", "Luis", "Usuario en turno: Luis", None)])
    for k, (reason, cat, d) in enumerate((("Cambio de dado", "Cambio", 900), ("Falta de material", "Material", 600),
                                          ("Cambio de dado", "Cambio", 300))):
        h.add_problem({"kind": "downtime", "start": now - 5000 * (k + 1), "end": now - 5000 * (k + 1) + d,
                       "category_id": "c", "category": cat, "reason_id": "r", "reason": reason, "planned": 0,
                       "scrap": 2.0, "unit": "m", "operator": "Ana", "comment": "", "recipe": None})
    return c


ALL = {
    "describe": {"vars": ["diam", "vel"], "group_by": "shift"},
    "compare": {"vars": ["exc"], "group_by": "shift"},
    "normality": {"vars": ["diam"]},
    "histogram": {"vars": ["diam"], "group_by": "day", "lsl": 3.15, "usl": 3.25},
    "boxplot": {"vars": ["exc"], "group_by": "operator"},
    "timeseries": {"vars": ["diam", "vel"]},
    "bar": {"vars": ["exc"], "group_by": "hour", "stat": "mean"},
    "capability": {"vars": ["diam"], "lsl": 3.15, "usl": 3.25, "target": 3.2},
    "sixpack": {"vars": ["diam"], "lsl": 3.15, "usl": 3.25},
    "control": {"vars": ["diam"], "chart": "xbar_r", "subgroup": 5},
    "pareto": {"source": "downtime", "by": "reason", "measure": "minutes"},
    "matrix": {"vars": ["diam", "vel", "exc"], "step_s": 60},
    "contour": {"vars": ["vel", "exc", "diam"], "x": "vel", "y": "exc", "z": "diam", "step_s": 60},
    "regression": {"vars": ["diam", "vel", "exc"], "y": "diam", "xs": ["vel", "exc"], "step_s": 60,
                   "quadratic": True},
}


def test_every_analysis_type_renders_with_history(ctx):
    from PySide6.QtWidgets import QApplication, QLabel

    from extrusion_monitor.ui.stats_page import TYPES, StatsPage
    assert set(ALL) == set(TYPES)
    page = StatsPage(ctx)
    now = time.time()
    for kind, params in ALL.items():
        rec = {"id": kind, "type": kind, "title": "", "style": {},
               "params": {"since": now - 4 * 86400, "until": now, **params}}
        page.add(rec)
        QApplication.processEvents()
        R = page.current
        texts = " ".join(lb.text() for lb in R.findChildren(QLabel))
        assert "No se pudo calcular" not in texts and "No hay datos" not in texts, (kind, texts[:300])
        assert R.lay.count() >= 2, kind
    assert len(page.records) == len(ALL)
    # la regresión tiene simulador; mover un factor cambia la predicción
    page.lst.setCurrentRow(0)
    sim = page.current.simulator
    before = sim.out.text()
    sim.spins[0].setValue(sim.spins[0].value() + 5)
    assert sim.out.text() != before
    # la comparación por turno detecta la diferencia de las 14:00 en adelante
    i = next(k for k, r in enumerate(page.records) if r["type"] == "compare")
    page.lst.setCurrentRow(i)
    texts = " ".join(lb.text() for lb in page.current.findChildren(QLabel))
    assert "diferencia significativa" in texts


def test_navigator_persists_rename_colors_titles_and_delete(ctx, tmp_path):
    from extrusion_monitor.ui.stats_page import StatsPage, load_project
    page = StatsPage(ctx)
    now = time.time()
    page.add({"id": "h1", "type": "histogram", "title": "", "style": {},
              "params": {"since": now - 86400, "until": now, "vars": ["diam", "vel"]}})
    page.records[0]["title"] = "Diámetro abril contra septiembre"
    page._chart_title(0, "hist", "Mi histograma")
    page.set_colors(0, ["#112233", "#445566"])
    assert page.current.color(0, page.current.series[0]).name() == "#112233"
    assert "Mi histograma" in page.current.findChildren(__import__("pyqtgraph").PlotWidget)[0].getPlotItem().titleLabel.text
    saved = load_project(ctx.workspace.home)
    assert saved[0]["title"] == "Diámetro abril contra septiembre" and saved[0]["style"]["colors"][0] == "#112233"
    page2 = StatsPage(ctx)  # al abrir de nuevo, el navegador sigue ahí
    assert page2.lst.count() == 1 and page2.current is not None
    png = page2.export_png(str(tmp_path / "a.png"))
    assert png and os.path.getsize(png) > 1000
    page2.delete(confirm=False)
    assert load_project(ctx.workspace.home) == []


def test_dialog_builds_records_and_validates(ctx):
    from extrusion_monitor.ui.stats_page import AnalysisDialog
    dlg = AnalysisDialog(ctx)
    dlg._select_type("capability")
    dlg.cmb_one.setCurrentIndex(dlg.cmb_one.findData("diam"))
    dlg.chk_lsl.setChecked(False)
    dlg.chk_usl.setChecked(False)
    assert dlg.problems()  # sin especificación
    dlg.chk_usl.setChecked(True)
    dlg.sp_usl.setValue(3.25)
    rec = dlg.record()
    assert rec["type"] == "capability" and rec["params"]["vars"] == ["diam"] and rec["params"]["usl"] == 3.25
    dlg._select_type("regression")
    dlg.cmb_resp.setCurrentIndex(dlg.cmb_resp.findData("diam"))
    assert any("factor" in m for m in dlg.problems())
    for i in range(dlg.lst_vars.count()):
        if dlg.lst_vars.item(i).data(0x0100) == "vel":
            dlg.lst_vars.item(i).setCheckState(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Checked)
    rec = dlg.record()
    assert rec["params"]["y"] == "diam" and rec["params"]["xs"] == ["vel"] and not dlg.problems()


def test_page_in_sidebar_and_crew_changes_are_logged(ctx):
    from extrusion_monitor.ui.main_window import NAV_ITEMS, MainWindow
    assert "analysis" in {k for k, _, _ in NAV_ITEMS}
    win = MainWindow(ctx)
    win.show_page("analysis")
    assert win.current_page() == "analysis"
    win.set_user("Rosa")
    ev = [e for e in ctx.engine.historian.events_between(time.time() - 60, time.time() + 60) if e[1] == "crew"]
    assert ev and ev[-1][4] == "Rosa"
    win._detach()


def test_pdf_report_and_scheduled_analyses(ctx, tmp_path):
    from extrusion_monitor.ui.stats_page import StatsPage, load_schedule_state
    from extrusion_monitor.ui.stats_report import period_start, run_due, write_pdf
    page = StatsPage(ctx)
    now = time.time()
    for kind in ("capability", "pareto", "histogram"):
        page.add({"id": kind, "type": kind, "title": "", "style": {}, "schedule": "day" if kind != "histogram" else "",
                  "params": {"since": now - 3 * 86400, "until": now, **ALL[kind]}})
    pdf = write_pdf(ctx, page.records, tmp_path / "r.pdf", "Reporte de prueba", "Línea 1")
    data = pdf.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 20000
    # programados: la primera vez solo marca el periodo; al terminar el día genera el PDF del día anterior
    assert run_due(page, now) == []
    day0 = period_start("day", now, [])
    assert load_schedule_state(page.home)["day"] == day0
    sent = []
    ctx.notifier = type("N", (), {"report_ready": lambda self, p, t: sent.append((p, t))})()
    made = run_due(page, day0 + 86400 + 60)
    assert len(made) == 1 and made[0].exists() and "Analisis_day_" in made[0].name and sent
    assert run_due(page, day0 + 86400 + 120) == []  # ya se hizo el de ese día
    assert period_start("week", now, []) <= day0 and period_start("shift", now, ["06:00", "14:00", "22:00"]) <= now
