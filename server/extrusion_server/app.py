"""API HTTP del servidor (FastAPI).

Seguridad:
* Cada línea envía con su propia clave (`Authorization: Bearer <clave>`). En la base solo se guarda su hash.
* Una línea nueva se registra con la clave de registro del servidor (`EXTRUSION_ENROLL_KEY`); el servidor le
  responde su clave de línea, que el monitor guarda. Sin clave de registro configurada, el registro está apagado.
* Para leer (dashboards) se usa una clave «viewer»; para administrar, una «admin» (se crean con la CLI).
* El servidor nunca envía órdenes a las líneas: el flujo de datos es solo de la línea hacia el servidor.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
import zlib
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from . import PROTOCOL, __version__
from .db import api_keys, batches, events, lines, make_engine, problems, purge, trend

log = logging.getLogger("extrusion_server")

MAX_BODY = 20 * 1024 * 1024  # un lote comprimido de días sin red cabe de sobra
MAX_ITEMS = 50000
LINE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


@dataclass
class Settings:
    database_url: str = "sqlite:///./extrusion.db"
    enroll_key: str = ""
    retention_days: int = 365
    offline_s: float = 60.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(database_url=os.environ.get("EXTRUSION_DATABASE_URL", cls.database_url),
                   enroll_key=os.environ.get("EXTRUSION_ENROLL_KEY", ""),
                   retention_days=int(os.environ.get("EXTRUSION_RETENTION_DAYS", "365")),
                   offline_s=float(os.environ.get("EXTRUSION_OFFLINE_S", "60")))


# --- modelos del protocolo -----------------------------------------------------------------------------
class RegisterIn(BaseModel):
    line_id: str = Field(..., min_length=1, max_length=64)
    line_name: str = ""
    area: str = ""
    app_version: str = ""


class IngestIn(BaseModel):
    protocol: int = PROTOCOL
    batch_id: Optional[str] = Field(None, max_length=64)
    status: Optional[dict[str, Any]] = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    trend: list[dict[str, Any]] = Field(default_factory=list)
    problems: list[dict[str, Any]] = Field(default_factory=list)


def _f(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def _s(x, n: int) -> Optional[str]:
    return None if x is None else str(x)[:n]


def create_app(settings: Optional[Settings] = None, engine: Optional[Engine] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    eng = engine or make_engine(settings.database_url)
    app = FastAPI(title="Servidor del monitor de extrusión", version=__version__)
    app.state.engine = eng
    app.state.settings = settings
    app.add_middleware(GzipRequest)
    _start_purger(app)

    # --- autenticación ------------------------------------------------------------------------------
    def _bearer(authorization: Optional[str]) -> str:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "Falta la clave (Authorization: Bearer …)")
        return authorization[7:].strip()

    def line_auth(authorization: Optional[str] = Header(None)) -> dict:
        h = hash_token(_bearer(authorization))
        with eng.connect() as c:
            row = c.execute(select(lines).where(lines.c.token_hash == h)).mappings().first()
        if row is None or not row["enabled"]:
            raise HTTPException(401, "Clave de línea no válida")
        return dict(row)

    def key_auth(role: str):
        def dep(authorization: Optional[str] = Header(None)) -> dict:
            h = hash_token(_bearer(authorization))
            with eng.connect() as c:
                row = c.execute(select(api_keys).where(api_keys.c.token_hash == h)).mappings().first()
            if row is None or row["revoked"] or (role == "admin" and row["role"] != "admin"):
                raise HTTPException(401 if row is None else 403, "Clave no válida para esta operación")
            return dict(row)
        return dep

    viewer = key_auth("viewer")
    admin = key_auth("admin")

    async def _json_body(request: Request) -> Any:
        raw = await request.body()  # ya descomprimido por GzipRequest
        try:
            return json.loads(raw)
        except ValueError:
            raise HTTPException(400, "JSON inválido")

    # --- público ------------------------------------------------------------------------------------
    @app.get("/api/v1/health")
    def health():
        try:
            with eng.connect() as c:
                c.execute(select(func.count()).select_from(lines))
            db_ok = True
        except Exception:  # pragma: no cover
            db_ok = False
        return {"ok": db_ok, "version": __version__, "protocol": PROTOCOL, "time": time.time(),
                "registration": bool(settings.enroll_key)}

    @app.post("/api/v1/register")
    def register(body: RegisterIn, x_enroll_key: Optional[str] = Header(None)):
        if not settings.enroll_key:
            raise HTTPException(403, "El registro de líneas está desactivado en el servidor")
        if not x_enroll_key or not hmac.compare_digest(x_enroll_key, settings.enroll_key):
            raise HTTPException(401, "Clave de registro incorrecta")
        if not LINE_ID.match(body.line_id):
            raise HTTPException(422, "ID de línea inválido (letras, números, . _ -)")
        token = new_token("ln")
        now = time.time()
        try:
            with eng.begin() as c:
                c.execute(insert(lines).values(id=body.line_id, name=body.line_name or body.line_id,
                                               area=body.area, token_hash=hash_token(token), created=now,
                                               app_version=body.app_version[:40], enabled=True))
        except IntegrityError:
            raise HTTPException(409, f"La línea «{body.line_id}» ya está registrada: pide al administrador "
                                     "una clave nueva o usa otro ID de línea")
        log.info("Línea registrada: %s", body.line_id)
        return {"line_id": body.line_id, "token": token}

    # --- línea --------------------------------------------------------------------------------------
    @app.get("/api/v1/me")
    def me(line: dict = Depends(line_auth)):
        return {"line_id": line["id"], "name": line["name"], "area": line["area"], "last_seen": line["last_seen"]}

    @app.post("/api/v1/ingest")
    async def ingest(request: Request, line: dict = Depends(line_auth)):
        try:
            body = IngestIn.model_validate(await _json_body(request))
        except ValueError as exc:
            raise HTTPException(422, f"Lote inválido: {exc}")
        if len(body.events) + len(body.trend) + len(body.problems) > MAX_ITEMS:
            raise HTTPException(413, "Demasiados renglones en un lote")
        lid, now = line["id"], time.time()
        with eng.begin() as c:
            if body.batch_id:
                try:
                    with c.begin_nested():
                        c.execute(insert(batches).values(line_id=lid, batch_id=body.batch_id, received=now))
                except IntegrityError:
                    c.execute(update(lines).where(lines.c.id == lid).values(last_seen=now))
                    return {"ok": True, "duplicate": True}
            if body.events:
                c.execute(insert(events), [
                    {"line_id": lid, "ts": _f(e.get("ts")) or now, "kind": _s(e.get("kind"), 40),
                     "level": _s(e.get("level"), 10), "rule": _s(e.get("rule"), 60), "var": _s(e.get("var"), 120),
                     "msg": _s(e.get("msg"), 4000), "recipe": _s(e.get("recipe"), 200)} for e in body.events])
            if body.trend:
                c.execute(insert(trend), [
                    {"line_id": lid, "ts": _f(t.get("ts")) or now, "t_from": _f(t.get("from")),
                     "v": t.get("v") or {}, "k": t.get("k") or {}} for t in body.trend])
            for op in body.problems:
                _apply_problem(c, lid, op, now)
            vals: dict[str, Any] = {"last_seen": now}
            if body.status is not None:
                st = body.status
                vals.update(status=st, status_ts=_f(st.get("ts")) or now,
                            app_version=_s(st.get("app_version"), 40))
                if st.get("line_name"):
                    vals["name"] = _s(st["line_name"], 200)
                if "area" in st:
                    vals["area"] = _s(st.get("area") or "", 200)
            c.execute(update(lines).where(lines.c.id == lid).values(**vals))
        return {"ok": True, "events": len(body.events), "trend": len(body.trend), "problems": len(body.problems)}

    # --- lectura (dashboards) -----------------------------------------------------------------------
    def _summary(row, now: float) -> dict:
        st = row["status"] or {}
        online = bool(row["last_seen"] and now - row["last_seen"] <= settings.offline_s and not st.get("closed"))
        return {"line_id": row["id"], "name": row["name"], "area": row["area"], "last_seen": row["last_seen"],
                "status_ts": row["status_ts"], "online": online, "closed": bool(st.get("closed")),
                "app_version": row["app_version"], "overall": st.get("overall"), "recipe": st.get("recipe"),
                "n_alarms": st.get("n_alarms", 0), "n_warnings": st.get("n_warnings", 0),
                "machine": st.get("machine"), "kpis": st.get("kpis") or {}}

    @app.get("/api/v1/lines")
    def list_lines(key: dict = Depends(viewer)):
        now = time.time()
        with eng.connect() as c:
            rows = c.execute(select(lines).where(lines.c.enabled.is_(True)).order_by(lines.c.area, lines.c.name)
                             ).mappings().all()
        return {"time": now, "lines": [_summary(r, now) for r in rows]}

    def _line(c, line_id: str):
        row = c.execute(select(lines).where(lines.c.id == line_id)).mappings().first()
        if row is None:
            raise HTTPException(404, "Línea no encontrada")
        return row

    @app.get("/api/v1/lines/{line_id}/status")
    def line_status(line_id: str, key: dict = Depends(viewer)):
        with eng.connect() as c:
            row = _line(c, line_id)
        return {**_summary(row, time.time()), "status": row["status"]}

    @app.get("/api/v1/lines/{line_id}/events")
    def line_events(line_id: str, since: float = 0, until: Optional[float] = None,
                    limit: int = Query(1000, ge=1, le=20000), key: dict = Depends(viewer)):
        cond = [events.c.line_id == line_id, events.c.ts >= since]
        if until is not None:
            cond.append(events.c.ts <= until)
        with eng.connect() as c:
            _line(c, line_id)
            rows = c.execute(select(events).where(and_(*cond)).order_by(events.c.ts.desc()).limit(limit)
                             ).mappings().all()
        return {"events": [{k: r[k] for k in ("ts", "kind", "level", "rule", "var", "msg", "recipe")}
                           for r in reversed(rows)]}

    @app.get("/api/v1/lines/{line_id}/trend")
    def line_trend(line_id: str, since: float = 0, until: Optional[float] = None,
                   vars: str = Query("", description="ids separados por coma (vacío = todas)"),
                   limit: int = Query(5000, ge=1, le=50000), key: dict = Depends(viewer)):
        cond = [trend.c.line_id == line_id, trend.c.ts >= since]
        if until is not None:
            cond.append(trend.c.ts <= until)
        want = {v for v in vars.split(",") if v}
        with eng.connect() as c:
            _line(c, line_id)
            rows = c.execute(select(trend).where(and_(*cond)).order_by(trend.c.ts.desc()).limit(limit)
                             ).mappings().all()
        out = []
        for r in reversed(rows):
            v = r["v"] or {}
            if want:
                v = {k: x for k, x in v.items() if k in want}
            out.append({"ts": r["ts"], "from": r["t_from"], "v": v, "k": r["k"] or {}})
        return {"trend": out}

    @app.get("/api/v1/lines/{line_id}/problems")
    def line_problems(line_id: str, since: float = 0, key: dict = Depends(viewer)):
        with eng.connect() as c:
            _line(c, line_id)
            rows = c.execute(select(problems).where(and_(problems.c.line_id == line_id, problems.c.deleted.is_(False),
                                                         problems.c.end >= since)).order_by(problems.c.start)
                             ).mappings().all()
        return {"problems": [r["record"] for r in rows]}

    # --- administración -----------------------------------------------------------------------------
    @app.post("/api/v1/admin/lines/{line_id}/token")
    def rotate_token(line_id: str, key: dict = Depends(admin)):
        token = new_token("ln")
        with eng.begin() as c:
            _line(c, line_id)
            c.execute(update(lines).where(lines.c.id == line_id).values(token_hash=hash_token(token), enabled=True))
        return {"line_id": line_id, "token": token}

    @app.post("/api/v1/admin/lines/{line_id}/disable")
    def disable_line(line_id: str, key: dict = Depends(admin)):
        with eng.begin() as c:
            _line(c, line_id)
            c.execute(update(lines).where(lines.c.id == line_id).values(enabled=False))
        return {"line_id": line_id, "enabled": False}

    return app


class GzipRequest:
    """Middleware ASGI: acepta cuerpos comprimidos (Content-Encoding: gzip) con límite de tamaño."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        gz = headers.get(b"content-encoding", b"").lower() == b"gzip"
        chunks, size = [], 0
        while True:
            msg = await receive()
            if msg["type"] != "http.request":
                break
            chunks.append(msg.get("body", b""))
            size += len(chunks[-1])
            if size > MAX_BODY:
                return await _plain(send, 413, "Lote demasiado grande")
            if not msg.get("more_body"):
                break
        body = b"".join(chunks)
        if gz:
            try:
                d = zlib.decompressobj(16 + zlib.MAX_WBITS)
                body = d.decompress(body, 10 * MAX_BODY)
                if d.unconsumed_tail:
                    return await _plain(send, 413, "Lote demasiado grande")
            except zlib.error:
                return await _plain(send, 400, "Contenido gzip inválido")
            scope = dict(scope)
            scope["headers"] = [(k, v) for k, v in scope["headers"]
                                if k not in (b"content-encoding", b"content-length")] + \
                [(b"content-length", str(len(body)).encode())]
        sent = False

        async def replay():
            nonlocal sent
            if sent:
                return await receive()
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        return await self.app(scope, replay, send)


