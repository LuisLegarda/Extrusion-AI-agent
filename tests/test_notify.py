"""Notificaciones: configuración (secretos cifrados), reglas, tiempo de espera y canales (simulados)."""
import json
import os
import time
from types import SimpleNamespace as NS

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def make(tmp_path, rules=("alarm", "read_error", "stop", "scrap", "supervisor", "monitor", "low_cpk", "control",
                          "report"), **thresholds):
    from extrusion_monitor.notify import Notifier, NotifySettings
    s = NotifySettings()
    s.webhook.enabled = True
    s.set_secret("webhook", "https://example.invalid/hook")
    for k, r in s.rules.items():
        r.enabled = k in rules
    for k, v in thresholds.items():
        s.rules[k].threshold = v
    s.save(tmp_path)
    out = []
    clock = [1000.0]
    n = Notifier(tmp_path, None, clock=lambda: clock[0], where=lambda: "Línea 3", who=lambda: "Ana",
                 senders={"webhook": lambda st, m: out.append(m), "email": lambda st, m: out.append(m),
                          "telegram": lambda st, m: out.append(m)})
    return n, out, clock


def snap(ts, findings=(), events=(), statuses=None, error=""):
    return NS(ts=ts, findings=list(findings), events=list(events), statuses=statuses or {}, error=error)


def finding(rule, var, level, msg, since):
    return NS(rule=rule, var_id=var, level=level, message=msg, since=since)


def test_settings_keep_secrets_encrypted(tmp_path):
    from extrusion_monitor.notify import NotifySettings
    s = NotifySettings()
    s.email.enabled, s.email.host, s.email.to = True, "smtp.example.com", ["a@b.c"]
    s.set_secret("email", "MiClaveSecreta")
    s.save(tmp_path)
    raw = (tmp_path / "notificaciones.json").read_text("utf-8")
    assert "MiClaveSecreta" not in raw
    s2 = NotifySettings.load(tmp_path)
    assert s2.secret("email") == "MiClaveSecreta" and s2.channels() == ["email"]
    (tmp_path / "notificaciones.json").write_text("{malo", "utf-8")
    assert NotifySettings.load(tmp_path).channels() == []


def test_alarm_findings_cooldown_and_read_threshold(tmp_path):
    n, out, clock = make(tmp_path, read_error=60)
    f = finding("TOLERANCIA", "diam", 3, "«Diámetro» fuera de límites (máx 3.25)", 1000)
    n.on_snapshot(snap(1000, [f]))
    n.flush()
    assert len(out) == 1 and "ALARMA" in out[0].subject and "Línea 3" in out[0].subject and "Ana" in out[0].body
    n.on_snapshot(snap(1001, [f]))  # sigue activa: no se repite
    n.on_snapshot(snap(1002, []))  # se normaliza
    clock[0] = 1003
    n.on_snapshot(snap(1003, [f]))  # vuelve antes del tiempo de espera: no se repite
    n.flush()
    assert len(out) == 1
    clock[0] = 1000 + 16 * 60
    n.on_snapshot(snap(clock[0], []))
    n.on_snapshot(snap(clock[0], [f]))
    n.flush()
    assert len(out) == 2
    r = finding("LECTURA", "vel", 2, "No se puede leer «Velocidad»", clock[0])
    n.on_snapshot(snap(clock[0] + 30, [r]))  # aún no pasan 60 s
    n.flush()
    assert len(out) == 2
    n.on_snapshot(snap(clock[0] + 61, [r]))
    n.flush()
    assert len(out) == 3 and "leer" in out[-1].subject
    w = finding("TOLERANCIA", "exc", 2, "aviso", clock[0])  # «warn» no se eligió
    n.on_snapshot(snap(clock[0] + 62, [w]))
    n.flush()
    assert len(out) == 3


def test_stop_resume_scrap_supervisor_monitor_and_quiet(tmp_path):
    n, out, clock = make(tmp_path, stop=5, scrap=50)
    var = NS(measured=True)
    cfg = NS(oee=NS(enabled=True, speed_var="vel", stop_threshold=1.0, shift_starts=["06:00", "18:00"]),
             var_label=lambda v: "Velocidad")
    n.engine = NS(config=cfg, historian=None, state=NS(recipe="R1"))

    def speed(v, ts):
        st = NS(reading=NS(value=v), fresh=True, var=var, trend=None)
        return snap(ts, statuses={"vel": st})
    t0 = 10_000.0
    n.on_snapshot(speed(0.0, t0))
    n.on_snapshot(speed(0.0, t0 + 4 * 60))
    n.flush()
    assert not out
    n.on_snapshot(speed(0.0, t0 + 6 * 60))
    n.flush()
    assert len(out) == 1 and "detenida" in out[0].subject and "R1" in out[0].body
    n.on_snapshot(speed(350.0, t0 + 9 * 60))
    n.flush()
    assert len(out) == 2 and "marcha" in out[1].subject
    n.problem_saved({"id": 1, "kind": "quality", "scrap": 80, "unit": "m", "category": "Superficie",
                     "reason": "Burbuja", "operator": "Ana"})
    n.problem_saved({"id": 2, "kind": "quality", "scrap": 10, "unit": "m"})
    n.supervisor_login("Luis")
    n.monitor_stopped()
    n.flush()
    subjects = [m.subject for m in out]
    assert any("Desperdicio alto: 80 m" in s for s in subjects) and not any("10 m" in s for s in subjects)
    assert any("Luis" in s for s in subjects) and any("Monitoreo detenido" in s for s in subjects)
    n.settings.quiet = True
    n.monitor_stopped(closing=True)
    n.flush()
    assert not any("cerrado" in m.subject for m in out)


