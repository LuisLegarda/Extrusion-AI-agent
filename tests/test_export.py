"""Exportar: CSV, Excel (.xlsx) y texto para software estadístico (Minitab), en el monitor y el dashboard."""
import datetime as dt
import os
import time
import zipfile
from xml.etree import ElementTree as ET

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
HEADER = ["fecha_hora", "Diámetro (mm)", "Diámetro (mm)", "Operador's", "#paros"]
ROWS = [[dt.datetime(2026, 10, 1, 8, 0), 3.25, None, "Ana", 2],
        [dt.datetime(2026, 10, 1, 8, 1), "3.5", float("nan"), "007", 0]]


def _sheet(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        ET.fromstring(z.read("xl/workbook.xml"))
        ET.fromstring(z.read("xl/styles.xml"))
    return [[c for c in row.findall("m:c", NS)] for row in root.find("m:sheetData", NS).findall("m:row", NS)]


def test_csv_xlsx_and_statistical_formats(tmp_path):
    from extrusion_monitor.tabular import stat_names, stat_text, write_table
    # CSV en español: «;» y coma decimal; los códigos con ceros a la izquierda se quedan como texto
    p = tmp_path / "a.csv"
    assert write_table(p, HEADER, ROWS, "csv") == 2
    lines = p.read_text("utf-8-sig").splitlines()
    assert lines[1] == "2026-10-01 08:00:00;3,25;;Ana;2" and lines[2].endswith(";007;0")
    write_table(p, HEADER, ROWS, "csv", lang="en")
    assert p.read_text("utf-8-sig").splitlines()[1] == "2026-10-01 08:00:00,3.25,,Ana,2"

    # Minitab: tabulaciones, punto decimal, «*» en faltantes, nombres únicos, sin apóstrofos ni «#»
    names = stat_names(HEADER + ["x" * 40])
    assert names[1:5] == ["Diámetro (mm)", "Diámetro (mm)_2", "Operador s", "No.paros"]
    assert len(names[5]) == 31
    text = stat_text(HEADER, ROWS)
    rows = [r.split("\t") for r in text.splitlines()]
    assert rows[1] == ["2026-10-01 08:00:00", "3.25", "*", "Ana", "2"]
    assert rows[2] == ["2026-10-01 08:01:00", "3.5", "*", "007", "0"]
    write_table(tmp_path / "a.txt", HEADER, ROWS, "stat")
    assert (tmp_path / "a.txt").read_bytes() == b"\xef\xbb\xbf" + text.encode("utf-8")

    # Excel: números y fechas reales, encabezado como texto
    x = tmp_path / "a.xlsx"
    assert write_table(x, HEADER, ROWS, "xlsx") == 2
    sheet = _sheet(x)
    assert sheet[0][1].get("t") == "inlineStr"
    date, num, op = sheet[1][0], sheet[1][1], sheet[2][2]  # (la celda vacía no se escribe)
    assert date.get("s") == "2" and float(date.find("m:v", NS).text) == pytest.approx(46296.3333, abs=1e-3)
    assert num.get("t") is None and num.find("m:v", NS).text == "3.25"
    assert op.get("t") == "inlineStr" and op.find(".//m:t", NS).text == "007"
    assert len(sheet[1]) == 4  # la celda vacía no se escribe


def test_monitor_history_export_formats(tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.ui.main_window import MainWindow
    ctx = build(tmp_path / "home", demo=True)
    ctx.engine.sleep = lambda s: None
    for _ in range(5):
        ctx.engine.step()
    win = MainWindow(ctx)
    out = win.export_csv(str(tmp_path / "hist"), fmt="stat")
    assert out.endswith(".txt")
    rows = [r.split("\t") for r in open(out, encoding="utf-8-sig").read().splitlines()]
    assert rows[0][0] == "fecha_hora" and any("(mm)" in h for h in rows[0]) and len(rows) >= 2
    out = win.export_csv(str(tmp_path / "hist.xlsx"), fmt="xlsx", days="7")
    assert len(_sheet(out)) >= 2
    win.close()


def test_dashboard_and_analysis_exports(tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from test_fleet_pages import make_plant

    from extrusion_monitor.fleet import FleetReader
    from extrusion_monitor.fleet_data import FleetStatsContext
    from extrusion_monitor.ui.fleet_window import FleetWindow
    from extrusion_monitor.ui.stats_page import StatsPage
    now = time.time()
    make_plant(tmp_path / "planta", now)
    w = FleetWindow(str(tmp_path / "planta"), tmp_path / "fleet.json")
    w.refresh()
    out = w.export_csv(str(tmp_path / "lineas.txt"), fmt="stat", content="trend1")
    rows = [r.split("\t") for r in open(out, encoding="utf-8-sig").read().splitlines()]
    head = rows[0]
    assert head[:4] == ["fecha_hora", "linea", "estado", "usuario"] and "Diámetro (mm)" in head and "OEE %" in head
    assert len(rows) > 2 * 60 * 20 and {r[1] for r in rows[1:]} == {"Línea 1", "Línea 2"}
    out = w.export_csv(str(tmp_path / "lineas.xlsx"), fmt="xlsx")
    assert len(_sheet(out)) == 3
    w.close()

    r = FleetReader(tmp_path / "planta")
    r.scan()
    page = StatsPage(FleetStatsContext(lambda: r, tmp_path / "home2"))
    page.add({"id": "h", "type": "histogram", "title": "", "style": {},
              "params": {"since": now - 86400, "until": now, "vars": ["diam", "vel"], "group_by": "line"}})
    out = page.export_csv(str(tmp_path / "datos"), fmt="stat")
    rows = [r.split("\t") for r in open(out, encoding="utf-8-sig").read().splitlines()]
    assert rows[0][:2] == ["fecha_hora", "Grupo"] and len(rows[0]) == 4 and len(rows) > 100
    assert {r[1] for r in rows[1:]} == {"Línea 1", "Línea 2"}
    out = page.export_csv(str(tmp_path / "res.csv"), fmt="csv", content="results")
    assert out and len(open(out, encoding="utf-8-sig").read().splitlines()) >= 2

    from extrusion_monitor.ui.export_dialog import export_table
    export_table(None, "Exportar", "x", lambda _c: (["a b"], [[1.5]]), path=str(tmp_path / "c.txt"), fmt="stat",
                 clipboard=True)
    assert app.clipboard().text().splitlines() == ["a b", "1.5"]
