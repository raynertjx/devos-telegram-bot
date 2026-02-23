import sqlite3
from datetime import datetime

from telegram import Update


def init_db(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                bible_version INTEGER DEFAULT 111,
                created_at TEXT
            )
            """
        )
        # Migrate existing text values to integer IDs
        conn.execute(
            """
            UPDATE subscribers
            SET bible_version = CASE bible_version
                WHEN 'NIV' THEN 111
                WHEN 'ESV' THEN 59
                WHEN 'KJV' THEN 1
                WHEN 'NKJV' THEN 114
                WHEN 'NASB' THEN 100
                WHEN 'NLT' THEN 116
                WHEN 'AMP' THEN 1588
                ELSE bible_version
            END
            WHERE bible_version IN ('NIV','ESV','KJV','NKJV','NASB','NLT','AMP')
            """
        )
        conn.commit()


def upsert_subscriber(db_path: str, update: Update, bible_version: int = 111) -> None:
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
                bible_version,
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


def list_subscribers_with_versions(db_path: str) -> list[tuple[int, int]]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT chat_id, COALESCE(bible_version, 111) FROM subscribers"
        ).fetchall()
    return [(int(row[0]), int(row[1])) for row in rows]


def get_bible_version(db_path: str, chat_id: int) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT COALESCE(bible_version, 111) FROM subscribers WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
    return int(row[0]) if row else 111


def set_bible_version(db_path: str, chat_id: int, bible_version: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE subscribers SET bible_version = ? WHERE chat_id = ?",
            (bible_version, chat_id),
        )
        conn.commit()


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