def test_channels_payloads_and_test_button(tmp_path, monkeypatch):
    from extrusion_monitor import notify
    from extrusion_monitor.notify import Message, NotifySettings
    posts = []
    monkeypatch.setattr(notify, "_post", lambda url, data, ct, timeout=20: posts.append((url, data, ct)))
    s = NotifySettings()
    s.telegram.enabled, s.telegram.chat_ids = True, ["123", "456"]
    s.set_secret("telegram", "TOKEN")
    s.webhook.enabled, s.webhook.kind = True, "teams"
    s.set_secret("webhook", "https://hook")
    notify.send_telegram(s, Message("alarm", "Asunto", "Cuerpo"))
    notify.send_webhook(s, Message("alarm", "Asunto", "Cuerpo"))
    assert [p[0] for p in posts[:2]] == ["https://api.telegram.org/botTOKEN/sendMessage"] * 2
    assert json.loads(posts[0][1])["chat_id"] == "123" and posts[2][0] == "https://hook"
    assert "Asunto" in json.loads(posts[2][1])["text"]
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1.4 prueba")
    posts.clear()
    notify.send_telegram(s, Message("report", "Reporte", "adjunto", attachment=pdf))
    assert posts[0][0].endswith("/sendDocument") and b"%PDF-1.4 prueba" in posts[0][1]
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=0):
            sent.append(("connect", host, port))

        def starttls(self, context=None):
            sent.append("tls")

        def login(self, u, p):
            sent.append(("login", u, p))

        def send_message(self, m):
            sent.append(("send", m["To"], m["Subject"], [p.get_filename() for p in m.iter_attachments()]))

        def quit(self):
            pass
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    s.email.enabled, s.email.host, s.email.user, s.email.to = True, "smtp.x", "yo@x", ["a@x", "b@x"]
    s.set_secret("email", "pw")
    notify.send_email(s, Message("report", "Reporte", "adjunto", attachment=pdf))
    assert ("login", "yo@x", "pw") in sent and sent[-1][1] == "a@x, b@x" and sent[-1][3] == ["r.pdf"]


def test_notify_dialog_saves_rules_and_secrets(tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from extrusion_monitor.notify import Notifier, NotifySettings
    from extrusion_monitor.ui.notify_dialog import KEEP, NotifyDialog
    got = []
    n = Notifier(tmp_path, None, senders={"email": lambda s, m: got.append(m)})
    dlg = NotifyDialog(n)
    dlg.g_email.setChecked(True)
    dlg.ed_host.setText("smtp.office365.com")
    dlg.ed_user.setText("monitor@planta.com")
    dlg.ed_pw.setText("Secreta1")
    dlg.ed_to.setText("jefe@planta.com; calidad@planta.com")
    for r in range(dlg.tbl.rowCount()):
        it = dlg.tbl.item(r, 0)
        if it.data(Qt.UserRole) == "low_cpk":
            it.setCheckState(Qt.Checked)
    dlg.spins["low_cpk"].setValue(1.33)
    dlg.send_test()
    assert got and "Prueba" in got[0].subject and "✔" in dlg.lbl_test.text()
    dlg.accept()
    s = NotifySettings.load(tmp_path)
    assert s.email.to == ["jefe@planta.com", "calidad@planta.com"] and s.secret("email") == "Secreta1"
    assert s.on("low_cpk") and s.th("low_cpk") == pytest.approx(1.33)
    dlg2 = NotifyDialog(n)
    assert dlg2.ed_pw.text() == KEEP  # no se muestra la contraseña guardada
    dlg2.accept()
    assert NotifySettings.load(tmp_path).secret("email") == "Secreta1"  # se conserva si no se cambia


def test_main_window_registers_one_notifier_and_logs_crew(tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.ui.main_window import MainWindow
    ctx = build(tmp_path, demo=True)
    win = MainWindow(ctx)
    assert ctx.notifier is win.notifier and ctx.engine.listeners.count(ctx.notifier.on_snapshot) == 1
    win2 = MainWindow(ctx)
    assert win2.notifier is ctx.notifier and ctx.engine.listeners.count(ctx.notifier.on_snapshot) == 1
    win2._detach()
    win._detach()
