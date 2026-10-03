"""Historial local propio (SQLite). No toca la base de datos del HMI."""
from __future__ import annotations

import csv
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (ts REAL NOT NULL, var TEXT NOT NULL, value REAL, text TEXT);
CREATE INDEX IF NOT EXISTS ix_samples_var_ts ON samples(var, ts);
CREATE TABLE IF NOT EXISTS events (
    ts REAL NOT NULL, kind TEXT, level INTEGER, rule TEXT, var TEXT, message TEXT, recipe TEXT);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS oee (
    ts REAL NOT NULL, dt REAL, state TEXT, speed REAL, nominal REAL, good INTEGER, overall INTEGER);
CREATE INDEX IF NOT EXISTS ix_oee_ts ON oee(ts);
CREATE TABLE IF NOT EXISTS problems (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT, kind TEXT NOT NULL, captured_at REAL NOT NULL,
    start REAL NOT NULL, end REAL NOT NULL, duration_s REAL NOT NULL, category_id TEXT, category TEXT,
    reason_id TEXT, reason TEXT, planned INTEGER DEFAULT 0, scrap REAL DEFAULT 0, unit TEXT, operator TEXT,
    comment TEXT, recipe TEXT);
CREATE INDEX IF NOT EXISTS ix_problems_start ON problems(start);
"""

PROBLEM_FIELDS = ("id", "uid", "kind", "captured_at", "start", "end", "duration_s", "category_id", "category",
                  "reason_id", "reason", "planned", "scrap", "unit", "operator", "comment", "recipe")


class Historian:
    def __init__(self, path: Path | str, retention_days: float = 90):
        self.path = str(path)
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")  # seguro con WAL y mucho más rápido
        self._conn.executescript(SCHEMA)
        self._last_purge = 0.0

    def write_samples(self, rows: Iterable[tuple[float, str, Optional[float], Optional[str]]]) -> None:
        rows = list(rows)
        if not rows:
            return
        with self._lock, self._conn:
            self._conn.executemany("INSERT INTO samples VALUES (?,?,?,?)", rows)
        self._maybe_purge()

    def write_events(self, rows: Iterable[tuple]) -> None:
        rows = list(rows)
        if not rows:
            return
        with self._lock, self._conn:
            self._conn.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?)", rows)

    def write_oee(self, row: tuple) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO oee VALUES (?,?,?,?,?,?,?)", row)

    def oee_samples(self, since: float, until: float | None = None) -> list[tuple]:
        until = until or time.time()
        with self._lock:
            return self._conn.execute(
                "SELECT ts, dt, state, speed, nominal, good, overall FROM oee WHERE ts BETWEEN ? AND ? ORDER BY ts",
                (since, until)).fetchall()

    def events_between(self, since: float, until: float) -> list[tuple]:
        with self._lock:
            return self._conn.execute(
                "SELECT * FROM events WHERE ts BETWEEN ? AND ? ORDER BY ts", (since, until)).fetchall()

    def samples(self, var_id: str, since: float, until: float | None = None) -> list[tuple[float, float]]:
        until = until or time.time()
        with self._lock:
            cur = self._conn.execute(
                "SELECT ts, value FROM samples WHERE var=? AND ts BETWEEN ? AND ? ORDER BY ts",
                (var_id, since, until))
            return cur.fetchall()

    def samples_full(self, var_id: str, since: float, until: float) -> list[tuple]:
        """(ts, valor, texto) de una variable en el periodo."""
        with self._lock:
            return self._conn.execute(
                "SELECT ts, value, text FROM samples WHERE var=? AND ts BETWEEN ? AND ? ORDER BY ts",
                (var_id, since, until)).fetchall()

    def events(self, since: float, limit: int = 500) -> list[tuple]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM events WHERE ts>=? ORDER BY ts DESC LIMIT ?", (since, limit))
            return cur.fetchall()

    def export_csv(self, path: Path | str, since: float, until: float | None = None,
                   variables: Optional[list[str]] = None, headers: Optional[dict[str, str]] = None) -> int:
        """Exporta muestras en formato ancho: una columna por variable."""
        until = until or time.time()
        sql = "SELECT ts, var, COALESCE(value, text) FROM samples WHERE ts BETWEEN ? AND ?"
        args: list = [since, until]
        if variables is not None:
            if not variables:
                return 0
            sql += f" AND var IN ({','.join('?' * len(variables))})"
            args += list(variables)
        with self._lock:
            rows = self._conn.execute(sql + " ORDER BY ts", args).fetchall()
        if variables is None:
            variables = sorted({r[1] for r in rows})
        by_ts: dict[float, dict[str, object]] = {}
        for ts, var, val in rows:
            by_ts.setdefault(ts, {})[var] = val
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["fecha_hora", *[(headers or {}).get(v, v) for v in variables]])
            for ts in sorted(by_ts):
                stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
                w.writerow([stamp, *[by_ts[ts].get(v, "") for v in variables]])
        return len(by_ts)

    def _maybe_purge(self) -> None:
        now = time.time()
        if now - self._last_purge < 3600:
            return
        self._last_purge = now
        cutoff = now - self.retention_days * 86400
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
            self._conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            self._conn.execute("DELETE FROM oee WHERE ts < ?", (cutoff,))

    # --- problemas de proceso (capturados por el operador) ------------------------------------
    def add_problem(self, rec: dict) -> dict:
        """Guarda una captura (paro o defecto). Devuelve el registro completo (con id y uid)."""
        import uuid
        rec = dict(rec)
        rec.setdefault("uid", uuid.uuid4().hex)
        rec.setdefault("captured_at", time.time())
        rec["duration_s"] = max(0.0, float(rec["end"]) - float(rec["start"]))
        rec["planned"] = int(bool(rec.get("planned")))
        cols = [f for f in PROBLEM_FIELDS if f != "id"]
        with self._lock, self._conn:
            cur = self._conn.execute(f"INSERT INTO problems ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                                     [rec.get(c) for c in cols])
            rec["id"] = cur.lastrowid
        return rec

    def delete_problem(self, pid: int) -> Optional[dict]:
        rows = self.problems(ids=[pid])
        if not rows:
            return None
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM problems WHERE id=?", (pid,))
        return rows[0]

    def problems(self, since: float = 0.0, until: Optional[float] = None, kind: Optional[str] = None,
                 ids: Optional[list[int]] = None) -> list[dict]:
        """Capturas que se cruzan con [since, until], ordenadas por inicio."""
        sql = f"SELECT {','.join(PROBLEM_FIELDS)} FROM problems WHERE end >= ? AND start <= ?"
        args: list = [since, until if until is not None else time.time() + 86400]
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        if ids:
            sql += f" AND id IN ({','.join('?' * len(ids))})"
            args += list(ids)
        with self._lock:
            rows = self._conn.execute(sql + " ORDER BY start", args).fetchall()
        return [dict(zip(PROBLEM_FIELDS, r)) for r in rows]

    def planned_intervals(self, since: float, until: float) -> list[tuple[float, float]]:
        """Tramos de paro planeado (no cuentan contra la Disponibilidad del OEE)."""
        return [(r["start"], r["end"]) for r in self.problems(since, until, kind="downtime") if r["planned"]]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
