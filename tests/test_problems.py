"""Problemas de proceso: capturas, OEE sin paros planeados, Paretos, CSV, carpeta compartida y pantallas."""
import csv
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from extrusion_monitor.analysis.oee import RUNNING, STOPPED, OeeSample, compute  # noqa: E402
from extrusion_monitor.analysis.problems import (export_csv, free_spans, machine_intervals, pareto,  # noqa: E402
                                                 stop_events, summary)
from extrusion_monitor.storage import Historian  # noqa: E402

T0 = 1_000_000.0


def _rec(kind, a, b, reason, cat="Mecánico", planned=False, scrap=0.0, operator="Ana"):
    return {"kind": kind, "start": a, "end": b, "duration_s": b - a, "category_id": cat.lower()[:3], "category": cat,
            "reason_id": reason.lower()[:4], "reason": reason, "planned": planned, "scrap": scrap, "unit": "m",
            "operator": operator, "comment": "", "recipe": "R1"}


def _line_history(h: Historian):
    """1 h: marcha 0–20 min, paro 20–35 min, marcha 35–60 min (muestras cada 10 s)."""
    for i in range(360):
        ts = T0 + i * 10
        stopped = 120 <= i < 210
        h.write_oee((ts, 10.0, STOPPED if stopped else RUNNING, 0.0 if stopped else 300.0, 300.0, 1, 0))


def test_storage_problems_and_planned(tmp_path):
    h = Historian(tmp_path / "h.sqlite")
    a = h.add_problem(_rec("downtime", T0, T0 + 600, "Atasco"))
    b = h.add_problem(_rec("downtime", T0 + 600, T0 + 900, "Comida", "Paro programado", planned=True))
    assert a["uid"] and a["duration_s"] == 600 and a["id"]
    assert [r["reason"] for r in h.problems(T0, T0 + 1000)] == ["Atasco", "Comida"]
    assert h.planned_intervals(T0, T0 + 1000) == [(T0 + 600, T0 + 900)]
    assert h.delete_problem(b["id"])["uid"] == b["uid"]
    assert h.planned_intervals(T0, T0 + 1000) == []


def test_planned_stop_does_not_count_against_availability():
    samples = [OeeSample(T0 + i * 10, 10.0, STOPPED if 60 <= i < 120 else RUNNING, 0 if 60 <= i < 120 else 300,
                         300, True, 0) for i in range(180)]
    plain = compute(samples, T0, T0 + 1800, 120)
    planned = compute(samples, T0, T0 + 1800, 120, planned=[(T0 + 600, T0 + 1200)])
    assert plain.availability == pytest.approx(2 / 3, abs=0.02)
    assert planned.availability == pytest.approx(1.0, abs=0.02)
    assert planned.planned_stop_s == pytest.approx(600, abs=20) and planned.n_stops == 0


def test_stop_events_split_and_pareto(tmp_path):
    h = Historian(tmp_path / "h.sqlite")
    _line_history(h)
    from extrusion_monitor.config import AppConfig, OeeSettings
    cfg = AppConfig(oee=OeeSettings(enabled=True, speed_var="vel"))
    iv = machine_intervals(h, cfg, T0, T0 + 3600)
    evs = stop_events(iv, [], min_s=120)
    assert len(evs) == 1 and evs[0].duration == pytest.approx(900, abs=20) and not evs[0].classified
    ev = evs[0]
    first = _rec("downtime", ev.start, ev.start + 300, "Atasco")
    evs = stop_events(iv, [first], min_s=120)
    spans = free_spans(evs[0])
    assert len(spans) == 1 and spans[0][0] == pytest.approx(ev.start + 300)  # se propone el resto del paro
    second = _rec("downtime", spans[0][0], spans[0][1], "Falla de motor", "Eléctrico")
    evs = stop_events(iv, [first, second], min_s=120)
    assert evs[0].classified
    recs = [first, second, _rec("quality", T0, T0 + 60, "Burbujas", "Superficie", scrap=120.0)]
    rows = pareto(recs, "downtime", by="reason", metric="time")
    assert rows[0].label == "Falla de motor" and rows[-1].cum_pct == pytest.approx(100)
    assert pareto(recs, "quality", metric="scrap")[0].value == 120.0
    s = summary(recs, evs)
    assert s.n_downtime == 2 and s.n_quality == 1 and s.pending_n == 0 and s.scrap == 120.0


