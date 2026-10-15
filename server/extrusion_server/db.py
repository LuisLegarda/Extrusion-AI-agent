"""Base de datos: PostgreSQL en producción (SQLite para pruebas y para probar sin Docker).

Tablas:
* lines: cada línea registrada, su clave (solo el hash) y su último estado completo.
* events: alarmas, recetas, recorridos, reportes… (un renglón por evento).
* trend: un renglón por línea y minuto con media, mínimo, máximo y último valor de cada variable.
* problems: capturas de paros y defectos (operaciones «add» / «del» por uid).
* batches: lotes ya recibidos (el monitor puede reenviar un lote: se ignora la segunda vez).
* api_keys: claves de lectura y de administración.
"""
from __future__ import annotations

import time
from typing import Optional

from sqlalchemy import (JSON, BigInteger, Boolean, Column, Float, Index, Integer, MetaData, String, Table, Text,
                        UniqueConstraint, create_engine, event)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

JSONType = JSON().with_variant(JSONB(), "postgresql")
metadata = MetaData()

lines = Table(
    "lines", metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(200), nullable=False, default=""),
    Column("area", String(200), nullable=False, default=""),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("created", Float, nullable=False),
    Column("last_seen", Float),
    Column("status_ts", Float),
    Column("status", JSONType),
    Column("app_version", String(40)),
    Column("enabled", Boolean, nullable=False, default=True),
)

events = Table(
    "events", metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("line_id", String(64), nullable=False),
    Column("ts", Float, nullable=False),
    Column("kind", String(40)),
    Column("level", String(10)),
    Column("rule", String(60)),
    Column("var", String(120)),
    Column("msg", Text),
    Column("recipe", String(200)),
    Index("ix_events_line_ts", "line_id", "ts"),
)

trend = Table(
    "trend", metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("line_id", String(64), nullable=False),
    Column("ts", Float, nullable=False),
    Column("t_from", Float),
    Column("v", JSONType),  # {variable: [media, mín, máx, último]}
    Column("k", JSONType),  # {kpi: valor}
    Index("ix_trend_line_ts", "line_id", "ts"),
)

problems = Table(
    "problems", metadata,
    Column("line_id", String(64), primary_key=True),
    Column("uid", String(64), primary_key=True),
    Column("start", Float),
    Column("end", Float),
    Column("kind", String(20)),
    Column("record", JSONType),
    Column("deleted", Boolean, nullable=False, default=False),
    Column("updated", Float, nullable=False),
    Index("ix_problems_line_start", "line_id", "start"),
)

batches = Table(
    "batches", metadata,
    Column("line_id", String(64), nullable=False),
    Column("batch_id", String(64), nullable=False),
    Column("received", Float, nullable=False),
    UniqueConstraint("line_id", "batch_id", name="uq_batches"),
)

api_keys = Table(
    "api_keys", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(200), nullable=False),
    Column("role", String(20), nullable=False),  # viewer | admin
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("created", Float, nullable=False),
    Column("revoked", Boolean, nullable=False, default=False),
)


def make_engine(url: str) -> Engine:
    kw = {}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False}
    else:
        kw.update(pool_pre_ping=True, pool_size=10, max_overflow=20)
    eng = create_engine(url, future=True, **kw)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _wal(dbapi_conn, _):  # pragma: no cover - detalle de SQLite
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()
    metadata.create_all(eng)
    return eng


def purge(eng: Engine, retention_days: int, now: Optional[float] = None) -> dict[str, int]:
    """Borra eventos, tendencias y lotes más viejos que la retención (las capturas de problemas se conservan)."""
    now = time.time() if now is None else now
    cut = now - retention_days * 86400
    out = {}
    with eng.begin() as c:
        for name, tbl, col in (("events", events, events.c.ts), ("trend", trend, trend.c.ts),
                               ("batches", batches, batches.c.received)):
            out[name] = c.execute(tbl.delete().where(col < cut)).rowcount or 0
    return out
