"""Gráficas: alto ajustable con el ratón y bloqueo del zoom con la rueda."""
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


def test_resizable_box_drag_and_reset():
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel

    from extrusion_monitor.ui.resizable import ResizableStack
    QApplication.instance() or QApplication([])
    st = ResizableStack(min_h=120)
    st.resize(400, 600)
    a, b = QLabel("a"), QLabel("b")
    box = st.add(a)
    st.add(b)
    st.show()
    QApplication.processEvents()
    assert box.fixed is None  # automático: llena el espacio
    box.set_height(380)
    assert box.height() == 380 and box.fixed == 380
    box.set_height(40)
    assert box.fixed == 120  # nunca menos que el mínimo
    QTest.mouseDClick(box.grip, Qt.LeftButton, pos=QPoint(5, 3))
    assert box.fixed is None
    st.remove(a)
    assert st.box(a) is None and st.box(b) is not None


def test_trend_spc_and_control_use_resizable_heights(ctx):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.ui.main_window import MainWindow
    win = MainWindow(ctx)
    for _ in range(3):
        ctx.engine.step()
    QApplication.processEvents()
    assert win.trends.plots
    for p in win.trends.plots.values():
        assert win.trends.stack.box(p["widget"]) is not None
    for card in win.stats_panel.cards.values():
        assert win.stats_panel.area.box(card) is not None
    for card in win.control_page.cards.values():
        assert win.control_page.area.box(card) is not None
    win._detach()


def test_wheel_lock_scrolls_page_instead_of_zooming(ctx):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.ui.main_window import MainWindow
    from extrusion_monitor.ui.wheel_lock import lock
    win = MainWindow(ctx)
    win.resize(1400, 900)
    win.show()
    for _ in range(3):
        ctx.engine.step()
    win.show_page("trends")
    win._replot()
    QApplication.processEvents()
    w = next(iter(win.trends.plots.values()))["widget"]
    vb = w.getViewBox()

    def wheel():
        pos = QPointF(w.viewport().width() / 2, w.viewport().height() / 2)
        ev = QWheelEvent(pos, w.viewport().mapToGlobal(pos), QPoint(0, 0), QPoint(0, 240), Qt.NoButton,
                         Qt.NoModifier, Qt.NoScrollPhase, False)
        QApplication.sendEvent(w.viewport(), ev)
        QApplication.processEvents()

    assert win.act_wheel.isChecked() and lock().enabled  # bloqueado por defecto
    win.act_wheel.setChecked(False)
    win.act_wheel.setChecked(True)
    assert lock().enabled and ctx.workspace.load_state()["ui"]["lock_wheel"] is True
    before = vb.viewRange()
    wheel()
    assert vb.viewRange() == before  # bloqueado: sin zoom
    win.act_wheel.setChecked(False)
    wheel()
    assert vb.viewRange() != before  # desbloqueado: la rueda hace zoom
    win._detach()
