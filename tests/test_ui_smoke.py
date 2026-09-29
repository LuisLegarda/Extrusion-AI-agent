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
    win.show_page("variables")
    for _ in range(5):
        ctx.engine.step()
    QApplication.processEvents()
    linked = {v.setpoint_var for v in ctx.config.variables if v.setpoint_var}
    assert len(win.table._rows) == len(ctx.config.variables) - len(linked)
    row = win.table._rows["z1"]
    assert row.text(1) == "160" and row.text(2) != ""  # consigna y medición en la misma fila

    dlg = SetupDialog(ctx, win)
    dlg._select_key(("var", "diam"))
    assert "variantes coinciden" in dlg.lbl_result.text(), dlg.lbl_result.text()
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
    names = iter(["BET10", "Overview", "Cylinder 1"])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: (next(names), True))

    dlg.view.selection = Rect(x=400, y=760, w=60, h=30)
    dlg._new_root_page()
    assert dlg.config.page("bet10").anchor is not None
    dlg.view.selection = None
    dlg._new_child_page()
    child = dlg.config.page("bet10_overview")
    assert child.parent == "bet10" and child.anchor is None

    dlg._start_pair()
    dlg._rect_drawn(Rect(x=10, y=10, w=50, h=20))  # consigna
    dlg._rect_drawn(Rect(x=10, y=40, w=50, h=20))  # medición
    pv = dlg.config.variable("bet10_overview_cylinder_1")
    sp = dlg.config.variable(pv.setpoint_var)
    assert pv.kind == "actual" and sp.kind == "setpoint" and sp.page == pv.page == "bet10_overview"

    dlg._select_key(("var", pv.id))
    monkeypatch.setattr(SeriesDialog, "exec", lambda self: (self.sp_count.setValue(4), self.sp_dx.setValue(140),
                                                            True)[-1])
    dlg._series()
    c5 = dlg.config.variable("bet10_overview_cylinder_5")
    assert c5.region.x == 10 + 4 * 140
    assert dlg.config.variable(c5.setpoint_var).name == "Cylinder 5 consigna"
    assert "BET10 › Overview › Cylinder 5" == dlg.config.var_label(c5)
    assert not dlg.config.validate_references()


def test_record_and_test_tour_in_demo(ctx, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from extrusion_monitor.simulator import nav_center
    from extrusion_monitor.ui.setup_dialog import SetupDialog

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(str(a[2])))
    ctx.engine.sleep = lambda s: None
    sim = ctx.engine.source.sim
    dlg = SetupDialog(ctx)
    tab = dlg.tour_tab
    tab.tour.steps.clear()
    tab.tour.return_clicks.clear()
    tab.patches.clear()
    tab.refresh()
    for page in ("ext1", "linea"):
        tab.cmb_page.setCurrentIndex(tab.cmb_page.findData(page))
        tab._add_step()
        tab._toggle_record()
        tab._point_clicked(*nav_center(page))  # clic grabado y ejecutado en el HMI
        assert sim.page == page
        tab._toggle_record()
    tab.lst.setCurrentRow(tab.lst.count() - 1)  # regreso a la principal
    tab._toggle_record()
    tab._point_clicked(*nav_center("principal"))
    tab._toggle_record()
    assert sim.page == "principal"
    tab._test()
    assert "OK" in tab.lbl_status.text(), tab.lbl_status.text()
    dlg._save()
    assert len(list(ctx.workspace.clicks_dir.glob("*.png"))) == 3


def test_analysis_tabs_and_behavior_dialog(ctx, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: warnings.append(a[2]))

    from extrusion_monitor.ui.behavior_dialog import BehaviorDialog
    from extrusion_monitor.ui.main_window import MainWindow

    ctx.engine.sleep = lambda s: None
    win = MainWindow(ctx)
    for _ in range(12):
        ctx.engine.step()
    for key in ("spc", "corr", "behavior"):
        win.show_page(key)
        win._refresh_analysis(force=True)
    QApplication.processEvents()
    assert "n =" in win.stats_panel.lbl.text()
    dlg = BehaviorDialog(ctx, win, preselect=["rpm", "carga"])
    dlg.rb_last.setChecked(True)
    dlg._train()  # pocos datos: muestra aviso sin fallar
    assert warnings and "muestras" in warnings[-1]
    win.close()


def test_kpi_dashboard(ctx):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.ui.main_window import MainWindow

    ctx.engine.sleep = lambda s: None
    win = MainWindow(ctx)
    win.show()
    for _ in range(20):
        ctx.engine.step()
    win.show_page("kpi")
    QApplication.processEvents()
    win.kpi.refresh()
    assert win.kpi.result is not None and win.kpi.result.run_s > 0
    assert win.kpi.tbl_other.rowCount() > 5
    win.close()


def test_ocr_diagnosis_dialog(ctx):
    from extrusion_monitor.ui.ocr_diagnosis import DiagnosisDialog
    frame = ctx.engine.grab_frame()
    dlg = DiagnosisDialog(ctx.config, frame, ctx.template_ocr, {"principal"})
    assert "OK" in dlg.summary.text()


