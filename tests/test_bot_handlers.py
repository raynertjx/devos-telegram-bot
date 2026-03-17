import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot_handlers import bible_callback, broadcast, send_devotional, subscribe, unsubscribe
from db import get_bible_version, init_db, list_subscribers, set_bible_version, upsert_subscriber


def make_cfg(tmp_path) -> dict:
    return {
        "db_path": str(tmp_path / "subscribers.sqlite3"),
        "json_path": str(tmp_path / "devotionals.json"),
        "timezone": "Asia/Singapore",
        "chat_id": None,
        "feedback_url": None,
        "admin_ids": set(),
        "send_time": None,
    }


def make_user(user_id: int, username: str, first_name: str):
    return SimpleNamespace(id=user_id, username=username, first_name=first_name)


def make_seed_update(chat_id: int, user):
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id),
        effective_user=user,
        _effective_user=user,
    )


def test_subscribe_inserts_subscriber_and_sends_welcome_flow(tmp_path) -> None:
    cfg = make_cfg(tmp_path)
    init_db(cfg["db_path"])

    message = SimpleNamespace(reply_text=AsyncMock())
    user = make_user(1, "tester", "Tester")
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_user=user,
        _effective_user=user,
        message=message,
    )
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"cfg": cfg}))

    with patch("bot_handlers.today", new=AsyncMock()) as today_mock:
        asyncio.run(subscribe(update, context))

    assert list_subscribers(cfg["db_path"]) == [123]
    assert message.reply_text.await_count == 2
    today_mock.assert_awaited_once()


def test_bible_callback_updates_subscriber_version(tmp_path) -> None:
    cfg = make_cfg(tmp_path)
    init_db(cfg["db_path"])
    Path(cfg["json_path"]).write_text("{}", encoding="utf-8")

    user = make_user(1, "tester", "Tester")
    upsert_subscriber(cfg["db_path"], make_seed_update(123, user), bible_version=111)

    query = SimpleNamespace(
        data="bible:ESV",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(chat=SimpleNamespace(id=123)),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"cfg": cfg}))

    asyncio.run(bible_callback(update, context))

    assert get_bible_version(cfg["db_path"], 123) == 59
    query.edit_message_text.assert_awaited_once_with("Bible version set to ESV.")


def test_send_devotional_uses_stored_bible_version(tmp_path) -> None:
    cfg = make_cfg(tmp_path)
    init_db(cfg["db_path"])
    payload = {
        "devotionals": {
            "2026-03-17": {
                "header": "March 17",
                "date_topic": "Faithful",
                "verses": "John 3:16",
                "body": "Body text",
                "prayer": "Amen.",
            }
        }
    }
    Path(cfg["json_path"]).write_text(json.dumps(payload), encoding="utf-8")

    user = make_user(1, "tester", "Tester")
    upsert_subscriber(cfg["db_path"], make_seed_update(123, user), bible_version=111)
    set_bible_version(cfg["db_path"], 123, 59)

    bot = SimpleNamespace(send_message=AsyncMock())
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"cfg": cfg}),
        bot=bot,
    )

    class FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime

            return datetime(2026, 3, 17, 7, 0, tzinfo=tz)

    with patch("bot_handlers.datetime", FixedDatetime):
        asyncio.run(send_devotional(context))

    assert bot.send_message.await_count >= 1
    sent_text = bot.send_message.await_args.kwargs["text"]
    assert "https://www.bible.com/bible/59/" in sent_text


def test_unsubscribe_removes_existing_subscriber(tmp_path) -> None:
    cfg = make_cfg(tmp_path)
    init_db(cfg["db_path"])

    user = make_user(1, "tester", "Tester")
    upsert_subscriber(cfg["db_path"], make_seed_update(123, user), bible_version=111)

    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        message=message,
    )
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"cfg": cfg}))

    asyncio.run(unsubscribe(update, context))

    assert list_subscribers(cfg["db_path"]) == []
    message.reply_text.assert_awaited_once()
    assert "Unsubscribed" in message.reply_text.await_args.args[0]


def test_broadcast_sends_to_all_subscribers_for_admin(tmp_path) -> None:
    cfg = make_cfg(tmp_path)
    cfg["admin_ids"] = {99}
    init_db(cfg["db_path"])

    upsert_subscriber(
        cfg["db_path"], make_seed_update(111, make_user(1, "one", "One")), bible_version=111
    )
    upsert_subscriber(
        cfg["db_path"], make_seed_update(222, make_user(2, "two", "Two")), bible_version=111
    )

    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=99),
        message=message,
    )
    bot = SimpleNamespace(send_message=AsyncMock())
    context = SimpleNamespace(
        args=["Hello", "subscribers"],
        application=SimpleNamespace(bot_data={"cfg": cfg}),
        bot=bot,
    )

    asyncio.run(broadcast(update, context))

    assert bot.send_message.await_count == 2
    sent_chat_ids = [call.kwargs["chat_id"] for call in bot.send_message.await_args_list]
    assert sent_chat_ids == [111, 222]
    message.reply_text.assert_awaited_once_with("Broadcast sent to 2 subscribers.")
