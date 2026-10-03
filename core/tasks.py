"""Lista de tarefas (SQLite, mesmo kyky.db da memória)."""
import sqlite3
import time
from .memory import DB


def _conn():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS tasks("
              "id INTEGER PRIMARY KEY, ts REAL, text TEXT, due TEXT, done INTEGER DEFAULT 0)")
    return c


def add_task(text, due=""):
    with _conn() as c:
        cur = c.execute("INSERT INTO tasks(ts, text, due) VALUES(?,?,?)", (time.time(), text, due or ""))
    return f"tarefa #{cur.lastrowid} criada: {text}" + (f" (prazo {due})" if due else "")


def list_tasks(status="pending"):
    q = "SELECT id, text, due, done FROM tasks"
    if status == "pending":
        q += " WHERE done=0"
    with _conn() as c:
        rows = c.execute(q + " ORDER BY (due=''), due, id").fetchall()
    return "\n".join(f"#{i} [{'x' if d else ' '}] {t}" + (f" (prazo {due})" if due else "")
                     for i, t, due, d in rows) or "(nenhuma tarefa)"


def complete_task(id):
    with _conn() as c:
        cur = c.execute("UPDATE tasks SET done=1 WHERE id=?", (int(id),))
    return f"tarefa #{id} concluída" if cur.rowcount else f"tarefa #{id} não encontrada"
