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
            from extrusion_monitor.analysis.oee import shift_start
            sh = shift_start(ts, ["06:00", "14:00", "22:00"])
            run = (i % 60) < 55  # 5 min detenida cada hora
            row = {"ts": ts, "from": ts - 60, "v": {"diam": [3.2 + 0.01 * k + rng.normal(0, 0.01), 0, 0],
                                                   "vel": [350 + rng.normal(0, 2), 0, 0]},
                   "k": {"oee": 80 - 15 * k + rng.normal(0, 2), "availability": 90 - 10 * k, "performance": 92,
                         "quality": 97, "stability": 95 - 2 * k - 0.001 * i * k, "i5": 85 - 20 * k},
                   # producción acumulada del turno (10 m/min), estado de la máquina y usuario en turno
                   "p": [sh, (ts - sh) / 60 * 10, (ts - sh) / 60 * 9.5], "s": "running" if run else "stopped",
                   "u": "Ana" if time.localtime(ts).tm_hour < 14 else "Luis"}
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


def test_production_shifts_operators_failures_and_goals(tmp_path):
    from extrusion_monitor.analysis.plant import summarize
    from extrusion_monitor.fleet import FleetReader
    from extrusion_monitor.fleet_data import FleetHistorian
    from extrusion_monitor.plant_settings import PlantSettings, Targets
    now = time.time()
    make_plant(tmp_path / "planta", now)
    r = FleetReader(tmp_path / "planta")
    r.scan()
    plant = PlantSettings(cost_stop_h=600, cost_scrap_unit=2, default_targets=Targets(production_shift=4000, oee=75))
    plant.targets["Línea 2"] = Targets(production_shift=6000, oee=70, mttr_min=15)
    plant.save(tmp_path / "home")
    p2 = PlantSettings.load(tmp_path / "home")
    assert p2.target("Línea 1").production_shift == 4000 and p2.target("Línea 2").mttr_min == 15
    s = summarize(FleetHistorian(r), now - 2 * 86400, now, plant=p2)
    m1, m2 = s.lines
    assert m1.produced > 0 and m1.n_shifts >= 6 and m1.compliance is not None
    assert m2.compliance < m1.compliance  # misma producción, meta más alta
    assert m1.run_h == pytest.approx(48 * 55 / 60, rel=0.05)
    assert m1.scrap_cost == pytest.approx(m1.scrap * 2) and m1.quality_cost == pytest.approx(m1.cost + m1.scrap_cost)
    assert {"Ana", "Luis"} <= set(m1.by_user) and len(m1.by_shift) >= 2
    assert m2.failures["Cambio de dado"]["n"] == 2 and m2.failures["Cambio de dado"]["mtbf"] > 0
    texts = " ".join(i.text for i in s.insights)
    # según la hora del día una línea va arriba o abajo de su meta: «cumplió» o «… de cumplimiento»
    assert "cumpli" in texts and "MTTR" in texts and "Costo de paros y desperdicio" in texts


def test_dashboard_new_pages_dialog_and_weekly_report(tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from extrusion_monitor.notify import NotifySettings
    from extrusion_monitor.plant_settings import PlantSettings
    from extrusion_monitor.ui.fleet_plant_dialog import PlantDialog
    from extrusion_monitor.ui.fleet_window import FleetWindow
    now = time.time()
    make_plant(tmp_path / "planta", now)
    w = FleetWindow(str(tmp_path / "planta"), tmp_path / "fleet.json")
    w.refresh()
    home = tmp_path
    dlg = PlantDialog(home, ["Línea 1", "Línea 2"])
    dlg.spins[("__todas__", "production_shift")].setValue(4500)
    dlg.spins[("Línea 2", "oee")].setValue(70)
    dlg.sp_stop.setValue(900)
    dlg.chk_weekly.setChecked(True)
    dlg.accept()
    plant = PlantSettings.load(home)
    assert plant.default_targets.production_shift == 4500 and plant.targets["Línea 2"].oee == 70
    assert plant.cost_stop_h == 900 and plant.weekly.enabled
    for key in ("map", "maintenance", "analyzer"):
        w.show_page(key)
        assert w.current_page == key
    tiles = w.pages["map"].items
    assert set(tiles) == {"L1", "L2"} and "Línea 1" in tiles["L1"].lbl_name.text()
    maint = w.pages["maintenance"]
    assert maint.cmb_line.count() == 3  # «todas» + las dos líneas, sin agregarlas a mano
    # reporte semanal: cuando toca, genera el PDF y lo manda (canal simulado)
    sent = []
    ns = NotifySettings()
    ns.webhook.enabled = True
    ns.set_secret("webhook", "https://hook")
    ns.save(home)
    w.notifier.reload()
    w.notifier.senders = {"webhook": lambda s, m: sent.append(m)}
    p = PlantSettings.load(home)
    p.weekly.last = 0
    p.save(home)
    assert w.weekly_due(now)
    path = w.send_weekly()
    w.notifier.flush()
    assert path and path.exists() and path.read_bytes().startswith(b"%PDF")
    assert sent and sent[0].attachment == path and not w.weekly_due(now)
    w.close()


def add_maintenance(root, now):
    """Paros de mantenimiento capturados en los monitores (preventivo y correctivo)."""
    from extrusion_monitor.fleet import PROBLEMS_DIR, month_name
    recs = [("L1", "Mantenimiento", "Preventivo de cabezal", 10, 3600, 4),
            ("L1", "Mantenimiento", "Falla de bomba de vacío", 2, 1800, 12),
            ("L2", "Mecánico", "Reparación de jalador", 1, 2700, 0),
            ("L2", "Limpieza", "Limpieza programada", 40, 1200, 0)]
    for k, (lid, cat, reason, days, dur, scrap) in enumerate(recs):
        path = root / lid / PROBLEMS_DIR / month_name(now - days * 86400)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"op": "add", "uid": f"m{k}", "kind": "downtime", "start": now - days * 86400,
                                "end": now - days * 86400 + dur, "duration_s": dur, "category": cat, "reason": reason,
                                "planned": 0, "scrap": scrap, "unit": "m", "operator": "Ana"}) + "\n")


