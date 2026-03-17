import sqlite3
from datetime import datetime

from telegram import Update

DEFAULT_PREFERRED_SEND_TIME = "07:00"


def init_db(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                bible_version INTEGER DEFAULT 111,
                preferred_send_time TEXT NOT NULL DEFAULT '07:00',
                last_sent_date TEXT,
                created_at TEXT
            )
            """
        )
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(subscribers)").fetchall()
        }
        if "preferred_send_time" not in columns:
            conn.execute(
                f"""
                ALTER TABLE subscribers
                ADD COLUMN preferred_send_time TEXT NOT NULL
                DEFAULT '{DEFAULT_PREFERRED_SEND_TIME}'
                """
            )
        if "last_sent_date" not in columns:
            conn.execute(
                """
                ALTER TABLE subscribers
                ADD COLUMN last_sent_date TEXT
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


def list_subscribers_due_for_time(
    db_path: str, preferred_send_time: str, target_date: str
) -> list[tuple[int, int]]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                chat_id,
                COALESCE(bible_version, 111)
            FROM subscribers
            WHERE COALESCE(preferred_send_time, ?) = ?
              AND COALESCE(last_sent_date, '') != ?
            """,
            (DEFAULT_PREFERRED_SEND_TIME, preferred_send_time, target_date),
        ).fetchall()
    return [(int(row[0]), int(row[1])) for row in rows]


def get_bible_version(db_path: str, chat_id: int) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT COALESCE(bible_version, 111) FROM subscribers WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
    return int(row[0]) if row else 111


def get_preferred_send_time(db_path: str, chat_id: int) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT COALESCE(preferred_send_time, ?)
            FROM subscribers
            WHERE chat_id = ?
            """,
            (DEFAULT_PREFERRED_SEND_TIME, chat_id),
        ).fetchone()
    return str(row[0]) if row else DEFAULT_PREFERRED_SEND_TIME


def set_bible_version(db_path: str, chat_id: int, bible_version: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE subscribers SET bible_version = ? WHERE chat_id = ?",
            (bible_version, chat_id),
        )
        conn.commit()


def set_preferred_send_time(db_path: str, chat_id: int, preferred_send_time: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE subscribers SET preferred_send_time = ? WHERE chat_id = ?",
            (preferred_send_time, chat_id),
        )
        conn.commit()


def mark_subscriber_sent(db_path: str, chat_id: int, target_date: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE subscribers SET last_sent_date = ? WHERE chat_id = ?",
            (target_date, chat_id),
        )
        conn.commit()


def list_subscribers_full(db_path: str) -> list[tuple]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                chat_id,
                username,
                first_name,
                bible_version,
                COALESCE(preferred_send_time, '07:00'),
                created_at
            FROM subscribers
            ORDER BY created_at ASC
            """
        ).fetchall()
    return rows
