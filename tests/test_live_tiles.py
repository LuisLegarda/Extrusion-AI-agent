"""Variables en vivo: mosaicos por variable configurables (gráfico, tamaño, tiempo) y la tabla."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture
def ctx(tmp_path):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.bootstrap import build
    QApplication.instance() or QApplication([])
    return build(tmp_path, demo=True)


def test_live_tiles_show_status_value_tolerance_and_reading(ctx):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.ui.main_window import MainWindow
    win = MainWindow(ctx)
    win.resize(1400, 900)
    win.show()
    win.show_page("variables")
    for _ in range(4):
        ctx.engine.step()
    win.on_snapshot(ctx.engine.last)
    QApplication.processEvents()
    lt = win.live_tiles
    assert win.live_page.mode == "tiles" and lt.tiles
    linked = {v.setpoint_var for v in ctx.config.variables if v.setpoint_var}
    assert {t.vid for t in lt.tiles} == {v.id for v in ctx.config.variables if v.id not in linked}
    diam = next(t for t in lt.tiles if t.vid == "diam")
    lt.update_snapshot(ctx.engine.last, force=True)
    assert diam.pill.text() and "Tolerancia" in diam.lbl_tol.text() and "lectura" in diam.lbl_tol.text()
    # filtrar
    lt.filter.setText("diametro")
    QApplication.processEvents()
    assert diam.isVisible() and not any(t.isVisible() for t in lt.tiles if t.vid == "vel")
    lt.filter.clear()
    # cambiar gráfico, tamaño y tiempo de un mosaico: se guarda en la vista
    lt.set_pref("diam", chart="histogram")
    lt.set_pref("diam", w=2, h=2, range=3600)
    diam = next(t for t in lt.tiles if t.vid == "diam")
    assert diam.chart == "histogram" and (diam.tile.width, diam.tile.height) == (2, 2) and diam.tile.range_s == 3600
    win._write_view()
    view = ctx.workspace.load_state()["view"]
    assert view["live_tiles"]["diam"]["chart"] == "histogram"
    # la vista de tabla sigue disponible y se recuerda
    win.live_page.set_mode("table")
    win._save_view()
    win._write_view()
    assert ctx.workspace.load_state()["view"]["live_mode"] == "table"
    win2 = MainWindow(ctx)
    assert win2.live_page.mode == "table"
    assert next(t for t in win2.live_tiles.tiles if t.vid == "diam").chart == "histogram"
    win2._detach()
    win._detach()


def test_tile_changes_need_supervisor_when_protected(ctx):
    from extrusion_monitor.personnel import Person, Personnel, hash_password
    from extrusion_monitor.ui.main_window import MainWindow
    Personnel([Person("Ana", "supervisor", "200", password=hash_password("clave1"))]).save(ctx.workspace.home)
    win = MainWindow(ctx)
    win.gate.offer = lambda reason: False
    before = next(t for t in win.live_tiles.tiles if t.vid == "diam").chart
    win.live_tiles.set_pref("diam", chart="gauge" if before != "gauge" else "value")
    assert next(t for t in win.live_tiles.tiles if t.vid == "diam").chart == before
    win._detach()
