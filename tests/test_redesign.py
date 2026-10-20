"""Rediseño: búsqueda, personal en turno, tarjetas de estado y dona de causas de paro."""
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
    return build(tmp_path, demo=True)


def test_match_ignores_accents_case_and_typos():
    from extrusion_monitor.ui.search import clean_action_text, match_score
    assert match_score("presion", "Presión fundido") > 0
    assert match_score("DIAM", "Diámetro ext.") > 0
    assert match_score("diametor", "Diámetro ext.") > 0  # error de tecleo
    assert match_score("zona 3", "EXT1 › Zona 3 [°C]") > match_score("zona", "EXT1 › Zona 3 [°C]")
    assert match_score("velocidad", "Diámetro ext.") == 0
    assert clean_action_text("🛟 Crear &respaldo de la configuración…") == "Crear respaldo de la configuración"


def test_parse_written_times():
    from extrusion_monitor.ui.search import parse_time
    now = time.mktime((2026, 10, 20, 15, 0, 0, 0, 0, -1))
    ts, _ = parse_time("14:30", now)
    assert now - ts == 30 * 60
    ts, _ = parse_time("16:00", now)  # todavía no son las 16:00: la de ayer
    assert now - ts == 23 * 3600
    ts, _ = parse_time("ayer 14:30:15", now)
    assert now - ts == 86400 + 30 * 60 - 15
    ts, _ = parse_time("hace 2 h", now)
    assert now - ts == 7200
    ts, _ = parse_time("90 min ago", now)
    assert now - ts == 5400
    ts, _ = parse_time("19/10 08:00", now)
    assert time.localtime(ts)[:5] == (2026, 10, 19, 8, 0)
    ts, _ = parse_time("turno", now, ["06:00", "14:00", "22:00"])
    assert time.localtime(ts)[3] == 14
    ts, _ = parse_time("turno anterior", now, ["06:00", "14:00", "22:00"])
    assert time.localtime(ts)[3] == 6
    assert parse_time("25:00", now) is None and parse_time("diámetro", now) is None


def test_personnel_catalog_and_crew(tmp_path):
    from extrusion_monitor.personnel import Person, Personnel, capture_names, crew
    Personnel([Person("Ana", "supervisor"), Person("Luis"), Person("Pedro", active=False)]).save(tmp_path)
    p = Personnel.load(tmp_path)
    assert p.names(["operator"]) == ["Luis"] and p.names(["supervisor"]) == ["Ana"]
    assert capture_names(tmp_path, ["Luis", "Viejo"]) == ["Ana", "Luis", "Viejo"]
    assert crew({}) == {"user": "", "role": "", "shift_key": ""}
    assert crew({"crew": {"operator": "Luis"}})["user"] == "Luis"  # formato anterior
    assert Personnel.load(tmp_path / "nada").people == []


def test_downtime_rows_group_by_reason_and_unknown():
    from extrusion_monitor.ui.home_status import downtime_rows
    recs = [{"kind": "downtime", "reason": "Cambio de dado", "duration_s": 600},
            {"kind": "downtime", "reason": "Cambio de dado", "duration_s": 300},
            {"kind": "downtime", "reason": "Comida", "planned": 1, "duration_s": 1800},
            {"kind": "quality", "reason": "Burbuja", "duration_s": 999}]
    rows, total = downtime_rows(recs, stop_s=3000)
    names = [r[0] for r in rows]
    assert names[0].startswith("Comida") and "Cambio de dado" in names and "Sin identificar" in names
    assert dict((r[0], r[1]) for r in rows)["Cambio de dado"] == 900 and total == 3000


