"""Guardar la configuración: no se pierde el trabajo (recorridos) por pendientes en otras partes."""
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture
def ctx(tmp_path):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.bootstrap import build
    QApplication.instance() or QApplication([])
    c = build(tmp_path, demo=True)
    c.engine.sleep = lambda s: None
    return c


def _record_tour(dlg):
    from extrusion_monitor.simulator import nav_center
    tab = dlg.tour_tab
    tab._new_tour()
    tab.cmb_page.setCurrentIndex(tab.cmb_page.findData("ext1"))
    tab._add_step()
    tab._toggle_record()
    tab._point_clicked(*nav_center("ext1"))
    tab._toggle_record()
    return tab.tour


def test_save_with_pending_problems_keeps_tours(ctx, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from extrusion_monitor.ui.main_window import MainWindow
    from extrusion_monitor.ui.setup_dialog import SetupDialog

    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a[2]), QMessageBox.Save)[1])
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(str(a[2])))
    for _ in range(3):
        ctx.engine.step()  # la receta que muestra el HMI queda activa
    assert ctx.engine.state.recipe
    win = MainWindow(ctx)

    def run(self):
        _record_tour(self)
        self.tour_tab._new_tour()  # otro recorrido sin pasos: pendiente, pero no impide guardar
        self._save()
        return self.result()

    monkeypatch.setattr(SetupDialog, "exec", run)
    win.open_setup()
    assert asked and "no tiene pasos" in asked[0]
    names = [t.name for t in ctx.config.tours]
    assert len(names) == 3
    saved = json.loads(ctx.workspace.config_file.read_text(encoding="utf-8"))
    assert [t["name"] for t in saved["tours"]] == names
    # el perfil de la receta activa también los tiene (al volver a cargarla no se pierden)
    from extrusion_monitor.profiles import profile_dir
    prof = json.loads((profile_dir(ctx.workspace, ctx.engine.state.recipe) / "config.json").read_text("utf-8"))
    assert [t["name"] for t in prof["tours"]] == names
    for _ in range(3):
        ctx.engine.step()
        win.on_snapshot(ctx.engine.last)
    dlg = SetupDialog(ctx)
    combo = dlg.tour_tab.cmb_tour
    assert [combo.itemText(i) for i in range(combo.count())] == names
    win.close()


def test_critical_problem_blocks_save(ctx, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from extrusion_monitor.ui.setup_dialog import SetupDialog

    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    dlg = SetupDialog(ctx)
    dlg.config.variables.append(dlg.config.variables[0].model_copy())
    dlg._save()
    assert warned and "duplicados" in warned[0]
    assert not dlg.result()


def test_close_with_unsaved_changes_asks(ctx, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from extrusion_monitor.ui.setup_dialog import SetupDialog

    asked = []
    dlg = SetupDialog(ctx)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(1), QMessageBox.Cancel)[1])
    dlg.reject()  # sin cambios: se cierra sin preguntar
    assert not asked and dlg.result() == 0

    dlg = SetupDialog(ctx)
    dlg.show()
    _record_tour(dlg)
    dlg.reject()
    assert asked and dlg.isVisible()  # «Cancelar»: sigue abierta con el trabajo
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    dlg.reject()
    assert not dlg.isVisible()


def test_save_profile_with_locked_leftover(ctx, monkeypatch):
    import shutil

    from extrusion_monitor import profiles

    name = ctx.engine.state.recipe or "THHN-12AWG-NEGRO"
    dest = profiles.profile_dir(ctx.workspace, name)
    profiles.save_profile(ctx.workspace, name, ctx.config)
    old = dest.with_name(dest.name + ".old")
    old.mkdir(exist_ok=True)
    (old / "bloqueado.png").write_bytes(b"x")
    real = shutil.rmtree
    # Windows: la carpeta .old no se deja borrar (un archivo abierto)
    monkeypatch.setattr(shutil, "rmtree", lambda p, ignore_errors=False: None if str(p).endswith(".old")
                        else real(p, ignore_errors=ignore_errors))
    ctx.config.machine_name = "Línea nueva"
    profiles.save_profile(ctx.workspace, name, ctx.config)
    assert json.loads((dest / "config.json").read_text("utf-8"))["machine_name"] == "Línea nueva"
