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

    ctx.engine.config.dock = DockSettings(enabled=True, edge="bottom", thickness=132, tiles=[
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
    o, size = dock.origin(), dock.total_size()
    assert o.y() + size.height() == geo.y() + geo.height()
    assert abs((o.x() + size.width() / 2) - (geo.x() + geo.width() / 2)) <= 1
    # la agarradera es una pieza aparte, pegada al cuerpo, y también es del dock (captura y recorridos)
    assert dock.handle.isVisible() and dock.x() == o.x() + dock.handle.width() + 2
    assert int(dock.handle.winId()) in navigation.OVERLAY_HWNDS
    win.restore_from_dock()
    QApplication.processEvents()
    assert not dock.isVisible() and not dock.handle.isVisible()
    assert int(dock.winId()) not in navigation.OVERLAY_HWNDS
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

    ctx.engine.config.dock = DockSettings(enabled=True, edge="left", size="small")  # formato anterior
    assert ctx.engine.config.dock.thickness == 96
    dock = DockWindow(ctx.engine, ctx.workspace)
    dock.show()
    geo = QRect(0, 0, 1920, 1080)
    dock.place(geo)
    assert dock.origin().x() == 0 and not dock.horizontal and dock.y() > dock.handle.y()
    # fantasma: casi transparente (deja pasar los clics); también mientras un recorrido hace clic
    dock.set_ghost(True)
    assert dock.windowOpacity() == pytest.approx(GHOST_OPACITY, abs=0.01)
    # …pero la agarradera sigue sólida: se puede arrastrar y restaurar aunque el dock esté translúcido
    assert dock.handle.windowOpacity() == 1.0
    restored = []
    dock.restore.connect(lambda: restored.append(1))
    dock.handle.btn.click()
    assert restored
    dock.set_ghost(False)
    navigation.overlays_pass_clicks(hold_s=5)
    dock._poll()
    assert dock._ghost
    navigation.overlay_hold_until = 0.0
    dock._poll()
    # arrastrado a otra posición: la recuerda; soltado junto a su borde: vuelve a anclarse
    start = dock.origin()
    dock.begin_drag(start + QPoint(5, 5))
    dock.drag_to(QPoint(505, 305))
    dock.end_drag()
    assert ctx.workspace.load_state()["dock_pos"] == [500, 300]
    dock.place(geo)
    assert (dock.origin().x(), dock.origin().y()) == (500, 300)
    assert dock.y() == 300 + dock.handle.height() + 2  # el cuerpo se mueve con la agarradera
    dock.begin_drag(dock.origin())
    dock.drag_to(dock.edge_pos(geo) + QPoint(10, 5))
    dock.end_drag()
    assert "dock_pos" not in ctx.workspace.load_state() and dock.origin() == dock.edge_pos(geo)
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
    dlg.sp_thick.setValue(40)
    assert "no caben gráficas" in dlg.lbl_thick.text()
    dlg._add_var()
    d = dlg.dock
    assert d.enabled and d.edge == "right" and d.thickness == 40 and d.compact and dlg.reset_position
    assert d.tiles[-1].kind == "var" and all(t.height == 1 and t.width <= 4 for t in d.tiles)

    win = MainWindow(ctx)
    monkeypatch.setattr(DockConfigDialog, "exec", lambda self: (self.chk_enabled.setChecked(True),
                                                                 self.cmb_edge.setCurrentIndex(1), True)[-1])
    win.open_dock_config()
    assert ctx.engine.config.dock.enabled and ctx.engine.config.dock.edge == "bottom"
    assert '"edge": "bottom"' in ctx.workspace.config_file.read_text("utf-8")
    win._rebuilding = True
    win.close()


def test_thin_dock_switches_to_value_with_color(ctx):
    """Muy delgado para gráficas: cada indicador pasa a nombre + valor con color según su rango."""
    from extrusion_monitor.analysis.rules import Level
    from extrusion_monitor.ui import theme
    from extrusion_monitor.ui.dock import CompactTile, DockWindow

    tiles = [HomeTile(id="a", kind="oee", kpi_chart="gauge"),
             HomeTile(id="c", kind="var", var_ids=["diam"], chart="trend", width=3),
             HomeTile(id="s", kind="var", var_ids=["inyeccion"], chart="value")]
    ctx.engine.config.dock = DockSettings(enabled=True, edge="top", thickness=132, tiles=tiles)
    dock = DockWindow(ctx.engine, ctx.workspace)
    assert not any(isinstance(w, CompactTile) for w in dock.var_tiles) and dock.var_tiles[0].plot is not None
    assert dock.height() == 132

    ctx.engine.config.dock = DockSettings(enabled=True, edge="top", thickness=40, tiles=tiles)
    dock.rebuild()
    assert dock.height() == 40  # mide exactamente el grosor configurado (el largo depende del texto)
    assert all(isinstance(w, CompactTile) for w in dock.var_tiles + dock.kpi_widgets["oee"])
    snap = ctx.engine.step()
    dock.update_snapshot(snap, force=True)
    diam, sel = dock.var_tiles
    assert "3.2" in diam.lbl.text() and theme.c("good") in diam.lbl.text()  # dentro de límites: verde
    assert "ON" in sel.lbl.text()
    assert "%" in dock.kpi_widgets["oee"][0].lbl.text()
    snap.statuses["diam"].level = Level.ALARM
    dock.update_snapshot(snap, force=True)
    assert theme.c("critical") in diam.lbl.text()  # en alarma: rojo
    dock.close()


def test_side_dock_uses_thickness_as_width(ctx):
    """A la izquierda o derecha el grosor es el ancho del dock (arriba/abajo, su alto)."""
    from extrusion_monitor.ui.dock import CompactTile, DockWindow

    tiles = [HomeTile(id="a", kind="oee", kpi_chart="gauge"), HomeTile(id="c", kind="var", var_ids=["diam"], chart="value")]
    for edge in ("left", "right"):
        for thick in (60, 110, 160):
            ctx.engine.config.dock = DockSettings(enabled=True, edge=edge, thickness=thick, tiles=tiles)
            dock = DockWindow(ctx.engine, ctx.workspace)
            assert dock.width() == thick and dock.handle.width() == thick and dock.height() > thick
            assert all(w.width() <= thick for w in dock.var_tiles + dock.kpi_widgets["oee"])
            assert isinstance(dock.var_tiles[0], CompactTile) == (thick < 84)
            dock.close()
    ctx.engine.config.dock = DockSettings(enabled=True, edge="bottom", thickness=110, tiles=tiles)
    dock = DockWindow(ctx.engine, ctx.workspace)
    assert dock.height() == 110 and dock.width() > 110
    dock.close()
