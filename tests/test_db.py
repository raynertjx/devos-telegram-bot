import sqlite3

from db import (
    get_bible_version,
    get_preferred_send_time,
    init_db,
    set_bible_version,
    set_preferred_send_time,
)


def test_init_db_migrates_legacy_bible_version_strings(tmp_path) -> None:
    db_path = tmp_path / "subscribers.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE subscribers (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                bible_version TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO subscribers
            (chat_id, username, first_name, bible_version, created_at)
            VALUES (1, 'tester', 'Tester', 'NIV', '2026-03-17T00:00:00')
            """
        )
        conn.commit()

    init_db(str(db_path))

    assert get_bible_version(str(db_path), 1) == 111


def test_set_preferred_send_time_persists_to_db(tmp_path) -> None:
    db_path = tmp_path / "subscribers.sqlite3"
    init_db(str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO subscribers
            (chat_id, username, first_name, bible_version, created_at)
            VALUES (1, 'tester', 'Tester', 111, '2026-03-17T00:00:00')
            """
        )
        conn.commit()

    set_preferred_send_time(str(db_path), 1, "08:30")

    assert get_preferred_send_time(str(db_path), 1) == "08:30"


def test_set_bible_version_persists_to_db(tmp_path) -> None:
    db_path = tmp_path / "subscribers.sqlite3"
    init_db(str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO subscribers
            (chat_id, username, first_name, bible_version, created_at)
            VALUES (1, 'tester', 'Tester', 111, '2026-03-17T00:00:00')
            """
        )
        conn.commit()

    set_bible_version(str(db_path), 1, 59)

    assert get_bible_version(str(db_path), 1) == 59