def test_csv_for_excel(tmp_path):
    p = tmp_path / "p.csv"
    n = export_csv(p, [_rec("downtime", T0, T0 + 90, "Atasco", scrap=2.5)], line="Línea 1")
    assert n == 1
    text = p.read_bytes()
    assert text.startswith(b"\xef\xbb\xbf")  # BOM: Excel abre bien los acentos
    rows = list(csv.reader(p.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
    assert rows[1][0] == "Línea 1" and rows[1][4] == "1,50" and rows[1][8] == "2,5"


def test_shared_folder_export_and_fleet_read(tmp_path):
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.fleet import FleetReader, StationSettings, read_problems
    ctx = build(tmp_path / "data", demo=True)
    ex = ctx.exporter
    ex.reconfigure(StationSettings(enabled=True, export_dir=str(tmp_path / "share"), line_id="L1", line_name="Línea 1"))
    now = time.time()
    a = ctx.engine.historian.add_problem(_rec("downtime", now - 900, now - 600, "Atasco"))
    b = ctx.engine.historian.add_problem(_rec("quality", now - 500, now - 400, "Grumos", "Superficie", scrap=30))
    ex.queue_problem("add", a)
    ex.queue_problem("add", b)
    ex.write_once()
    ex.queue_problem("del", b)
    ex.write_once()
    reader = FleetReader(tmp_path / "share")
    reader.scan()
    recs = read_problems(reader.lines["L1"], now - 86400)
    assert [r["reason"] for r in recs] == ["Atasco"] and recs[0]["line"] == "Línea 1"
    assert "id" not in recs[0]  # el id local no viaja


def test_capture_page_save_split_and_config(tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.ui.problems_config import ProblemsConfigDialog
    from extrusion_monitor.ui.problems_page import ProblemsPage
    ctx = build(tmp_path / "data", demo=True)
    h = ctx.engine.historian
    now = time.time()
    # un turno que empezó hace 2 h: el paro cae en el turno sin importar la hora a la que corra la prueba
    ctx.engine.config.oee.shift_starts = [time.strftime("%H:%M", time.localtime(now - 7200))]
    for i in range(360):  # paro de 15 min hace 25–10 min
        ts = now - 3600 + i * 10
        stopped = now - 1500 <= ts < now - 600
        h.write_oee((ts, 10.0, STOPPED if stopped else RUNNING, 0.0 if stopped else 300.0, 300.0, 1, 0))
    page = ProblemsPage(ctx)
    cap = page.capture
    cap.refresh(keep_selection=False)
    assert page.count_pending() == 1
    ev = cap.events[0]
    cap.select_range(ev.start, ev.start + 300)
    cap.cmb_op.setCurrentIndex(max(0, cap.cmb_op.findText("María López")))
    rec = cap.save()
    assert rec and rec["operator"] == "María López" and rec["duration_s"] == pytest.approx(300, abs=11)
    sel = cap.selection()
    assert sel and sel[0] == pytest.approx(ev.start + 300, abs=11)  # propone el siguiente tramo del mismo paro
    cap.save()
    assert page.count_pending() == 0
    dlg = ProblemsConfigDialog(ctx.engine.config.problems)
    st = dlg.settings()
    assert [c.name for c in st.downtime] == [c.name for c in ctx.engine.config.problems.downtime]
    assert st.operators == ["Juan Pérez", "María López", "Carlos Ruiz"]


def test_main_window_has_problems_page(tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.ui.main_window import NAV_ITEMS, MainWindow
    ctx = build(tmp_path / "data", demo=True)
    win = MainWindow(ctx)
    assert "problems" in {k for k, _, _ in NAV_ITEMS}
    win.show_page("problems")
    assert win.current_page() == "problems"
    win._problems_badge(2)
    item = next(win.nav.item(i) for i in range(win.nav.count()) if win.nav.item(i).data(0x0100) == "problems")
    assert "(2)" in item.text()
    win._detach()
