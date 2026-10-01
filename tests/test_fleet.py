"""Exportación al dashboard global y lectura de la carpeta compartida."""
import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from extrusion_monitor.fleet import FleetReader, LineState, StationSettings, line_slug  # noqa: E402


@pytest.fixture
def ctx(tmp_path):
    from extrusion_monitor.bootstrap import build
    c = build(tmp_path / "home", demo=True)
    c.engine.sleep = lambda s: None
    return c


def test_line_slug():
    assert line_slug("Línea 1 / Extrusora") == "Linea-1-Extrusora"
    assert line_slug("  ") == "linea"


def test_export_status_events_trend(ctx, tmp_path):
    shared = tmp_path / "planta"
    shared.mkdir()
    ex = ctx.exporter
    ex.reconfigure(StationSettings(enabled=True, export_dir=str(shared), line_name="Línea 1", trend_interval_s=10))
    assert json.loads((ctx.workspace.home / "station.json").read_text("utf-8"))["line_name"] == "Línea 1"
    for _ in range(25):
        ctx.engine.step()
    ex._acc_start -= 60  # ya pasó el minuto de tendencia
    ex.write_once()
    d = shared / "Linea-1"
    st = json.loads((d / "status.json").read_text("utf-8"))
    assert st["schema"] == 1 and st["line_name"] == "Línea 1" and st["recipe"]
    assert st["machine"]["state"] == "running" and st["oee"]["oee"] is not None
    diam = next(v for v in st["variables"] if v["id"] == "diam")
    assert diam["value"] == pytest.approx(3.2, abs=0.1) and diam["limits"][2] is not None
    assert list((d / "events").glob("*.jsonl")) and list((d / "trend").glob("*.jsonl"))
    assert not list(d.glob("*.tmp"))  # escritura atómica: sin temporales

    r = FleetReader(shared)
    events = r.scan()
    assert list(r.lines) == ["Linea-1"] and events
    line = r.lines["Linea-1"]
    assert line.connection(time.time()) == "online"
    t, mean, lo, hi = r.trend("Linea-1", "diam", time.time() - 3600)
    assert len(t) == 1 and lo[0] <= mean[0] <= hi[0]
    assert r.scan() == []  # sin eventos nuevos: no se vuelve a leer nada

    ex.stop(closed=True)
    r.scan()
    assert r.lines["Linea-1"].connection(time.time()) == "closed"


def test_export_survives_unavailable_folder(ctx, tmp_path):
    ex = ctx.exporter
    missing = tmp_path / "no_existe" / "x"
    blocker = tmp_path / "no_existe"
    blocker.write_text("un archivo donde debería ir la carpeta")  # la carpeta no se puede crear
    ex.reconfigure(StationSettings(enabled=True, export_dir=str(missing), line_id="L1"))
    for _ in range(10):
        ctx.engine.step()
    with pytest.raises(OSError):
        ex.write_once()
    pending = len(ex._events)
    assert pending > 0  # los eventos esperan en memoria
    blocker.unlink()
    ex.write_once()  # la red volvió: se escribe todo lo pendiente
    assert not ex._events and ex.last_error == ""
    rows = (missing / "L1" / "events").glob("*.jsonl")
    assert sum(len(f.read_text("utf-8").splitlines()) for f in rows) >= pending


def test_exporter_thread_does_not_block_monitoring(ctx, tmp_path, monkeypatch):
    from extrusion_monitor import exporter

    ex = ctx.exporter
    ex.reconfigure(StationSettings(enabled=True, export_dir=str(tmp_path), line_id="L1", interval_s=1))
    calls = []
    monkeypatch.setattr(exporter, "write_atomic", lambda *a, **k: (calls.append(1), time.sleep(3)))  # red lenta
    ex.start()
    time.sleep(0.3)
    assert calls  # el hilo de exportación está atorado escribiendo…
    t0 = time.perf_counter()
    for _ in range(5):
        ctx.engine.step()
    assert time.perf_counter() - t0 < 2.5  # …y el monitoreo no lo espera
    ex._stop.set()
    ex._wake.set()


def test_connection_states():
    now = time.time()
    ln = LineState("a", None, status={"ts": now - 3, "interval_s": 5})
    assert ln.connection(now) == "online"
    ln.status["ts"] = now - 20
    assert ln.connection(now) == "stale"
    ln.status["ts"] = now - 120
    assert ln.connection(now) == "offline"
    assert LineState("b", None).connection(now) == "offline"


def test_reader_incremental_events(tmp_path):
    from extrusion_monitor.fleet import day_name
    d = tmp_path / "L1"
    (d / "events").mkdir(parents=True)
    (d / "status.json").write_text(json.dumps({"ts": time.time(), "line_name": "Uno"}), encoding="utf-8")
    ev = d / "events" / day_name(time.time())
    ev.write_text('{"ts": 1, "msg": "a"}\n{"ts": 2, "msg": "b"}\n{"ts": 3, "msg": "inco', encoding="utf-8")
    r = FleetReader(tmp_path)
    assert [e["msg"] for e in r.scan()] == ["a", "b"]  # el renglón incompleto espera
    with open(ev, "a", encoding="utf-8") as f:
        f.write('mpleto"}\n')
    assert [e["msg"] for e in r.scan()] == ["incompleto"]
    assert r.lines["L1"].name == "Uno"


def test_fleet_window(ctx, tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.ui.fleet_window import FleetWindow
    QApplication.instance() or QApplication([])
    shared = tmp_path / "planta"
    shared.mkdir()
    ex = ctx.exporter
    for name in ("Línea A", "Línea B"):
        ex.reconfigure(StationSettings(enabled=True, export_dir=str(shared), line_name=name))
        for _ in range(5):
            ctx.engine.step()
        ex.write_once()
    w = FleetWindow(str(shared), tmp_path / "fleet.json")
    w.refresh()
    assert set(w.cards) == {"Linea-A", "Linea-B"}
    assert w.tiles["lines"].val.text().count("2")
    w.select("Linea-A")
    assert w.detail.tbl.rowCount() == len(ctx.config.variables)
    w.ed_search.setText("B")
    assert w._order == ["Linea-B"]
    w.set_folder(str(tmp_path / "otra"))
    assert not w.cards and json.loads((tmp_path / "fleet.json").read_text("utf-8"))["dir"].endswith("otra")
    w.close()
