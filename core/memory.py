"""Memória local em SQLite (arquivo kyky.db ao lado do projeto)."""
import sqlite3
import time
from pathlib import Path

import os
DB = Path(os.environ.get("KYKY_DB") or Path(__file__).parent.parent / "kyky.db")


def _conn():
    c = sqlite3.connect(DB)
    c.execute(
        "CREATE TABLE IF NOT EXISTS messages("
        "id INTEGER PRIMARY KEY, ts REAL, role TEXT, content TEXT, provider TEXT)"
    )
    return c


def save(role, content, provider=None):
    with _conn() as c:
        c.execute(
            "INSERT INTO messages(ts, role, content, provider) VALUES(?,?,?,?)",
            (time.time(), role, content, provider),
        )


def recent(n=20):
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
    return [{"role": r, "content": t} for r, t in reversed(rows)]
