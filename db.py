import sqlite3
from datetime import datetime
from typing import Optional

from telegram import Update


def init_db(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                bible_version TEXT DEFAULT 'NIV',
                created_at TEXT
            )
            """
        )
        conn.commit()


def upsert_subscriber(db_path: str, update: Update) -> None:
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO subscribers
            (chat_id, username, first_name, bible_version, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                chat.id,
                user.username,
                user.first_name,
                "NIV",
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def remove_subscriber(db_path: str, update: Update) -> bool:
    chat = update.effective_chat
    if not chat:
        return False
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat.id,))
        conn.commit()
        return cur.rowcount > 0


def list_subscribers(db_path: str) -> list[int]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT chat_id FROM subscribers").fetchall()
    return [row[0] for row in rows]


def list_subscribers_full(db_path: str) -> list[tuple]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT chat_id, username, first_name, bible_version, created_at
            FROM subscribers
            ORDER BY created_at ASC
            """
        ).fetchall()
    return rows
