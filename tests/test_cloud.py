"""Envío al servidor propio: cola en disco, reintentos sin duplicar y estado actual."""
import gzip
import json
import os


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from extrusion_monitor.cloud import CloudOutbox, ServerError  # noqa: E402
from extrusion_monitor.fleet import StationSettings  # noqa: E402

S = StationSettings(server_enabled=True, server_url="https://srv", server_token="ln_x", server_interval_s=2,
                    server_heartbeat_s=30)


class FakeServer:
    def __init__(self):
        self.calls = []
        self.down = False
        self.seen = set()

    def __call__(self, base, path, method="GET", body=None, token="", verify=True, timeout=15, headers=None):
        if self.down:
            raise ServerError("sin conexión con el servidor (prueba)")
        self.calls.append((path, body))
        if body and body.get("batch_id"):
            dup = body["batch_id"] in self.seen
            self.seen.add(body["batch_id"])
            return {"ok": True, "duplicate": dup}
        return {"ok": True}


def test_queue_survives_outage_and_sends_in_order(tmp_path):
    t = [1000.0]
    srv = FakeServer()
    box = CloudOutbox(tmp_path, lambda: S, sender=srv, clock=lambda: t[0])
    srv.down = True
    box.enqueue([{"ts": 1, "msg": "a"}], [{"ts": 1, "v": {}}])
    box.enqueue([{"ts": 2, "msg": "b"}], [])
    box.set_status({"ts": 2, "overall": "OK"})
    assert not box.flush() and "sin conexión" in box.last_error
    assert len(box.pending()) == 2  # nada se perdió
    # reinicio del programa: una cola nueva lee los mismos archivos
    box2 = CloudOutbox(tmp_path, lambda: S, sender=srv, clock=lambda: t[0])
    box2.set_status({"ts": 3, "overall": "WARN"})
    srv.down = False
    assert box2.flush()
    sent = [b for p, b in srv.calls if b.get("batch_id")]
    assert [e["msg"] for b in sent for e in b["events"]] == ["a", "b"]
    assert sent[-1]["status"]["overall"] == "WARN"  # el estado viaja con el último lote
    assert box2.pending() == [] and box2.last_error == ""


def test_resend_after_lost_answer_keeps_batch_id(tmp_path):
    srv = FakeServer()
    box = CloudOutbox(tmp_path, lambda: S, sender=srv)
    box.enqueue([{"ts": 1, "msg": "a"}], [])
    p = box.pending()[0]
    bid = json.loads(gzip.decompress(p.read_bytes()))["batch_id"]
    srv(  "x", "/api/v1/ingest", "POST", {"batch_id": bid})  # el servidor ya lo había recibido
    assert box.flush() and srv.calls[-1][1]["batch_id"] == bid  # se reenvía con el mismo id: el servidor lo ignora


def test_status_heartbeat_and_disabled(tmp_path):
    t = [1000.0]
    srv = FakeServer()
    box = CloudOutbox(tmp_path, lambda: S, sender=srv, clock=lambda: t[0])
    box.set_status({"ts": 1})
    box.flush()
    n = len(srv.calls)
    t[0] += 5
    box.flush()  # sin cambios y antes del latido: no envía
    assert len(srv.calls) == n
    t[0] += 40
    box.flush()  # latido
    assert len(srv.calls) == n + 1
    off = CloudOutbox(tmp_path / "x", lambda: StationSettings(), sender=srv)
    off.set_status({"ts": 1})
    assert not off.flush() and len(srv.calls) == n + 1


def test_exporter_sends_events_status_and_problems(tmp_path):
    from extrusion_monitor.bootstrap import build
    ctx = build(tmp_path / "data", demo=True)
    srv = FakeServer()
    ex = ctx.exporter
    ex.cloud.sender = srv
    ex.reconfigure(S.model_copy(update={"line_id": "L01"}))
    for _ in range(3):
        ctx.engine.step()
    ex.queue_problem("add", {"uid": "u1", "kind": "downtime", "start": 1, "end": 2})
    ex.write_once()
    assert ex.cloud.pending()  # primero a disco
    assert ex.cloud.flush(force_status=True)
    bodies = [b for _, b in srv.calls]
    assert any(b.get("events") for b in bodies)
    assert any(p["uid"] == "u1" for b in bodies for p in b.get("problems", []))
    st = next(b["status"] for b in bodies if b.get("status"))
    assert st["line_id"] == "L01" and st["variables"]
    assert not (tmp_path / "data" / "L01").exists()  # sin carpeta compartida configurada no se escribe ahí
