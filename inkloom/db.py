"""SQLite storage for the Inkloom workspace."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  role TEXT NOT NULL,
  title TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS guidelines (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  body TEXT NOT NULL,
  confidential INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  updated_by TEXT
);

CREATE TABLE IF NOT EXISTS facts (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  statement TEXT NOT NULL,
  source TEXT NOT NULL,
  as_of TEXT NOT NULL,
  confidential INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'approved',
  guideline_code TEXT NOT NULL,
  checks_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS terms (
  id TEXT PRIMARY KEY,
  phrase TEXT NOT NULL,
  replacement TEXT NOT NULL,
  kind TEXT NOT NULL,
  severity TEXT NOT NULL,
  rationale TEXT NOT NULL,
  guideline_code TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  usage_text TEXT NOT NULL,
  hex TEXT,
  role TEXT,
  approved INTEGER NOT NULL DEFAULT 1,
  confidential INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS submissions (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  format TEXT NOT NULL,
  channel TEXT NOT NULL,
  purpose TEXT NOT NULL,
  status TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  assignee_id TEXT,
  asset_intent TEXT NOT NULL DEFAULT 'none',
  current_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS versions (
  id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  body TEXT NOT NULL,
  alt_text TEXT NOT NULL DEFAULT '',
  image_path TEXT,
  note TEXT NOT NULL,
  author_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (submission_id, version)
);

CREATE TABLE IF NOT EXISTS findings (
  id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  rule_id TEXT NOT NULL,
  category TEXT NOT NULL,
  severity TEXT NOT NULL,
  title TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  explanation TEXT NOT NULL,
  public_explanation TEXT,
  suggestion TEXT NOT NULL,
  replacement TEXT,
  apply_mode TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_label TEXT NOT NULL,
  confidence REAL NOT NULL,
  span_start INTEGER,
  span_end INTEGER,
  status TEXT NOT NULL,
  decision_note TEXT,
  decided_by TEXT,
  decided_at TEXT
);

CREATE TABLE IF NOT EXISTS comments (
  id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL,
  author_id TEXT NOT NULL,
  body TEXT NOT NULL,
  finding_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
  id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL,
  note TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  detail TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_findings_sub ON findings (submission_id, version);
CREATE INDEX IF NOT EXISTS idx_versions_sub ON versions (submission_id, version);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log (at);
"""


def db_path() -> str:
    return os.environ.get("INKLOOM_DB", str(Path("data") / "inkloom.db"))


def uploads_dir() -> Path:
    path = Path(os.environ.get("INKLOOM_UPLOADS", str(Path("data") / "uploads")))
    path.mkdir(parents=True, exist_ok=True)
    return path


def connect() -> sqlite3.Connection:
    path = Path(db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db() -> None:
    path = Path(db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        probe = sqlite3.connect(path)
        version = probe.execute("PRAGMA user_version").fetchone()[0]
        has_users = probe.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        probe.close()
        if has_users and version != SCHEMA_VERSION:
            path.unlink()
    con = connect()
    con.executescript(SCHEMA)
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    con.commit()
    con.close()
