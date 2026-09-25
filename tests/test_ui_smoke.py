import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


def test_main_window_and_dialogs(tmp_path):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.ui.main_window import MainWindow
    from extrusion_monitor.ui.recipe_dialog import RecipeDialog
    from extrusion_monitor.ui.setup_dialog import SetupDialog

    app = QApplication.instance() or QApplication([])
    ctx = build(tmp_path, demo=True)
    win = MainWindow(ctx)
    for _ in range(5):
        ctx.engine.step()
    app.processEvents()
    assert win.table.rowCount() == len(ctx.config.variables)
    dlg = SetupDialog(ctx, win)
    dlg.lst_vars.setCurrentRow(1)
    assert "→" in dlg.lbl_result.text()
    dlg._save()
    rd = RecipeDialog(ctx, win)
    assert rd.table.rowCount() > 0
    rd._save()
    win.close()
