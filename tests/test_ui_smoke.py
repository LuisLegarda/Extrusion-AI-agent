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


def test_main_window_and_dialogs(ctx, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from extrusion_monitor.ui.main_window import MainWindow
    from extrusion_monitor.ui.recipe_dialog import RecipeDialog
    from extrusion_monitor.ui.setup_dialog import SetupDialog

    win = MainWindow(ctx)
    for _ in range(5):
        ctx.engine.step()
    QApplication.processEvents()
    linked = {v.setpoint_var for v in ctx.config.variables if v.setpoint_var}
    assert len(win.table._rows) == len(ctx.config.variables) - len(linked)
    row = win.table._rows["z1"]
    assert row.text(1) == "160" and row.text(2) != ""  # consigna y medición en la misma fila

    dlg = SetupDialog(ctx, win)
    dlg._select_key(("var", "z1"))
    assert "→" in dlg.lbl_result.text()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    dlg._save()
    rd = RecipeDialog(ctx, win)
    rd._save()
    win.close()


def test_page_tree_pair_and_series(ctx, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    from extrusion_monitor.config import Rect
    from extrusion_monitor.ui.setup_dialog import SeriesDialog, SetupDialog

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    dlg = SetupDialog(ctx)
    names = iter(["EXT1", "Overview", "Cylinder 1"])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: (next(names), True))

    dlg.view.selection = Rect(x=400, y=760, w=60, h=30)
    dlg._new_root_page()
    assert dlg.config.page("ext1").anchor is not None
    dlg.view.selection = None
    dlg._new_child_page()
    child = dlg.config.page("ext1_overview")
    assert child.parent == "ext1" and child.anchor is None

    dlg._start_pair()
    dlg._rect_drawn(Rect(x=10, y=10, w=50, h=20))  # consigna
    dlg._rect_drawn(Rect(x=10, y=40, w=50, h=20))  # medición
    pv = dlg.config.variable("ext1_overview_cylinder_1")
    sp = dlg.config.variable(pv.setpoint_var)
    assert pv.kind == "actual" and sp.kind == "setpoint" and sp.page == pv.page == "ext1_overview"

    dlg._select_key(("var", pv.id))
    monkeypatch.setattr(SeriesDialog, "exec", lambda self: (self.sp_count.setValue(4), self.sp_dx.setValue(140),
                                                            True)[-1])
    dlg._series()
    c5 = dlg.config.variable("ext1_overview_cylinder_5")
    assert c5.region.x == 10 + 4 * 140
    assert dlg.config.variable(c5.setpoint_var).name == "Cylinder 5 consigna"
    assert "EXT1 › Overview › Cylinder 5" == dlg.config.var_label(c5)
    assert not dlg.config.validate_references()
