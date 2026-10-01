import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from extrusion_monitor.config import AppConfig, HomeSettings, HomeTile  # noqa: E402
from extrusion_monitor.recipes import Bounds  # noqa: E402


def test_default_home_and_old_config_without_home():
    cfg = AppConfig.model_validate_json('{"machine_name": "L1"}')
    kinds = [t.kind for t in cfg.home.tiles]
    assert kinds[:6] == ["oee", "i5", "stability", "cpk", "conform", "read"]
    assert {"machine", "alarms", "cpk_bars", "shift"} <= set(kinds)
    again = AppConfig.model_validate_json(cfg.model_dump_json())
    assert again.home == cfg.home


def test_pack_tiles_first_fit():
    from extrusion_monitor.ui.home_page import pack_tiles
    tiles = [HomeTile(id="a", width=2, height=2), HomeTile(id="b"), HomeTile(id="c", width=3),
             HomeTile(id="d"), HomeTile(id="e", width=9)]
    places = pack_tiles(tiles, 4)
    assert places[0] == (0, 0, 2, 2)
    assert places[1] == (0, 2, 1, 1)
    assert places[2] == (2, 0, 1, 3)  # no cabe junto a «a»: baja a la primera fila libre
    assert places[3] == (0, 3, 1, 1)  # rellena el hueco de la fila 0
    assert places[4] == (3, 0, 1, 4)  # ancho recortado al número de columnas


def test_zones_and_auto_scale():
    from extrusion_monitor.config import Rect, Variable
    from extrusion_monitor.ui.home_tiles import auto_scale, charts_for, zone, zone_segments
    b = Bounds(wl=97, wh=103, al=95, ah=105)
    assert zone(100, b) == "good" and zone(104, b) == "warning" and zone(94, b) == "critical"
    assert zone(1, Bounds()) == "neutral"
    assert zone(9, Bounds(ah=8)) == "critical"  # solo máximo
    lo, hi = auto_scale(b, 100, [99, 101])
    assert lo < 95 and hi > 105  # las zonas rojas quedan visibles
    assert auto_scale(b, 100, [99], fixed=(90, 110)) == (90, 110)
    pct = Variable(id="p", name="p", region=Rect(x=0, y=0, w=1, h=1), valid_min=0)
    assert auto_scale(Bounds(ah=5), 2, [1, 2], pct)[0] == 0  # no baja del mínimo válido
    segs = zone_segments(lo, hi, b)
    assert [s[2] for s in segs] == ["critical", "warning", "good", "warning", "critical"]
    assert segs[0][0] == lo and segs[-1][1] == hi
    txt = Variable(id="t", name="t", kind="text", region=Rect(x=0, y=0, w=1, h=1))
    num = Variable(id="n", name="n", region=Rect(x=0, y=0, w=1, h=1))
    assert charts_for(txt) == ("value",) and "gauge" in charts_for(num)


@pytest.fixture
def ctx(tmp_path):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.bootstrap import build
    QApplication.instance() or QApplication([])
    c = build(tmp_path, demo=True)
    c.engine.sleep = lambda s: None
    return c


def test_home_tiles_render_with_data(ctx):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.ui.main_window import MainWindow

    for _ in range(20):
        ctx.engine.step()  # la receta del HMI se activa y carga su configuración completa
    ctx.engine.config.home = HomeSettings(columns=4, tiles=[
        HomeTile(id="g", var_ids=["diam"], chart="gauge"),
        HomeTile(id="v", var_ids=["vel"], chart="value"),
        HomeTile(id="b", var_ids=["exc"], chart="bar", scale_min=0, scale_max=20),
        HomeTile(id="s", var_ids=["inyeccion"], chart="gauge"),  # selector: se muestra como estado
        HomeTile(id="t", var_ids=["diam", "vel"], chart="trend", width=2),
        HomeTile(id="h", var_ids=["diam"], chart="histogram"),
        HomeTile(id="x", var_ids=["borrada"], chart="value"),
        HomeTile(id="oee", kind="oee"),
    ])
    ctx.engine.step()
    win = MainWindow(ctx)
    win.show_page("home")
    win.home.update_snapshot(ctx.engine.last, force=True)
    win.home.refresh_oee(force=True)
    QApplication.processEvents()
    tiles = {t.tile.id: t for t in win.home.var_tiles}
    assert tiles["g"].gauge.value == pytest.approx(3.2, abs=0.1)
    assert tiles["g"].gauge.lo < tiles["g"].gauge.bounds.al
    assert "m/min" in tiles["v"].lbl_value.text()
    assert (tiles["b"].bar.lo, tiles["b"].bar.hi) == (0, 20)
    assert tiles["s"].chart == "value" and "ON" in tiles["s"].lbl_value.text()
    xs, _ = tiles["t"].curves[0].getData()
    assert xs is not None and len(xs) >= 10
    assert "n = " in tiles["h"].lbl_info.text()
    assert tiles["x"].vars == []
    assert set(win.home.cards) == {"oee"} and win.home.lst_alarms is None
    assert win.home.cards["oee"].gauge.value is not None
    win.close()


