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

    def history_table(self, since: float, until: float | None = None, variables: Optional[list[str]] = None,
                      headers: Optional[dict[str, str]] = None) -> tuple[list[str], list[list]]:
        """Muestras en formato ancho (una columna por variable): encabezados y filas [fecha, valores…]."""
        import datetime as dt
        until = until or time.time()
        if variables is None:
            variables = self.variables()
        if not variables:
            return ["fecha_hora"], []
        # una variable a la vez: así cada consulta usa el índice (var, ts) en lugar de recorrer la tabla
        by_ts: dict[float, dict[str, object]] = {}
        for var in variables:
            with self._lock:
                rows = self._conn.execute("SELECT ts, COALESCE(value, text) FROM samples WHERE var=? AND ts BETWEEN "
                                          "? AND ?", (var, since, until)).fetchall()
            for ts, val in rows:
                by_ts.setdefault(ts, {})[var] = val
        variables = [v for v in variables if any(v in r for r in by_ts.values())] if by_ts else []
        header = ["fecha_hora", *[(headers or {}).get(v, v) for v in variables]]
        out = [[dt.datetime.fromtimestamp(ts).replace(microsecond=0), *[by_ts[ts].get(v) for v in variables]]
               for ts in sorted(by_ts)]
        return header, out

    def variables(self) -> list[str]:
        """Variables con datos guardados (salta por el índice: no recorre la tabla)."""
        with self._lock:
            rows = self._conn.execute(
                "WITH RECURSIVE v(x) AS (SELECT MIN(var) FROM samples UNION ALL "
                "SELECT (SELECT MIN(var) FROM samples WHERE var > v.x) FROM v WHERE v.x IS NOT NULL) "
                "SELECT x FROM v WHERE x IS NOT NULL").fetchall()
        return [r[0] for r in rows]

    def export_csv(self, path: Path | str, since: float, until: float | None = None,
                   variables: Optional[list[str]] = None, headers: Optional[dict[str, str]] = None) -> int:
        """Exporta muestras en formato ancho: una columna por variable."""
        header, rows = self.history_table(since, until, variables, headers)
        if variables is not None and not variables:
            return 0
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(header)
            for r in rows:
                w.writerow([r[0].strftime("%Y-%m-%d %H:%M:%S"), *["" if v is None else v for v in r[1:]]])
        return len(rows)

    PURGE_CHUNK = 20000  # filas por bloque: el candado se suelta entre bloques y el monitoreo no se detiene

    def _maybe_purge(self) -> None:
        now = time.time()
        if now - self._last_purge < 3600:
            return
        self._last_purge = now
        self.purge(now - self.retention_days * 86400)

    def purge(self, cutoff: float) -> int:
        """Borra lo anterior a `cutoff`. Devuelve cuántas muestras borró.

        Las muestras se guardan en orden de tiempo, así que lo viejo está al inicio de la tabla (rowid bajo):
        se busca el primer rowid que se conserva y se borra por bloques de rowid, sin recorrer toda la tabla.
        """
        with self._lock:
            row = self._conn.execute("SELECT rowid FROM samples WHERE ts >= ? ORDER BY rowid LIMIT 1",
                                     (cutoff,)).fetchone()
            if row is None:
                row = self._conn.execute("SELECT MAX(rowid) + 1 FROM samples").fetchone()
            first = self._conn.execute("SELECT MIN(rowid) FROM samples").fetchone()[0]
        keep_from = row[0] if row and row[0] is not None else None
        n = 0
        if first is not None and keep_from is not None:
            lo = first
            while lo < keep_from:
                hi = min(keep_from, lo + self.PURGE_CHUNK)
                with self._lock, self._conn:
                    n += self._conn.execute("DELETE FROM samples WHERE rowid >= ? AND rowid < ? AND ts < ?",
                                            (lo, hi, cutoff)).rowcount
                lo = hi
                time.sleep(0.002)  # deja pasar las escrituras del monitoreo que esperan el candado
        with self._lock, self._conn:  # tablas chicas con índice por tiempo
            self._conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            self._conn.execute("DELETE FROM oee WHERE ts < ?", (cutoff,))
        return n

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