async def _plain(send, status: int, detail: str) -> None:
    data = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode())]})
    await send({"type": "http.response.body", "body": data})


def _apply_problem(c, line_id: str, op: dict, now: float) -> None:
    """Capturas de problemas: {"op": "add", ...registro con uid} o {"op": "del", "uid": …}."""
    uid = _s(op.get("uid"), 64)
    if not uid:
        return
    cur = c.execute(select(problems.c.uid).where(and_(problems.c.line_id == line_id, problems.c.uid == uid))).first()
    if op.get("op") == "del":
        if cur is not None:
            c.execute(update(problems).where(and_(problems.c.line_id == line_id, problems.c.uid == uid))
                      .values(deleted=True, updated=now))
        return
    rec = {k: v for k, v in op.items() if k != "op"}
    vals = dict(start=_f(rec.get("start")), end=_f(rec.get("end")), kind=_s(rec.get("kind"), 20), record=rec,
                deleted=False, updated=now)
    if cur is None:
        c.execute(insert(problems).values(line_id=line_id, uid=uid, **vals))
    else:
        c.execute(update(problems).where(and_(problems.c.line_id == line_id, problems.c.uid == uid)).values(**vals))


def _start_purger(app: FastAPI) -> None:
    """Limpieza diaria de lo que pasa la retención (hilo en segundo plano)."""
    if os.environ.get("EXTRUSION_NO_PURGE"):
        return

    def run():
        while True:
            try:
                n = purge(app.state.engine, app.state.settings.retention_days)
                if any(n.values()):
                    log.info("Limpieza por retención: %s", n)
            except Exception:  # pragma: no cover
                log.exception("Limpieza por retención")
            time.sleep(24 * 3600)

    threading.Thread(target=run, name="purga", daemon=True).start()
