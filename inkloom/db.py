"""SQLite storage for the Inkloom workspace."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("INKLOOM_DATA", ROOT / "data"))
DB_PATH = Path(os.environ.get("INKLOOM_DB", DATA / "inkloom.db"))
UPLOADS = DATA / "uploads"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  affiliation TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS brand (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  name TEXT NOT NULL,
  legal_name TEXT NOT NULL,
  voice TEXT NOT NULL,
  audience TEXT NOT NULL,
  reading_grades_json TEXT NOT NULL,
  seed_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS guidelines (
  id INTEGER PRIMARY KEY,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  severity TEXT NOT NULL,
  match_type TEXT NOT NULL,
  match_value TEXT NOT NULL DEFAULT '',
  suggestion TEXT NOT NULL DEFAULT '',
  good_example TEXT NOT NULL DEFAULT '',
  bad_example TEXT NOT NULL DEFAULT '',
  confidential INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  updated_by INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY,
  topic TEXT NOT NULL,
  statement TEXT NOT NULL,
  source_label TEXT NOT NULL,
  severity TEXT NOT NULL,
  contradicts_json TEXT NOT NULL DEFAULT '[]',
  supports_json TEXT NOT NULL DEFAULT '[]',
  covers_json TEXT NOT NULL DEFAULT '[]',
  suggested TEXT NOT NULL DEFAULT '',
  replacement TEXT NOT NULL DEFAULT '',
  confidential INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  effective_on TEXT NOT NULL DEFAULT '',
  review_after TEXT NOT NULL DEFAULT '',
  updated_by INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS terms (
  id INTEGER PRIMARY KEY,
  preferred TEXT NOT NULL,
  avoid_json TEXT NOT NULL DEFAULT '[]',
  definition TEXT NOT NULL DEFAULT '',
  context TEXT NOT NULL DEFAULT '',
  severity TEXT NOT NULL,
  confidential INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  updated_by INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  usage_rules TEXT NOT NULL DEFAULT '',
  color_hex TEXT NOT NULL DEFAULT '',
  rules_json TEXT NOT NULL DEFAULT '{}',
  file_path TEXT,
  file_name TEXT,
  mime TEXT,
  confidential INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  updated_by INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  format TEXT NOT NULL,
  channel TEXT NOT NULL,
  purpose TEXT NOT NULL,
  origin TEXT NOT NULL,
  status TEXT NOT NULL,
  author_id INTEGER NOT NULL,
  assignee_id INTEGER,
  current_revision_id INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(author_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS revisions (
  id INTEGER PRIMARY KEY,
  submission_id INTEGER NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  alt_text TEXT NOT NULL DEFAULT '',
  placement_notes TEXT NOT NULL DEFAULT '',
  decorative INTEGER NOT NULL DEFAULT 0,
  asset_id INTEGER,
  file_path TEXT,
  file_name TEXT,
  mime TEXT,
  image_json TEXT,
  review_json TEXT,
  created_by INTEGER NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(submission_id) REFERENCES submissions(id)
);

CREATE TABLE IF NOT EXISTS findings (
  id INTEGER PRIMARY KEY,
  submission_id INTEGER NOT NULL,
  revision_id INTEGER NOT NULL,
  category TEXT NOT NULL,
  severity TEXT NOT NULL,
  status TEXT NOT NULL,
  excerpt TEXT NOT NULL DEFAULT '',
  explanation TEXT NOT NULL,
  suggestion TEXT NOT NULL DEFAULT '',
  suggestion_mode TEXT NOT NULL,
  replaces TEXT NOT NULL DEFAULT '',
  replace_start INTEGER,
  replace_end INTEGER,
  replace_text TEXT,
  source_type TEXT NOT NULL,
  source_id INTEGER,
  source_label TEXT NOT NULL,
  source_excerpt TEXT NOT NULL DEFAULT '',
  confidential_source INTEGER NOT NULL DEFAULT 0,
  pattern_key TEXT NOT NULL,
  start_pos INTEGER,
  end_pos INTEGER,
  decision_note TEXT NOT NULL DEFAULT '',
  decision_by INTEGER,
  created_at TEXT NOT NULL,
  decided_at TEXT
);

CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY,
  submission_id INTEGER NOT NULL,
  finding_id INTEGER,
  author_id INTEGER NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  submission_id INTEGER NOT NULL,
  actor_id INTEGER,
  action TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  from_status TEXT,
  to_status TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY,
  actor_id INTEGER,
  action TEXT NOT NULL,
  target_type TEXT NOT NULL DEFAULT '',
  target_id INTEGER,
  detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_findings_sub ON findings(submission_id);
CREATE INDEX IF NOT EXISTS idx_findings_pattern ON findings(pattern_key);
CREATE INDEX IF NOT EXISTS idx_events_sub ON events(submission_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""


def loads(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def init_db() -> None:
    with transaction() as conn:
        conn.executescript(SCHEMA)
        from inkloom.seed import seed_if_empty

        seed_if_empty(conn)


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def audit(conn, actor_id, action: str, detail: str = "", target_type: str = "", target_id: int | None = None) -> None:
    conn.execute(
        """
        INSERT INTO audit (actor_id, action, target_type, target_id, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (actor_id, action, target_type, target_id, detail, now_iso()),
    )