def test_search_box_variables_actions_and_time(ctx, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from extrusion_monitor.ui.main_window import MainWindow
    win = MainWindow(ctx)
    for _ in range(3):
        ctx.engine.step()
    QApplication.processEvents()
    res = win.search.provider.results("diametro")
    assert res[0].kind == "var" and "Diametro" in res[0].title and res[1].kind == "sub"
    win._plotted = [x for x in win._plotted if x != "diam"]
    res[0].run()
    assert win.current_page() == "trends" and "diam" in win._plotted
    spc = next(r for r in res if r.kind == "sub" and "SPC" in r.title)
    spc.run()
    assert win.current_page() == "spc" and "diam" in win.stats_panel.selected
    acts = win.search.provider.results("respaldo")
    assert any(r.kind == "action" and "respaldo" in r.title.lower() for r in acts)
    assert not any(r.title == "Salir" for r in win.search.provider.results("salir"))
    t = win.search.provider.results("hace 1 min")
    assert t[0].kind == "time"
    t[0].run()
    assert win.current_page() == "trends" and win.trends.marker is not None
    t[1].run()
    assert win.current_page() == "problems"
    # una receta pide confirmación antes de cambiarse
    other = ctx.recipes.names()[0]
    ctx.engine.set_recipe(None)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    next(r for r in win.search.provider.results(other) if r.kind == "recipe").run()
    assert ctx.engine.state.recipe is None
    # teclado: Enter abre el primer resultado y la búsqueda se recuerda
    win.search.setText("tendencias")
    win.search.refresh()
    win.search._activate()
    assert win.current_page() == "trends"
    assert any(r.key == "page:trends" for r in win.search.provider.results(""))
    win._detach()


def test_crew_in_top_bar_and_personnel_dialog(ctx):
    from extrusion_monitor.personnel import crew
    from extrusion_monitor.ui.main_window import MainWindow
    from extrusion_monitor.ui.personnel_dialog import PersonnelDialog
    home = ctx.workspace.home
    dlg = PersonnelDialog(home, ["Juan Pérez"])
    assert dlg.table.rowCount() == 1  # la lista anterior de la receta se ofrece al empezar
    dlg._new("supervisor")
    dlg.table.item(1, 0).setText("Ana Supervisora")
    dlg._new("operator")
    dlg.table.item(2, 0).setText("Rosa Operadora")
    dlg.table.item(2, 2).setText("1234")
    dlg.accept()
    win = MainWindow(ctx)
    users = [win.cmb_user.itemData(i) for i in range(win.cmb_user.count())]
    assert "Rosa Operadora" in users and "Ana Supervisora" in users  # un solo selector para ambos
    texts = [win.cmb_user.itemText(i) for i in range(win.cmb_user.count())]
    assert any("Ana Supervisora" in t and "Supervisor" in t.replace("Ana Supervisora", "") for t in texts)
    win.cmb_user.setCurrentIndex(win.cmb_user.findData("Rosa Operadora"))
    win._crew_chosen()
    assert crew(ctx.workspace.load_state())["user"] == "Rosa Operadora"
    cap = win.problems_page.capture
    assert cap.cmb_op.currentData() == "Rosa Operadora"  # la captura propone al operador en turno
    win._detach()


def test_home_status_cards_and_donut(ctx):
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.config import HomeSettings
    from extrusion_monitor.ui.main_window import MainWindow
    win = MainWindow(ctx)
    for _ in range(3):
        ctx.engine.step()
    ctx.engine.config.home = HomeSettings()
    assert any(t.kind == "downtime" for t in ctx.engine.config.home.tiles)
    win.home.rebuild()
    win.home.refresh_oee(force=True)
    win.home.update_snapshot(ctx.engine.last, force=True)
    QApplication.processEvents()
    st = win.home.status
    assert st["state"].value.text() not in ("", "—")
    assert st["alarms"].value.text().isdigit()
    assert win.home.donut is not None
    win.home.set_pending(2)
    assert st["pending"].value.text() == "2"
    ctx.engine.config.home.status_bar = False
    win.home.rebuild()
    assert not win.home.status.isVisibleTo(win.home)
    win._detach()


def test_shifts_by_time_and_password_hash(tmp_path):
    import datetime as dt

    from extrusion_monitor.personnel import (
        LoginSettings, Person, Personnel, Shift, check_password, hash_password, shift_key,
    )
    h = hash_password("1234")
    assert "1234" not in h and check_password("1234", h) and not check_password("4321", h)
    night = Shift("Noche", "22:00", "06:00")
    assert night.contains(dt.datetime(2026, 10, 20, 23, 0)) and night.contains(dt.datetime(2026, 10, 21, 5, 59))
    assert not night.contains(dt.datetime(2026, 10, 21, 6, 0))
    # la noche que empieza el 20 sigue siendo la misma vuelta de turno a las 03:00 del 21
    k1 = shift_key(night, dt.datetime(2026, 10, 20, 23, 0).timestamp())
    k2 = shift_key(night, dt.datetime(2026, 10, 21, 3, 0).timestamp())
    assert k1 == k2 == "Noche@2026-10-20"
    p = Personnel([Person("Luis", badge="100", shift="Mañana"), Person("Ana", "supervisor", "200", password=h),
                   Person("Sin turno", badge="300")],
                  [Shift("Mañana", "06:00", "14:00"), night], LoginSettings(True, "badge"))
    p.save(tmp_path)
    q = Personnel.load(tmp_path)
    assert q.login.auto_shift and q.login.confirm == "badge" and q.find("Ana").password == h
    assert q.current_shift(dt.datetime(2026, 10, 20, 7, 0).timestamp()).name == "Mañana"
    assert q.current_shift(dt.datetime(2026, 10, 20, 15, 0).timestamp()) is None
    assert q.shift_people(q.shifts[0]) == ["Luis", "Ana", "Sin turno"] and "Luis" not in q.shift_people(night)
    assert q.verify("Luis", "100") is None and q.verify("Luis", "999") is not None
    q.login.confirm = "badge_password"
    assert q.verify("Ana", "200", "1234") is None and q.verify("Ana", "200", "x") is not None
    assert q.verify("Luis", "100", "1234") is not None  # sin contraseña asignada


def test_shift_change_asks_who_enters_and_confirms_badge(ctx, monkeypatch):
    import datetime as dt

    from PySide6.QtWidgets import QApplication, QDialog

    from extrusion_monitor.personnel import LoginSettings, Person, Personnel, Shift, crew, hash_password
    from extrusion_monitor.ui.main_window import MainWindow
    home = ctx.workspace.home
    Personnel([Person("Luis", badge="100"), Person("Ana", "supervisor", "200", password=hash_password("clave1"))],
              [Shift("Todo el día", "00:00", "23:59")], LoginSettings(True, "badge")).save(home)
    win = MainWindow(ctx)
    win.check_shift()
    dlg = win._login_dlg
    assert dlg is not None and "Todo el día" in win.lbl_shift.text()
    dlg.ed_badge.setText("999")
    dlg.cmb.setCurrentIndex(dlg.cmb.findData("Luis"))
    dlg.accept()
    assert dlg.result() != QDialog.Accepted and "no corresponde" in dlg.lbl.text()
    dlg.ed_badge.setText("200")
    dlg._badge_typed("200")  # escribir el número elige a la persona
    assert dlg.name == "Ana"
    dlg.accept()
    QApplication.processEvents()
    c = crew(ctx.workspace.load_state())
    assert c["user"] == "Ana" and c["role"] == "supervisor" and c["shift_key"].startswith("Todo el día@")
    win.check_shift()
    assert win._login_dlg is None  # ese turno ya se confirmó
    # cambiar de usuario en la barra superior también pide la confirmación
    p = Personnel.load(home)
    p.login.confirm = "badge_password"
    p.save(home)
    win.cmb_user.setCurrentIndex(win.cmb_user.findData("Luis"))
    win._crew_chosen()
    assert win._login_dlg is not None and crew(ctx.workspace.load_state())["user"] == "Ana"
    win._login_dlg.reject()
    QApplication.processEvents()
    assert win.cmb_user.currentData() == "Ana"
    # «Más tarde» en el aviso de turno lo pospone
    s = ctx.workspace.load_state()
    s["crew"]["shift_key"] = ""
    ctx.workspace.save_state(s)
    win.check_shift()
    win._login_dlg.reject()
    QApplication.processEvents()
    win.check_shift()
    assert win._login_dlg is None and win._login_snooze > ctx.engine.clock()
    win._detach()


def test_personnel_dialog_shifts_and_passwords(ctx, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from extrusion_monitor.personnel import Personnel, check_password
    from extrusion_monitor.ui.personnel_dialog import C_SHIFT, PersonnelDialog
    home = ctx.workspace.home
    dlg = PersonnelDialog(home, [], shift_starts=["06:00", "14:00", "22:00"])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    dlg._shifts_from_oee()
    assert [(s.name, s.start, s.end) for s in dlg.shift_list()][2] == ("Turno 3", "22:00", "06:00")
    dlg._new("operator")
    dlg.table.item(0, 0).setText("Rosa")
    dlg.table.item(0, 2).setText("55")
    dlg._refresh_shift_combos()
    cmb = dlg.table.cellWidget(0, C_SHIFT)
    cmb.setCurrentIndex(cmb.findData("Turno 2"))
    dlg.set_password(0, "secreta")
    dlg.chk_auto.setChecked(True)
    dlg.rb["badge_password"].setChecked(True)
    assert dlg.problems(dlg.personnel()) == []
    dlg.accept()
    p = Personnel.load(home)
    rosa = p.find("Rosa")
    assert rosa.shift == "Turno 2" and rosa.badge == "55" and check_password("secreta", rosa.password)
    assert p.login.auto_shift and p.login.confirm == "badge_password" and len(p.shifts) == 3
