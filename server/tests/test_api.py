"""API del servidor con SQLite en memoria de archivo temporal."""
import gzip
import json
import os
import time

import pytest

os.environ["EXTRUSION_NO_PURGE"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import insert  # noqa: E402

from extrusion_server.app import Settings, create_app, hash_token  # noqa: E402
from extrusion_server.db import api_keys, make_engine, purge  # noqa: E402


@pytest.fixture
def srv(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL")
    eng = make_engine(url or f"sqlite:///{tmp_path / 'db.sqlite'}")
    if url:  # PostgreSQL de CI: se empieza con tablas vacías
        from extrusion_server.db import metadata
        metadata.drop_all(eng)
        metadata.create_all(eng)
    app = create_app(Settings(database_url="", enroll_key="registro-secreto"), engine=eng)
    with eng.begin() as c:
        c.execute(insert(api_keys).values(name="ing", role="viewer", token_hash=hash_token("vw_x"),
                                          created=time.time(), revoked=False))
        c.execute(insert(api_keys).values(name="adm", role="admin", token_hash=hash_token("ad_x"),
                                          created=time.time(), revoked=False))
    return TestClient(app), eng


def _register(client, line_id="L01"):
    r = client.post("/api/v1/register", json={"line_id": line_id, "line_name": "Línea 1", "area": "Nave A"},
                    headers={"X-Enroll-Key": "registro-secreto"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


V = {"Authorization": "Bearer vw_x"}


def test_health_and_registration(srv):
    client, _ = srv
    assert client.get("/api/v1/health").json()["ok"]
    bad = client.post("/api/v1/register", json={"line_id": "L01"}, headers={"X-Enroll-Key": "otra"})
    assert bad.status_code == 401
    h = _register(client)
    assert client.get("/api/v1/me", headers=h).json()["line_id"] == "L01"
    again = client.post("/api/v1/register", json={"line_id": "L01"}, headers={"X-Enroll-Key": "registro-secreto"})
    assert again.status_code == 409  # nadie puede quedarse con la clave de una línea existente
    assert client.post("/api/v1/register", json={"line_id": "L 01/../x"},
                       headers={"X-Enroll-Key": "registro-secreto"}).status_code == 422


def test_ingest_gzip_and_read_back(srv):
    client, _ = srv
    h = _register(client)
    now = time.time()
    batch = {"batch_id": "b1", "status": {"ts": now, "line_name": "Línea 1", "area": "Nave A", "overall": "WARN",
                                          "n_alarms": 1, "kpis": {"oee": 81.5}, "app_version": "0.3.0"},
             "events": [{"ts": now - 5, "kind": "raised", "level": "ALARM", "rule": "TOLERANCIA", "var": "z3",
                         "msg": "fuera", "recipe": "R1"}],
             "trend": [{"ts": now - 60, "from": now - 120, "v": {"z3": [181, 180, 182, 181]}, "k": {"oee": 80}}],
             "problems": [{"op": "add", "uid": "u1", "kind": "downtime", "start": now - 600, "end": now - 300,
                           "reason": "Cambio de dado"}]}
    raw = gzip.compress(json.dumps(batch).encode())
    r = client.post("/api/v1/ingest", content=raw, headers={**h, "Content-Encoding": "gzip",
                                                            "Content-Type": "application/json"})
    assert r.status_code == 200 and r.json()["events"] == 1
    # el mismo lote reenviado (p. ej. se cortó la red antes de la respuesta) no se duplica
    dup = client.post("/api/v1/ingest", json=batch, headers=h).json()
    assert dup["duplicate"]
    lines = client.get("/api/v1/lines", headers=V).json()["lines"]
    assert lines[0]["line_id"] == "L01" and lines[0]["online"] and lines[0]["kpis"]["oee"] == 81.5
    assert len(client.get("/api/v1/lines/L01/events", headers=V).json()["events"]) == 1
    tr = client.get("/api/v1/lines/L01/trend?vars=z3", headers=V).json()["trend"]
    assert tr[0]["v"] == {"z3": [181, 180, 182, 181]}
    assert client.get("/api/v1/lines/L01/problems", headers=V).json()["problems"][0]["reason"] == "Cambio de dado"
    client.post("/api/v1/ingest", json={"batch_id": "b2", "problems": [{"op": "del", "uid": "u1"}]}, headers=h)
    assert client.get("/api/v1/lines/L01/problems", headers=V).json()["problems"] == []


def test_permissions(srv):
    client, _ = srv
    h = _register(client)
    assert client.get("/api/v1/lines").status_code == 401
    assert client.get("/api/v1/lines", headers=h).status_code == 401  # una línea no puede leer a las demás
    assert client.post("/api/v1/ingest", json={}, headers=V).status_code == 401
    assert client.post("/api/v1/admin/lines/L01/token", headers=V).status_code == 403
    new = client.post("/api/v1/admin/lines/L01/token", headers={"Authorization": "Bearer ad_x"}).json()["token"]
    assert client.get("/api/v1/me", headers=h).status_code == 401  # la clave anterior deja de servir
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {new}"}).status_code == 200


def test_retention(srv):
    client, eng = srv
    h = _register(client)
    old = time.time() - 400 * 86400
    client.post("/api/v1/ingest", json={"batch_id": "x", "events": [{"ts": old, "msg": "viejo"}],
                                        "trend": [{"ts": old, "v": {}}]}, headers=h)
    n = purge(eng, 365)
    assert n["events"] == 1 and n["trend"] == 1
