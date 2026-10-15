"""De punta a punta: la cola del monitor (extrusion_monitor.cloud) contra la API real del servidor."""
import gzip
import json
import os
import sys
import time
from pathlib import Path

os.environ["EXTRUSION_NO_PURGE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # código del monitor

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import insert  # noqa: E402

from extrusion_monitor.cloud import CloudOutbox, ServerError  # noqa: E402
from extrusion_monitor.fleet import StationSettings  # noqa: E402
from extrusion_server.app import Settings, create_app, hash_token  # noqa: E402
from extrusion_server.db import api_keys, make_engine  # noqa: E402


def _sender(client):
    """Misma firma que cloud.request, pero contra el TestClient."""
    def send(base, path, method="GET", body=None, token="", verify=True, timeout=15, headers=None):
        h = dict(headers or {})
        if token:
            h["Authorization"] = f"Bearer {token}"
        if body is not None:
            h.update({"Content-Type": "application/json", "Content-Encoding": "gzip"})
            r = client.request(method, path, content=gzip.compress(json.dumps(body).encode()), headers=h)
        else:
            r = client.request(method, path, headers=h)
        if r.status_code >= 400:
            raise ServerError(r.json().get("detail", f"HTTP {r.status_code}"), r.status_code)
        return r.json()
    return send


def test_monitor_queue_to_server(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    client = TestClient(create_app(Settings(enroll_key="k"), engine=eng))
    with eng.begin() as c:
        c.execute(insert(api_keys).values(name="v", role="viewer", token_hash=hash_token("vw"), created=0,
                                          revoked=False))
    send = _sender(client)
    token = send("", "/api/v1/register", "POST", {"line_id": "L07", "line_name": "Línea 7", "area": "B"},
                 headers={"X-Enroll-Key": "k"})["token"]
    st = StationSettings(server_enabled=True, server_url="http://srv", server_token=token)
    box = CloudOutbox(tmp_path / "hmi", lambda: st, sender=send)
    now = time.time()
    box.enqueue([{"ts": now, "kind": "raised", "level": "ALARM", "msg": "Zona 3 alta"}],
                [{"ts": now, "from": now - 60, "v": {"z3": [190, 188, 192, 191]}, "k": {"oee": 77.0}}],
                [{"op": "add", "uid": "p1", "kind": "downtime", "start": now - 300, "end": now, "reason": "Atasco"}])
    box.set_status({"ts": now, "line_id": "L07", "line_name": "Línea 7", "overall": "ALARM", "n_alarms": 1})
    assert box.flush(), box.last_error
    # un reintento del mismo lote (respuesta perdida) no duplica
    batch_file = tmp_path / "hmi" / "copia.json"
    V = {"Authorization": "Bearer vw"}
    lines = client.get("/api/v1/lines", headers=V).json()["lines"]
    assert lines[0]["line_id"] == "L07" and lines[0]["overall"] == "ALARM" and lines[0]["online"]
    assert client.get("/api/v1/lines/L07/events", headers=V).json()["events"][0]["msg"] == "Zona 3 alta"
    assert client.get("/api/v1/lines/L07/trend", headers=V).json()["trend"][0]["k"]["oee"] == 77.0
    assert client.get("/api/v1/lines/L07/problems", headers=V).json()["problems"][0]["reason"] == "Atasco"
    assert not batch_file.exists()
    # clave revocada: el monitor conserva los datos en su cola
    bad = StationSettings(server_enabled=True, server_url="http://srv", server_token="ln_mala")
    box_bad = CloudOutbox(tmp_path / "hmi2", lambda: bad, sender=send)
    box_bad.enqueue([{"ts": now, "msg": "x"}], [])
    assert not box_bad.flush() and "no válida" in box_bad.last_error and box_bad.pending()