def test_home_config_dialog(ctx, monkeypatch):
    from PySide6.QtCore import Qt

    from extrusion_monitor.ui.home_config_dialog import HomeConfigDialog

    dlg = HomeConfigDialog(ctx.config)
    n = len(dlg.home.tiles)
    dlg._add_var()
    assert len(dlg.home.tiles) == n + 1 and dlg.lst.currentRow() == n
    tile = dlg.home.tiles[-1]
    dlg.cmb_chart.setCurrentIndex(dlg.cmb_chart.findData("trend"))
    assert tile.chart == "trend"

    def check(vid):
        for i in range(dlg.lst_vars.count()):
            it = dlg.lst_vars.item(i)
            if it.data(Qt.UserRole) == vid:
                it.setCheckState(Qt.Checked)

    for vid in ("z1", "z2", "z3", "diam", "exc"):
        check(vid)
    assert len(tile.var_ids) == 4 and tile.var_ids[-1] == "exc"  # máximo 4 en tendencia
    dlg.cmb_chart.setCurrentIndex(dlg.cmb_chart.findData("gauge"))
    assert tile.chart == "gauge" and len(tile.var_ids) == 1
    check("inyeccion")  # selector: solo «valor actual»
    assert tile.var_ids == ["inyeccion"] and tile.chart == "value"
    assert [dlg.cmb_chart.itemData(i) for i in range(dlg.cmb_chart.count())] == ["value"]
    dlg.sp_w.setValue(3)
    dlg.ed_title.setText("Gas")
    assert (tile.width, tile.title) == (3, "Gas")
    # los indicadores numéricos se pueden repetir (OEE en gauge y en gráfica de tiempo)…
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dlg.cmb_kind.setCurrentIndex(dlg.cmb_kind.findData("oee"))
    assert tile.kind == "oee"
    assert [dlg.cmb_chart.itemData(i) for i in range(dlg.cmb_chart.count())] == ["gauge", "value", "trend"]
    dlg.cmb_chart.setCurrentIndex(dlg.cmb_chart.findData("trend"))
    dlg.cmb_range.setCurrentIndex(dlg.cmb_range.findData(0))  # turno actual
    assert tile.kpi_chart == "trend" and tile.range_s == 0
    # …pero los únicos (estado de la máquina, alarmas…) no
    dlg.cmb_kind.setCurrentIndex(dlg.cmb_kind.findData("machine"))
    assert tile.kind == "oee"
    dlg._remove()
    assert len(dlg.home.tiles) == n
    dlg.accept()
    assert dlg.result()


def test_kpi_tiles_gauge_value_and_trend(ctx):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.ui.home_tiles import KpiTrendTile, KpiValueTile
    from extrusion_monitor.ui.main_window import MainWindow

    for _ in range(5):
        ctx.engine.step()
    assert ctx.engine.kpis["oee"] is not None and ctx.engine.kpis["read"] == 100
    ctx.engine.config.home = HomeSettings(columns=4, tiles=[
        HomeTile(id="g", kind="oee"),
        HomeTile(id="t", kind="oee", kpi_chart="trend", range_s=0, width=2),
        HomeTile(id="q", kind="quality", kpi_chart="value"),
        HomeTile(id="r", kind="read", kpi_chart="trend", range_s=3600),
    ])
    ctx.engine.kpis_ts -= 60  # forzar otro registro de indicadores
    ctx.engine.step()
    win = MainWindow(ctx)
    win.show_page("home")
    win.home.update_snapshot(ctx.engine.last, force=True)
    win.home.refresh_oee(force=True)
    QApplication.processEvents()
    w = win.home.kpi_widgets
    assert len(w["oee"]) == 2 and win.home.cards["oee"].gauge.value is not None
    trend = next(x for x in w["oee"] if isinstance(x, KpiTrendTile))
    xs, _ = trend.curve.getData()
    assert xs is not None and len(xs) >= 2  # historial guardado + valor actual
    assert isinstance(w["quality"][0], KpiValueTile) and "%" in w["quality"][0].lbl_value.text()
    xs, _ = w["read"][0].curve.getData()
    assert len(xs) >= 2
    assert len(ctx.engine.historian.samples("kpi:oee", 0)) >= 2
    win.close()
