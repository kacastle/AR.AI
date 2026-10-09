"""SQLite storage. Learner data stays in this one local file."""
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("DB_PATH", ROOT / "data" / "tutor.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id TEXT PRIMARY KEY,
    tutor_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS children (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL REFERENCES groups(id),
    name TEXT NOT NULL,
    picture TEXT NOT NULL,
    profile TEXT NOT NULL,
    interests TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS skill_state (
    child_id TEXT NOT NULL REFERENCES children(id),
    skill_id TEXT NOT NULL,
    score REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    correct_streak INTEGER NOT NULL DEFAULT 0,
    wrong_streak INTEGER NOT NULL DEFAULT 0,
    support_level TEXT NOT NULL,
    review_step INTEGER,
    next_review_at TEXT,
    mastered_at TEXT,
    PRIMARY KEY (child_id, skill_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL REFERENCES groups(id),
    present TEXT NOT NULL,
    phase TEXT NOT NULL,
    phase_ends_at TEXT,
    read_along_story_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL DEFAULT 1,
    current_child_id TEXT,
    current_item_id TEXT,
    current_turn TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    child_id TEXT NOT NULL REFERENCES children(id),
    item_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    skill_id TEXT,
    given TEXT NOT NULL,
    correct INTEGER NOT NULL,
    mistake_type TEXT,
    hints_used INTEGER NOT NULL,
    attempt INTEGER NOT NULL,
    time_ms INTEGER NOT NULL,
    support_level TEXT NOT NULL,
    next_action TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS generated_items (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    child_id TEXT REFERENCES children(id),
    session_id TEXT REFERENCES sessions(id),
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    generated_item_id TEXT NOT NULL REFERENCES generated_items(id),
    status TEXT NOT NULL DEFAULT 'pending',
    decided_at TEXT
);
"""


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """One connection per request: commit on success, roll back on error, always close."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Columns added after a table was first created: (table, column, type).
ADDED_COLUMNS = [
    ("sessions", "current_turn", "TEXT"),
]


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        for table, column, col_type in ADDED_COLUMNS:
            existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