def test_report_tab_and_tour_prompt(ctx, monkeypatch, tmp_path):
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QApplication, QMessageBox

    from extrusion_monitor.ui.main_window import MainWindow
    from extrusion_monitor.ui.setup_dialog import SetupDialog

    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(str(a[2])))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    ctx.engine.sleep = lambda s: None
    for _ in range(5):
        ctx.engine.step()
    dlg = SetupDialog(ctx)
    tab = dlg.report_tab
    tab._new()
    tab._add_trigger()
    tab.cmb_add_var.setCurrentIndex(tab.cmb_add_var.findData("diam"))
    tab._add_var()
    tab.ed_dir.setText(str(tmp_path / "rep"))
    tab._commit()
    kind = tab.tbl_trg.cellWidget(0, 0)
    kind.setCurrentIndex(kind.findData("cross"))  # cambia el tipo: se reconstruye la fila
    assert tab.report.triggers[0].kind == "cross" and tab.report.triggers[0].var_id
    tab._preview()
    assert opened and list((tmp_path / "rep").glob("*.pdf"))

    tours = dlg.tour_tab
    tours._new_tour()
    tours.chk_confirm.setChecked(True)
    tours.cmb_off.setCurrentIndex(tours.cmb_off.findData("linea"))
    assert tours.tour.confirm and tours.tour.off_page == "linea"
    tours._del_tour()
    dlg._save()

    win = MainWindow(ctx)
    t = ctx.config.tours[0]
    t.confirm = True
    ctx.engine.scheduler.reconfigure(ctx.config)
    ctx.engine.scheduler.rt(t.id).last_run = None
    snap = ctx.engine.step()  # dispara por intervalo: aviso con cuenta regresiva
    assert t.id in snap.prompts
    win.on_snapshot(snap)
    assert t.id in win._prompts
    win._prompts[t.id]._snooze()
    assert not ctx.engine.pending_prompts()
    win.on_snapshot(ctx.engine.step())
    assert not win._prompts
    QApplication.processEvents()
    win._fill_report_menu()
    win.close()


def test_trend_range_and_auto_y(ctx):
    import numpy as np
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.ui.main_window import MainWindow, y_range
    # Límites 100 ± 5: con un pico en pantalla la escala lo incluye; sin él vuelve a los límites.
    lo, hi = y_range(np.array([100.0, 101, 99]), [95, 105, 100])
    assert 93 < lo < 95 and 105 < hi < 107
    lo, hi = y_range(np.array([100.0, 160, 99]), [95, 105, 100])
    assert hi > 160
    lo, hi = y_range(np.array([2.0, 3.0]), [None, 5.0])  # solo máximo
    assert lo < 2 and 5 < hi < 6
    ctx.engine.sleep = lambda s: None
    win = MainWindow(ctx)
    for _ in range(4):
        ctx.engine.step()
    win._plot_toggled("diam", True)
    win.trends.cmb_range.setCurrentIndex(win.trends.cmb_range.findData(4 * 3600))  # desde el historial
    win._replot()
    QApplication.processEvents()
    (x0, x1), (y0, y1) = win.trends.plots["diam"]["widget"].viewRange()
    assert x1 - x0 > 3 * 3600
    assert y0 < 3.15 and y1 > 3.25  # límites de alarma 3.20 ± 0.05 visibles
    win.close()


def test_navigation_and_home_dashboard(ctx):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.ui.main_window import NAV_ITEMS, MainWindow
    ctx.engine.sleep = lambda s: None
    win = MainWindow(ctx)
    win.show()
    for _ in range(25):
        ctx.engine.step()
    QApplication.processEvents()
    snap = ctx.engine.last
    win.home.update_snapshot(snap, force=True)
    win.home.refresh_oee(force=True)
    cards = win.home.cards
    assert cards["read"].gauge.value is not None and cards["read"].gauge.value > 50
    assert cards["conform"].gauge.value is not None
    assert cards["oee"].gauge.value is not None  # la demo tiene OEE configurado
    assert "Receta" in win.home.lbl_state.text()
    for key, _label, _icon in NAV_ITEMS:  # todas las páginas abren sin error
        win.show_page(key)
        QApplication.processEvents()
        win.on_snapshot(snap)
        assert win.current_page() == key
    win.show_page("reports")
    win.reports_page.refresh()
    cards["cpk"].clicked.emit("spc")
    assert win.current_page() == "spc"
    win.close()


def test_language_and_theme_switch(ctx, tmp_path):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor import i18n
    from extrusion_monitor.ui import theme
    from extrusion_monitor.ui.main_window import MainWindow, apply_ui_prefs, rebuilt_windows
    assert i18n.translate_text("Recetas") == "Recetas"  # español por defecto
    i18n.set_lang("en")
    try:
        assert i18n.translate_text("Recetas") == "Recipes"
        assert i18n.translate_text("📋 Recetas") == "📋 Recipes"
        assert i18n.translate_text("<b>Estado de la máquina</b>") == "<b>Machine status</b>"
        assert i18n.tr("{ok} de {n} variables", ok=3, n=4) == "3 of 4 variables"
        assert i18n.translate_text("texto sin traducción") == "texto sin traducción"
    finally:
        i18n.set_lang("es")
    ctx.engine.sleep = lambda s: None
    i18n.Translator().install(QApplication.instance())
    win = MainWindow(ctx)
    win.show()
    ctx.engine.step()
    win._set_ui_pref("lang", "en")
    new = rebuilt_windows[-1]
    QApplication.processEvents()
    assert new.menuBar().actions()[0].text() == "&File"
    assert "Home" in new.nav.item(0).text()
    assert ctx.workspace.load_state()["ui"]["lang"] == "en"
    new._set_ui_pref("theme", "dark")
    dark = rebuilt_windows[-1]
    QApplication.processEvents()
    assert theme.is_dark() and QApplication.instance().palette().window().color().name() == theme.c("page")
    assert dark.engine.listeners.count(dark.bridge.snapshot.emit) == 1 and len(dark.engine.listeners) == 1
    dark.on_snapshot(ctx.engine.step())
    apply_ui_prefs({})  # vuelve a español / claro para las demás pruebas
    dark.close()
