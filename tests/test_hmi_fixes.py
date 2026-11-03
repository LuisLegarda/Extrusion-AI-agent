"""Ajustes probando en el HMI: captura tapada por el programa, «Guardar» sin cerrar y dashboard sin conexión."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture
def ctx(tmp_path):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.bootstrap import build
    QApplication.instance() or QApplication([])
    c = build(tmp_path / "home", demo=True)
    c.engine.sleep = lambda s: None
    return c


@pytest.fixture
def no_exclusion(monkeypatch):
    """Simula un Windows que no permite excluir las ventanas de la captura (Win 7, Win 10 1809…)."""
    from extrusion_monitor.ui import capture_guard
    monkeypatch.setattr(capture_guard, "_supported", False)
    return capture_guard


def test_covered_variables_keep_their_value_instead_of_reading_garbage(ctx):
    from extrusion_monitor.acquisition import COVERED
    e = ctx.engine
    for _ in range(3):
        e.step()
    diam = e.config.variable("diam")
    before = e.acquirer.readings["diam"].value
    assert before is not None
    r = diam.region
    e.occluders = [(r.x - 5, r.y - 5, r.w + 10, r.h + 10)]  # una ventana del programa encima de «diam»
    snap = e.step()
    rd = snap.statuses["diam"].reading
    assert rd.reason == COVERED and not rd.ok and rd.value == before and rd.fail_count == 0
    others = [st for vid, st in snap.statuses.items() if vid != "diam" and st.reading.reason == COVERED]
    assert not others  # solo lo que está debajo de la ventana
    e.occluders = []
    assert e.step().statuses["diam"].reading.ok


def test_occluders_and_clean_grab_on_windows_without_exclusion(ctx, no_exclusion):
    from PySide6.QtWidgets import QApplication, QWidget
    w = QWidget()
    w.setGeometry(100, 120, 300, 200)
    w.show()
    QApplication.processEvents()
    rects = no_exclusion.occluders((0, 0), margin=0)
    g = w.frameGeometry()
    assert (g.x(), g.y(), g.width(), g.height()) in [tuple(r) for r in rects]
    seen = []
    out = no_exclusion.grab_clean(lambda: (seen.append(w.windowOpacity()), "captura")[1], settle_s=0)
    assert out == "captura" and seen == [0.0] and w.windowOpacity() == 1.0  # transparente solo al capturar
    w.close()


def test_occluders_are_empty_where_windows_supports_exclusion(monkeypatch):
    from extrusion_monitor.ui import capture_guard
    monkeypatch.setattr(capture_guard, "_supported", True)
    assert capture_guard.occluders((0, 0)) == []
    assert capture_guard.grab_clean(lambda: "x") == "x"


def test_save_keeps_the_window_open_and_applies_the_change(ctx, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.config import Rect, Variable
    from extrusion_monitor.ui.main_window import MainWindow
    from extrusion_monitor.ui.setup_dialog import SetupDialog
    win = MainWindow(ctx)
    ocr_before = ctx.engine.ocr
    state = {}

    def run(dlg):
        dlg.show()
        dlg.config.variables.append(Variable(id="nueva", name="Nueva", region=Rect(x=10, y=10, w=40, h=20)))
        dlg._save()
        state["open_after_first"] = dlg.isVisible()
        state["first"] = [v.id for v in ctx.engine.config.variables]
        dlg.config.variable("nueva").name = "Nueva 2"
        dlg._save()
        state["label"] = dlg.lbl_saved.text()
        dlg.reject()  # «Cerrar» sin cambios pendientes: no pregunta
        return 0

    monkeypatch.setattr(SetupDialog, "exec", run)
    win.open_setup()
    QApplication.processEvents()
    assert state["open_after_first"] and "nueva" in state["first"]
    assert ctx.engine.config.variable("nueva").name == "Nueva 2"  # el segundo «Guardar» también se aplicó
    assert "✔" in state["label"]
    assert ctx.engine.ocr is ocr_before  # mismo motor OCR: no se vuelve a crear
    assert win.table.findItems("Nueva 2", __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.MatchRecursive)
    win.close()


def test_path_probe_never_blocks_on_a_dead_network_folder():
    from extrusion_monitor.fleet import PathProbe

    def hang(path):
        time.sleep(3)
        return True

    p = PathProbe("\\\\SERVIDOR\\lineas", timeout=0.2, check=hang)
    a = time.perf_counter()
    assert p.check() is False and p.ok() is False
    assert time.perf_counter() - a < 1.0  # nunca espera lo que tarda Windows en rendirse
    assert PathProbe(".", timeout=1).check() is True


def test_dashboard_without_connection_opens_and_says_so(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from extrusion_monitor.fleet import FleetSettings, PathProbe, save_fleet_settings
    from extrusion_monitor.ui import fleet_window
    cfg = tmp_path / "fleet.json"
    save_fleet_settings(cfg, FleetSettings(dir="\\\\SERVIDOR\\no-existe"))
    w = fleet_window.FleetWindow(None, cfg)
    w.probe = PathProbe(w.settings.dir, timeout=0.2, check=lambda p: time.sleep(2) or True)
    a = time.perf_counter()
    w.refresh()
    assert time.perf_counter() - a < 1.0
    assert "conexión" in w.empty.text()
    w.show_page("analyzer")  # tampoco se traba al abrir otras páginas
    assert time.perf_counter() - a < 1.5
    w.close()
