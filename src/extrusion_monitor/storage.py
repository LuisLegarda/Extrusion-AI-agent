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
"""


class Historian:
    def __init__(self, path: Path | str, retention_days: float = 90):
        self.path = str(path)
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
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

    def samples(self, var_id: str, since: float, until: float | None = None) -> list[tuple[float, float]]:
        until = until or time.time()
        with self._lock:
            cur = self._conn.execute(
                "SELECT ts, value FROM samples WHERE var=? AND ts BETWEEN ? AND ? ORDER BY ts",
                (var_id, since, until))
            return cur.fetchall()

    def events(self, since: float, limit: int = 500) -> list[tuple]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM events WHERE ts>=? ORDER BY ts DESC LIMIT ?", (since, limit))
            return cur.fetchall()

    def export_csv(self, path: Path | str, since: float, until: float | None = None) -> int:
        """Exporta muestras en formato ancho: una columna por variable."""
        until = until or time.time()
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, var, COALESCE(value, text) FROM samples WHERE ts BETWEEN ? AND ? ORDER BY ts",
                (since, until)).fetchall()
        variables = sorted({r[1] for r in rows})
        by_ts: dict[float, dict[str, object]] = {}
        for ts, var, val in rows:
            by_ts.setdefault(ts, {})[var] = val
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["fecha_hora", *variables])
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

    def close(self) -> None:
        with self._lock:
            self._conn.close()
