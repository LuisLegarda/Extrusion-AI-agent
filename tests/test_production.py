"""Preparación para producción: purga del historial, respaldos, configuración dañada y registro de errores."""
import json
import logging
import os
import threading
import time
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_purge_by_blocks_and_history_uses_the_index(tmp_path):
    from extrusion_monitor.storage import Historian
    h = Historian(tmp_path / "h.sqlite")
    now = time.time()
    t0 = now - 10 * 3600
    rows = [(t0 + 10 * i, f"v{k}", float(i), None) for i in range(3600) for k in range(3)]
    h.write_samples(rows)
    h.write_events([(t0, "x", 1, "R", "v0", "viejo", None), (now, "x", 1, "R", "v0", "nuevo", None)])
    h.PURGE_CHUNK = 500  # varios bloques
    cutoff = t0 + 5 * 3600
    n = h.purge(cutoff)
    assert n == 1800 * 3
    left = h._conn.execute("SELECT MIN(ts), COUNT(*) FROM samples").fetchone()
    assert left[0] >= cutoff and left[1] == 1800 * 3
    assert [e[5] for e in h.events_between(0, now + 1)] == ["nuevo"]
    assert h.purge(cutoff) == 0  # nada más que borrar
    # el historial completo consulta variable por variable (índice var, ts) y omite las que no tienen datos
    assert h.variables() == ["v0", "v1", "v2"]
    header, out = h.history_table(now - 3600, now, headers={"v1": "Velocidad"})
    assert header == ["fecha_hora", "v0", "Velocidad", "v2"] and len(out) == 360
    header, out = h.history_table(now - 3600, now, variables=["v2", "nada"])
    assert header == ["fecha_hora", "v2"]
    plan = h._conn.execute("EXPLAIN QUERY PLAN SELECT ts FROM samples WHERE var=? AND ts BETWEEN ? AND ?",
                           ("v0", 0, 1)).fetchall()
    assert "ix_samples_var_ts" in str(plan)


def test_purge_does_not_block_monitoring_writes(tmp_path):
    from extrusion_monitor.storage import Historian
    h = Historian(tmp_path / "h.sqlite")
    t0 = time.time() - 86400
    h.write_samples([(t0 + i * 0.1, "v", 1.0, None) for i in range(200_000)])
    h.PURGE_CHUNK = 5000
    worst = []

    def writer():
        for _ in range(40):
            a = time.perf_counter()
            h.write_samples([(time.time(), "w", 1.0, None)])
            worst.append(time.perf_counter() - a)
            time.sleep(0.002)

    th = threading.Thread(target=writer)
    th.start()
    h.purge(t0 + 20_000)
    th.join()
    assert max(worst) < 0.5  # nunca espera toda la purga


def _make_home(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUMON_BACKUPS", str(tmp_path / "resp"))
    home = tmp_path / "datos"
    home.mkdir()
    from extrusion_monitor.config import AppConfig, Workspace
    ws = Workspace(home)
    ws.save_config(AppConfig())
    return home, ws


def test_restore_is_applied_when_the_program_opens_again(tmp_path, monkeypatch):
    from extrusion_monitor import backup
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.config import AppConfig
    home, ws = _make_home(tmp_path, monkeypatch)
    cfg = AppConfig()
    cfg.machine_name = "Antes"
    ws.save_config(cfg)
    z = backup.create_backup(home, "manual")
    cfg.machine_name = "Después"
    ws.save_config(cfg)
    with pytest.raises(ValueError):
        bad = tmp_path / "otro.zip"
        with zipfile.ZipFile(bad, "w") as zz:
            zz.writestr("cualquier/cosa.txt", "x")
        backup.schedule_restore(bad, home)
    backup.schedule_restore(z, home)
    assert ws.load_config().machine_name == "Después"  # todavía no: se aplica al abrir
    ctx = build(home)
    assert ctx.config.machine_name == "Antes" and not (home / backup.PENDING).exists()
    assert any("antes-de-restaurar" in p.name for p in backup.list_backups(home))  # lo de antes quedó respaldado
    ctx.engine.historian.close()


def test_damaged_config_is_recovered_from_the_latest_valid_backup(tmp_path, monkeypatch):
    from extrusion_monitor import backup
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.config import AppConfig
    home, ws = _make_home(tmp_path, monkeypatch)
    cfg = AppConfig()
    cfg.machine_name = "Línea 4"
    ws.save_config(cfg)
    backup.create_backup(home, "semanal")
    (home / "config.json").write_text("", encoding="utf-8")  # apagón a mitad de guardar
    ctx = build(home)
    assert ctx.config.machine_name == "Línea 4" and ctx.recovered and ctx.recovered.endswith(".zip")
    assert list(home.glob("config.dañado-*.json"))
    ctx.engine.historian.close()


def test_damaged_config_without_backup_is_reported(tmp_path, monkeypatch):
    from extrusion_monitor.bootstrap import build
    home, _ws = _make_home(tmp_path, monkeypatch)
    (home / "config.json").write_text("{roto", encoding="utf-8")
    with pytest.raises(ValueError):
        build(home)


def test_restore_menu_closes_and_schedules(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from extrusion_monitor import backup
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.ui.main_window import MainWindow
    home, _ws = _make_home(tmp_path, monkeypatch)
    z = backup.create_backup(home, "manual")
    ctx = build(home)
    win = MainWindow(ctx)
    win.gate.offer = lambda r: False
    win.show()
    assert win._restore_backup(str(z), confirm=False)
    assert json.loads((home / backup.PENDING).read_text("utf-8"))["zip"] == str(z)
    assert not win.isVisible()


def test_logging_rotates_and_records_uncaught_errors(tmp_path):
    import sys

    from extrusion_monitor import logsetup
    old_hook, old_thread_hook = sys.excepthook, threading.excepthook
    root = logging.getLogger()
    try:
        path = logsetup.setup_logging(tmp_path, "app")
        logsetup.setup_logging(tmp_path, "app")  # de nuevo: no duplica el manejador
        handlers = [h for h in root.handlers if getattr(h, "_extrumon", False)]
        assert len(handlers) == 1 and handlers[0].maxBytes == logsetup.MAX_BYTES
        try:
            raise RuntimeError("falla en un botón")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
        th = threading.Thread(target=lambda: 1 / 0, name="lector")
        th.start()
        th.join()
        handlers[0].flush()
        text = path.read_text("utf-8")
        assert "falla en un botón" in text and "Error no atrapado en el hilo «lector»" in text
        assert "ZeroDivisionError" in text and (tmp_path / "app-fallo.log").exists()
    finally:
        sys.excepthook, threading.excepthook = old_hook, old_thread_hook
        for h in [h for h in root.handlers if getattr(h, "_extrumon", False)]:
            root.removeHandler(h)
            h.close()


def test_secrets_never_fall_back_to_readable_text_on_windows(monkeypatch):
    from extrusion_monitor import secrets_store as ss
    monkeypatch.setattr(ss.sys, "platform", "win32")

    def broken(data, protect):
        raise OSError("DPAPI")

    monkeypatch.setattr(ss, "_dpapi", broken)
    with pytest.raises(ss.SecretError):
        ss.protect("clave-secreta")
    monkeypatch.setattr(ss, "_dpapi", lambda data, protect: data[::-1])
    enc = ss.protect("clave")
    assert enc.startswith("dpapi:") and "clave" not in enc and ss.unprotect(enc) == "clave"
