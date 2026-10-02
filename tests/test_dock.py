"""Dock: barra compacta que queda sobre el HMI al minimizar el programa."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from extrusion_monitor.config import AppConfig, DockSettings, HomeTile  # noqa: E402


@pytest.fixture
def ctx(tmp_path):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.bootstrap import build
    QApplication.instance() or QApplication([])
    c = build(tmp_path, demo=True)
    c.engine.sleep = lambda s: None
    for _ in range(6):
        c.engine.step()  # la receta del HMI queda activa (con su configuración)
    return c


def test_old_config_has_dock_disabled():
    cfg = AppConfig.model_validate_json('{"machine_name": "L1"}')
    assert cfg.dock.enabled is False and cfg.dock.edge == "top" and len(cfg.dock.tiles) == 3


def test_dock_on_minimize_and_restore(ctx):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor import navigation
    from extrusion_monitor.ui.main_window import MainWindow

    ctx.engine.config.dock = DockSettings(enabled=True, edge="bottom", size="medium", tiles=[
        HomeTile(id="a", kind="oee", kpi_chart="gauge"), HomeTile(id="b", kind="read", kpi_chart="value"),
        HomeTile(id="c", kind="var", var_ids=["diam"], chart="gauge"),
        HomeTile(id="d", kind="var", var_ids=["vel"], chart="trend", width=2),
        HomeTile(id="e", kind="machine")])  # no aplica en el dock: se ignora
    win = MainWindow(ctx)
    win.show()
    assert win.dock is None
    win.showMinimized()
    QApplication.processEvents()
    dock = win.dock
    assert dock is not None and dock.isVisible() and int(dock.winId()) in navigation.OVERLAY_HWNDS
    win.on_snapshot(ctx.engine.step())
    dock.update_snapshot(ctx.engine.last, force=True)
    assert len(dock.var_tiles) == 2 and set(dock.kpi_widgets) == {"oee", "read"}
    assert dock.kpi_widgets["read"][0].lbl_value.text().count("100")
    assert dock.var_tiles[0].gauge.value == pytest.approx(3.2, abs=0.1)
    assert "THHN" in dock.chip.text()
    # borde inferior, centrado
    geo = dock._screen_geo
    assert dock.y() + dock.height() == geo.y() + geo.height()
    assert abs((dock.x() + dock.width() / 2) - (geo.x() + geo.width() / 2)) <= 1
    win.restore_from_dock()
    QApplication.processEvents()
    assert not dock.isVisible() and int(dock.winId()) not in navigation.OVERLAY_HWNDS
    # con el dock desactivado, minimizar no lo muestra
    ctx.engine.config.dock.enabled = False
    win.showMinimized()
    QApplication.processEvents()
    assert not dock.isVisible()
    win.close()
    assert win.dock is None


def test_dock_ghost_drag_and_alarm(ctx):
    from PySide6.QtCore import QPoint, QRect

    from extrusion_monitor import navigation
    from extrusion_monitor.analysis.rules import Finding, Level
    from extrusion_monitor.ui.dock import GHOST_OPACITY, DockWindow

    ctx.engine.config.dock = DockSettings(enabled=True, edge="left", size="small")
    dock = DockWindow(ctx.engine, ctx.workspace)
    dock.show()
    geo = QRect(0, 0, 1920, 1080)
    dock.place(geo)
    assert dock.x() == 0 and not dock.horizontal
    # fantasma: casi transparente (deja pasar los clics); también mientras un recorrido hace clic
    dock.set_ghost(True)
    assert dock.windowOpacity() == pytest.approx(GHOST_OPACITY, abs=0.01)
    dock.set_ghost(False)
    navigation.overlays_pass_clicks(hold_s=5)
    dock._poll()
    assert dock._ghost
    navigation.overlay_hold_until = 0.0
    dock._poll()
    # arrastrado a otra posición: la recuerda; soltado junto a su borde: vuelve a anclarse
    dock.move(500, 300)
    dock._drag = QPoint(0, 0)
    dock.end_drag()
    assert ctx.workspace.load_state()["dock_pos"] == [500, 300]
    dock.place(geo)
    assert (dock.x(), dock.y()) == (500, 300)
    dock.move(dock.edge_pos(geo) + QPoint(10, 5))
    dock._drag = QPoint(0, 0)
    dock.end_drag()
    assert "dock_pos" not in ctx.workspace.load_state() and dock.pos() == dock.edge_pos(geo)
    # alarma nueva: parpadea y muestra el mensaje
    snap = ctx.engine.step()
    dock.update_snapshot(snap, force=True)
    assert not dock.alerting()
    snap.findings.append(Finding("TOLERANCIA", "diam", Level.ALARM, "«Diametro» fuera de tolerancia", time.time(),
                                 Level.ALARM))
    dock.update_snapshot(snap, force=True)
    assert dock.alerting() and "fuera de tolerancia" in dock.chip.text()
    dock._blink_tick()
    assert "border:3px" in dock.frame.styleSheet()
    dock.close()


def test_dock_config_dialog(ctx, monkeypatch):
    from extrusion_monitor.ui.dock_dialog import DockConfigDialog
    from extrusion_monitor.ui.main_window import MainWindow

    dlg = DockConfigDialog(ctx.config)
    kinds = [dlg.cmb_kind.itemData(i) for i in range(dlg.cmb_kind.count())]
    assert "var" in kinds and "oee" in kinds and "machine" not in kinds and "alarms" not in kinds
    dlg.chk_enabled.setChecked(True)
    dlg.cmb_edge.setCurrentIndex(dlg.cmb_edge.findData("right"))
    dlg.cmb_size.setCurrentIndex(dlg.cmb_size.findData("large"))
    dlg._add_var()
    d = dlg.dock
    assert d.enabled and d.edge == "right" and d.size == "large" and dlg.reset_position
    assert d.tiles[-1].kind == "var" and all(t.height == 1 and t.width <= 4 for t in d.tiles)

    win = MainWindow(ctx)
    monkeypatch.setattr(DockConfigDialog, "exec", lambda self: (self.chk_enabled.setChecked(True),
                                                                 self.cmb_edge.setCurrentIndex(1), True)[-1])
    win.open_dock_config()
    assert ctx.engine.config.dock.enabled and ctx.engine.config.dock.edge == "bottom"
    assert '"edge": "bottom"' in ctx.workspace.config_file.read_text("utf-8")
    win._rebuilding = True
    win.close()
