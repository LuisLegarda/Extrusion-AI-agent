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


def _status(tmp, lid, **kw):
    d = tmp / lid
    d.mkdir(parents=True, exist_ok=True)
    st = {"ts": time.time(), "interval_s": 5, "line_name": kw.pop("name", lid), "monitoring": True,
          "variables": [{"id": "diam", "name": "Diámetro", "unit": "mm", "kind": "actual", "value": 3.2,
                         "limits": [3.17, 3.23, 3.15, 3.25], "level": "OK", "fresh": True}],
          "kpis": {"oee": 80.0}, "machine": {"state": "running", "since": time.time() - 60}}
    st.update(kw)
    (d / "status.json").write_text(json.dumps(st), encoding="utf-8")
    return d


def test_fleet_settings_template_overrides_and_areas(tmp_path):
    from extrusion_monitor.fleet import FleetTile, load_fleet_settings, save_fleet_settings
    from extrusion_monitor.fleet import FleetSettings
    own = [FleetTile(id="x", kind="var", var="diam", chart="trend")]
    s = FleetSettings(dir="x", overrides={"L2": own}, areas={"L1": "Nave A"})
    p = tmp_path / "fleet.json"
    save_fleet_settings(p, s)
    s2 = load_fleet_settings(p)
    assert [t.id for t in s2.tiles_for("L1")] == [t.id for t in s.tiles] and s2.tiles_for("L2")[0].var == "diam"
    assert s2.area_of(LineState("L1", None, status={"area": "Nave B"})) == "Nave A"  # la del dashboard manda
    assert s2.area_of(LineState("L3", None, status={"area": "Nave B"})) == "Nave B"
    with pytest.raises(ValueError):
        FleetSettings(tiles=[FleetTile(id=str(i)) for i in range(6)])  # máximo 5 por línea


def test_trend_series_incremental(tmp_path):
    from extrusion_monitor.fleet import day_name
    d = _status(tmp_path, "L1")
    (d / "trend").mkdir()
    f = d / "trend" / day_name(time.time())
    now = time.time()
    f.write_text("".join(json.dumps({"ts": now - 600 + i * 60, "v": {"diam": [3.2 + i / 100, 0, 0, 0]},
                                     "k": {"oee": 70 + i}}) + "\n" for i in range(5)), encoding="utf-8")
    r = FleetReader(tmp_path)
    r.scan()
    line = r.lines["L1"]
    keys = {("v", "diam"), ("k", "oee")}
    r.update_series(line, keys, now - 3600)
    assert line.series[("k", "oee")][1] == [70, 71, 72, 73, 74]
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": now, "v": {"diam": [3.3, 0, 0, 0]}, "k": {"oee": 90}}) + "\n")
    r.update_series(line, keys, now - 3600)
    assert line.series[("k", "oee")][1][-1] == 90 and len(line.series[("v", "diam")][0]) == 6  # solo lo nuevo
    r.update_series(line, keys, now - 500)  # el periodo avanza: se descarta lo viejo
    assert line.series[("k", "oee")][1] == [72, 73, 74, 90]


def test_fleet_cards_notify_and_export(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.fleet import FleetSettings, FleetTile, save_fleet_settings
    from extrusion_monitor.ui.fleet_window import FleetWindow
    QApplication.instance() or QApplication([])
    shared = tmp_path / "planta"
    _status(shared, "L1", name="Línea 1", area="Nave A")
    _status(shared, "L2", name="Línea 2", area="Nave B")
    tiles = [FleetTile(id="g", kind="kpi", kpi="oee", chart="gauge"),
             FleetTile(id="t", kind="var", var="Diámetro", chart="trend", width=2),  # por nombre
             FleetTile(id="v", kind="var", var="no_existe", chart="value")]
    own = [FleetTile(id="p", kind="production", chart="value")]
    cfg = tmp_path / "fleet.json"
    save_fleet_settings(cfg, FleetSettings(dir=str(shared), tiles=tiles, overrides={"L2": own}))
    beeps = []
    monkeypatch.setattr(QApplication, "beep", lambda: beeps.append(1))
    w = FleetWindow(None, cfg)
    w.refresh()
    assert len(w.cards["L1"].tiles) == 3 and len(w.cards["L2"].tiles) == 1
    assert "80" in str(w.cards["L1"].tiles[0].body.value)
    assert "No existe" in w.cards["L1"].tiles[2].lbl.text()
    assert [h[1] for h in w._headers] == ["Nave A", "Nave B"]
    # la línea 1 entra en alarma: parpadeo, sonido y evento de planta
    _status(shared, "L1", name="Línea 1", area="Nave A", n_alarms=1,
            alarms=[{"since": time.time(), "level": "ALARM", "msg": "Diámetro fuera de alarma"}])
    time.sleep(0.02)
    w.refresh()
    assert w.cards["L1"].blinking and beeps and "entró en alarma" in w.lst_plant.item(0).text()
    w.select("L1")
    assert not w.cards["L1"].blinking  # clic = reconocido
    out = w.export_csv(str(tmp_path / "x.csv"))
    rows = open(out, encoding="utf-8-sig").read().splitlines()
    assert len(rows) == 3 and rows[1].startswith("Línea 1;L1;Nave A")
    w.toggle_tv()
    assert w.tv and not w.top.isVisible()
    w.toggle_tv()
    w.close()


def test_fleet_setup_dialog(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox

    from extrusion_monitor.fleet import FleetSettings
    from extrusion_monitor.ui.fleet_setup import FleetSetupDialog
    QApplication.instance() or QApplication([])
    _status(tmp_path, "L1")
    r = FleetReader(tmp_path)
    r.scan()
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dlg = FleetSetupDialog(FleetSettings(dir=str(tmp_path)), r.lines)
    ed = dlg.template
    for _ in range(4):
        ed._add()
    assert len(ed.tiles) == 5  # 3 por defecto + 2: el máximo es 5
    ed.lst.setCurrentRow(4)
    ed.cmb_kind.setCurrentIndex(ed.cmb_kind.findData("var"))
    ed.cmb_var.setCurrentIndex(ed.cmb_var.findData("diam"))
    ed.cmb_chart.setCurrentIndex(ed.cmb_chart.findData("bar"))
    assert ed.tiles[4].kind == "var" and ed.tiles[4].var == "diam" and ed.tiles[4].chart == "bar"
    dlg.lst_lines.setCurrentRow(0)
    dlg.ed_area.setText("Nave 9")
    dlg.chk_own.setChecked(True)
    dlg._own_editors["L1"].tiles = dlg._own_editors["L1"].tiles[:1]
    s = dlg.result_settings()
    assert len(s.tiles) == 5 and len(s.overrides["L1"]) == 1 and s.areas["L1"] == "Nave 9"