def test_maintenance_reads_preventive_and_corrective_from_captured_stops(tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from extrusion_monitor.analysis.maintenance import summarize_maintenance
    from extrusion_monitor.fleet import FleetReader
    from extrusion_monitor.fleet_data import FleetHistorian
    from extrusion_monitor.plant_settings import PlantSettings
    from extrusion_monitor.ui.fleet_maint import ClassifyDialog, FleetMaintenance
    now = time.time()
    make_plant(tmp_path / "planta", now)
    add_maintenance(tmp_path / "planta", now)
    r = FleetReader(tmp_path / "planta")
    r.scan()
    plant = PlantSettings(default_pm_days=30, extra_lines=["Línea 3"])
    plant.save(tmp_path)
    s = summarize_maintenance(FleetHistorian(r), plant, now - 30 * 86400, now)
    by = {m.name: m for m in s.lines}
    l1, l2 = by["Línea 1"], by["Línea 2"]
    assert (l1.n_prev, l1.n_corr) == (1, 1) and l1.min_prev == pytest.approx(60) and l1.scrap_corr == 12
    assert l1.state == "ok" and l1.days_since_prev == pytest.approx(10, abs=0.1)
    assert l2.n_corr == 1 and l2.n_prev == 0 and l2.last_prev is not None and l2.state == "late"  # hace 40 días
    assert not by["Línea 3"].has_data  # agregada a mano, sin monitor
    assert len(s.events) == 3 and s.events[0].start > s.events[-1].start
    # «Cambio de dado» no es mantenimiento por omisión; con la clasificación sí
    page = FleetMaintenance(lambda: r, tmp_path)
    page.refresh()
    dlg = ClassifyDialog(tmp_path, ["Cambio › Cambio de dado"], ["Línea 1", "Línea 2"])
    dlg.combos["Cambio › Cambio de dado"].setCurrentIndex(dlg.combos["Cambio › Cambio de dado"].findData("preventive"))
    dlg.days["Línea 2"].setValue(60)
    dlg.accept()
    p2 = PlantSettings.load(tmp_path)
    s2 = summarize_maintenance(FleetHistorian(r), p2, now - 30 * 86400, now)
    m2 = {m.name: m for m in s2.lines}["Línea 2"]
    assert m2.n_prev == 2 and m2.pm_days == 60 and m2.state == "ok"
    page.refresh()
    assert page.summary is not None and page.cmb_line.count() == 4


def test_analysis_variables_without_monitoring(tmp_path):
    """Monitor abierto sin monitorear (o de versión anterior): el análisis del dashboard igual ve las variables."""
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.fleet import STATUS_FILE, FleetReader, StationSettings
    from extrusion_monitor.fleet_data import FleetConfig, FleetHistorian
    now = time.time()
    shared = tmp_path / "planta"
    make_plant(shared, now)
    # versión anterior / status sin «variables»: se recuperan de la carpeta de tendencias
    for d in shared.iterdir():
        st = json.loads((d / STATUS_FILE).read_text("utf-8"))
        st.pop("variables")
        (d / STATUS_FILE).write_text(json.dumps(st), "utf-8")
    r = FleetReader(shared)
    r.scan()
    cfg = FleetConfig(r)
    assert {v.id for v in cfg.variables} == {"diam", "vel"}
    assert cfg.variable("diam").lines == ["Línea 1", "Línea 2"]
    assert len(FleetHistorian(r).samples("diam", now - 86400, now)) > 100

    # el monitor sin iniciar el monitoreo publica el catálogo de la receta (con nombres y unidades)
    ctx = build(tmp_path / "home", demo=True)
    ex = ctx.exporter
    ex.reconfigure(StationSettings(enabled=True, export_dir=str(shared), line_name="Línea 3"))
    assert ctx.engine.last is None
    ex.write_once()
    st = json.loads((shared / "Linea-3" / STATUS_FILE).read_text("utf-8"))
    assert not st["monitoring"] and "variables" not in st
    diam = next(v for v in st["catalog"] if v["id"] == "diam")
    assert diam["name"] and diam["unit"] == "mm"
    r.scan()
    assert "Línea 3" in FleetConfig(r).variable("diam").lines
    ex.stop(closed=True)
