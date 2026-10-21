"""Dashboard global: páginas en la misma ventana, analizador de planta y análisis estadístico con datos de las líneas."""
import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


def make_plant(root, now):
    """Dos líneas con tendencia por minuto, indicadores, eventos y paros, como las escribe el exportador."""
    import numpy as np

    from extrusion_monitor.fleet import EVENTS_DIR, PROBLEMS_DIR, STATUS_FILE, TREND_DIR, day_name, month_name
    rng = np.random.default_rng(3)
    for k, name in enumerate(("Línea 1", "Línea 2")):
        d = root / f"L{k + 1}"
        (d / TREND_DIR).mkdir(parents=True)
        (d / EVENTS_DIR).mkdir()
        (d / PROBLEMS_DIR).mkdir()
        (d / STATUS_FILE).write_text(json.dumps({
            "line_id": f"L{k + 1}", "line_name": name, "ts": now, "interval_s": 5, "recipe": "R1",
            "variables": [{"id": "diam", "name": "Diámetro", "unit": "mm", "kind": "actual"},
                          {"id": "vel", "name": "Velocidad", "unit": "m/min", "kind": "actual"}]}), "utf-8")
        files = {}
        for i in range(3 * 24 * 60):
            ts = now - 3 * 86400 + 60 * i
            row = {"ts": ts, "v": {"diam": [3.2 + 0.01 * k + rng.normal(0, 0.01), 0, 0],
                                   "vel": [350 + rng.normal(0, 2), 0, 0]},
                   "k": {"oee": 80 - 15 * k + rng.normal(0, 2), "availability": 90 - 10 * k, "performance": 92,
                         "quality": 97, "stability": 95 - 2 * k - 0.001 * i * k, "i5": 85 - 20 * k}}
            files.setdefault(day_name(ts), []).append(json.dumps(row))
        for fname, lines in files.items():
            (d / TREND_DIR / fname).write_text("\n".join(lines) + "\n", "utf-8")
        ev = [json.dumps({"ts": now - 3600 * j, "kind": "raised", "level": "ALARM", "rule": "TOLERANCIA",
                          "var": "diam", "msg": "fuera", "recipe": "R1"}) for j in range(5 * (k + 1))]
        (d / EVENTS_DIR / day_name(now)).write_text("\n".join(ev) + "\n", "utf-8")
        probs = [json.dumps({"op": "add", "uid": f"{k}-{j}", "kind": "downtime", "start": now - 7200 * (j + 1),
                             "end": now - 7200 * (j + 1) + 600 * (k + 1), "duration_s": 600 * (k + 1),
                             "category": "Cambio", "reason": "Cambio de dado" if j % 2 else "Falta de material",
                             "planned": 0, "scrap": 5, "unit": "m"}) for j in range(4)]
        (d / PROBLEMS_DIR / month_name(now)).write_text("\n".join(probs) + "\n", "utf-8")


def test_plant_summary_metrics_and_insights(tmp_path):
    from extrusion_monitor.analysis.plant import summarize
    from extrusion_monitor.fleet import FleetReader
    from extrusion_monitor.fleet_data import FleetHistorian
    now = time.time()
    make_plant(tmp_path, now)
    r = FleetReader(tmp_path)
    r.scan()
    s = summarize(FleetHistorian(r), now - 7 * 86400, now, cost_per_h=1000)
    m1, m2 = s.lines
    assert m1.name == "Línea 1" and m1.kpis["oee"] == pytest.approx(80, abs=1)
    assert m2.n_stops == 4 and m2.stop_min == pytest.approx(80) and m2.mttr_min == pytest.approx(20)
    assert m2.mtbf_h and m2.cost == pytest.approx(80 / 60 * 1000) and m2.alarms == 10
    assert m2.main_loss[0] == "availability"
    texts = " ".join(i.text for i in s.insights)
    assert "Línea 2 tiene el OEE más bajo" in texts and "tiempo muerto de la planta" in texts
    assert "índice 5.0 bajo" in texts and s.insights[0].severity >= s.insights[-1].severity


def test_fleet_stats_context_groups_by_line(tmp_path):
    from PySide6.QtWidgets import QApplication, QLabel
    QApplication.instance() or QApplication([])
    from extrusion_monitor.fleet import FleetReader
    from extrusion_monitor.fleet_data import FleetStatsContext
    from extrusion_monitor.ui.stats_page import AnalysisDialog, StatsPage
    now = time.time()
    make_plant(tmp_path / "planta", now)
    r = FleetReader(tmp_path / "planta")
    r.scan()
    ctx = FleetStatsContext(lambda: r, tmp_path / "home")
    assert {v.id for v in ctx.engine.config.variables} == {"diam", "vel"} and ctx.lines == ["Línea 1", "Línea 2"]
    dlg = AnalysisDialog(ctx)
    assert dlg.cmb_group.findData("line") >= 0 and dlg.cmb_line.count() == 3
    page = StatsPage(ctx)
    page.add({"id": "c", "type": "compare", "title": "", "style": {},
              "params": {"since": now - 4 * 86400, "until": now, "vars": ["diam"], "group_by": "line"}})
    texts = " ".join(lb.text() for lb in page.current.findChildren(QLabel))
    assert "Línea 1" in texts and "diferencia significativa" in texts
    page.add({"id": "p", "type": "pareto", "title": "", "style": {},
              "params": {"since": now - 4 * 86400, "until": now, "source": "downtime", "by": "line",
                         "measure": "minutes", "line": "Línea 2"}})
    texts = " ".join(lb.text() for lb in page.current.findChildren(QLabel))
    assert "Línea 2" in texts and "Línea 1" not in texts


def test_dashboard_pages_open_inside_the_window(tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from extrusion_monitor.ui.fleet_window import FleetWindow
    now = time.time()
    make_plant(tmp_path / "planta", now)
    w = FleetWindow(str(tmp_path / "planta"), tmp_path / "fleet.json")
    w.refresh()
    for key in ("analyzer", "problems", "analysis", "lines"):
        w.show_page(key)
        assert w.current_page == key and w.stack.currentWidget() is w.pages[key]
    w.open_problems()
    assert w.current_page == "problems" and not w.ed_search.isVisibleTo(w)
    w.show_page("analyzer")
    assert w.pages["analyzer"].summary is not None and len(w.pages["analyzer"].summary.lines) == 2
    item = next(w.nav.item(i) for i in range(w.nav.count()) if w.nav.item(i).data(0x0100) == "ack")
    assert "Silenciar" in item.text() and item.toolTip()
    w.close()
