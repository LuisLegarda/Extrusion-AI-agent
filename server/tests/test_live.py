"""Servidor HTTP real (uvicorn) + cliente real del monitor (urllib). Se omite si no se puede abrir un puerto."""
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

os.environ["EXTRUSION_NO_PURGE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import uvicorn  # noqa: E402

from extrusion_monitor.cloud import CloudOutbox, ServerError, register, request  # noqa: E402
from extrusion_monitor.fleet import StationSettings  # noqa: E402
from extrusion_server.app import Settings, create_app  # noqa: E402
from extrusion_server.db import make_engine  # noqa: E402


def _free_port():
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
    except OSError:
        pytest.skip("no se puede abrir un puerto local en este entorno")


def test_real_http_roundtrip(tmp_path):
    port = _free_port()
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'db.sqlite'}"
    app = create_app(Settings(enroll_key="k"), engine=make_engine(url))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            request(base, "/api/v1/health", timeout=1)
            break
        except ServerError:
            time.sleep(0.1)
    try:
        line = f"LIVE-{int(time.time() * 1000) % 10**8}"
        token = register(base, "k", line, "Línea en vivo", "Pruebas")
        st = StationSettings(server_enabled=True, server_url=base, server_token=token)
        box = CloudOutbox(tmp_path / "hmi", lambda: st)
        box.enqueue([{"ts": time.time(), "msg": "ñandú «ok»"}], [{"ts": time.time(), "v": {"a": [1, 1, 1, 1]}}])
        box.set_status({"ts": time.time(), "overall": "OK"})
        assert box.flush(), box.last_error
        assert request(base, "/api/v1/me", token=token)["line_id"] == line
        with pytest.raises(ServerError) as e:
            register(base, "otra", "X1", "", "")
        assert e.value.status == 401
    finally:
        server.should_exit = True
        th.join(5)
