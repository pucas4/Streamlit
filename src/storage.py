"""SQLite persistence so posts/chat aren't re-summarized (and re-billed) on every
page load. Note: on Streamlit Community Cloud the filesystem is ephemeral and
resets on redeploy/restart -- use the Setup tab's export buttons to back up
periodically if that matters to you."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    slug TEXT PRIMARY KEY,
    title TEXT,
    subtitle TEXT,
    url TEXT,
    post_date TEXT,
    audience TEXT,
    summary TEXT,
    fetched_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    source TEXT,
    author TEXT,
    created_at TEXT,
    body TEXT,
    plain_english TEXT,
    is_position_change INTEGER DEFAULT 0,
    analyzed_at TEXT DEFAULT (datetime('now'))
);
"""


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def post_exists(slug: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM posts WHERE slug = ?", (slug,)).fetchone()
        return row is not None


def upsert_post(slug: str, title: str, subtitle: str, url: str, post_date: str, audience: str, summary: str) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO posts (slug, title, subtitle, url, post_date, audience, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                 title=excluded.title, subtitle=excluded.subtitle, url=excluded.url,
                 post_date=excluded.post_date, audience=excluded.audience, summary=excluded.summary""",
            (slug, title, subtitle, url, post_date, audience, summary),
        )


def get_all_posts() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute("SELECT * FROM posts ORDER BY post_date DESC").fetchall()


def chat_message_exists(msg_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM chat_messages WHERE id = ?", (msg_id,)).fetchone()
        return row is not None


def upsert_chat_message(
    msg_id: str, source: str, author: str, created_at: str, body: str, plain_english: str, is_position_change: bool
) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO chat_messages (id, source, author, created_at, body, plain_english, is_position_change)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 plain_english=excluded.plain_english, is_position_change=excluded.is_position_change""",
            (msg_id, source, author, created_at, body, plain_english, int(is_position_change)),
        )


def get_all_chat_messages() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute("SELECT * FROM chat_messages ORDER BY created_at DESC").fetchall()


def get_position_changes() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM chat_messages WHERE is_position_change = 1 ORDER BY created_at DESC"
        ).fetchall()
