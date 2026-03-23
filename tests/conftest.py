import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def run_async():
    def _run(coro):
        return asyncio.run(coro)

    return _run


@pytest.fixture
def make_cfg():
    def _make_cfg(tmp_path, **overrides):
        cfg = {
            "db_path": str(tmp_path / "subscribers.sqlite3"),
            "json_path": str(tmp_path / "devotionals.json"),
            "timezone": "Asia/Singapore",
            "chat_id": None,
            "feedback_url": None,
            "admin_ids": set(),
            "send_time": None,
            "log_group_id": -5250672666,
        }
        cfg.update(overrides)
        return cfg

    return _make_cfg


@pytest.fixture
def make_user():
    def _make_user(user_id: int, username: str, first_name: str):
        return SimpleNamespace(id=user_id, username=username, first_name=first_name)

    return _make_user


@pytest.fixture
def make_seed_update():
    def _make_seed_update(chat_id: int, user):
        return SimpleNamespace(
            effective_chat=SimpleNamespace(id=chat_id),
            effective_user=user,
            _effective_user=user,
        )

    return _make_seed_update


@pytest.fixture
def make_message():
    def _make_message():
        return SimpleNamespace(reply_text=AsyncMock())

    return _make_message


@pytest.fixture
def make_context():
    def _make_context(cfg, **overrides):
        context = SimpleNamespace(
            args=[],
            application=SimpleNamespace(bot_data={"cfg": cfg}),
            bot=SimpleNamespace(send_message=AsyncMock()),
        )
        for key, value in overrides.items():
            setattr(context, key, value)
        return context

    return _make_context


@pytest.fixture
def write_devotionals():
    def _write_devotionals(json_path, payload=None):
        if payload is None:
            payload = {
                "devotionals": {
                    "2026-03-16": {
                        "header": "March 16",
                        "date_topic": "Yesterday",
                        "verses": "John 3:16",
                        "body": "Yesterday body",
                        "prayer": "Yesterday prayer.",
                    },
                    "2026-03-17": {
                        "header": "March 17",
                        "date_topic": "Today",
                        "verses": "John 3:16",
                        "body": "Today body",
                        "prayer": "Today prayer.",
                    },
                    "2026-03-18": {
                        "header": "March 18",
                        "date_topic": "Tomorrow",
                        "verses": "John 3:16",
                        "body": "Tomorrow body",
                        "prayer": "Tomorrow prayer.",
                    },
                }
            }
        Path(json_path).write_text(json.dumps(payload), encoding="utf-8")

    return _write_devotionals
