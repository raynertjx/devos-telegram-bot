from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot_constants import DISCLAIMER_TEXT, LOG_CHAT_ID
from bot_handlers import (
    bible,
    bible_callback,
    broadcast,
    disclaimer,
    feedback,
    help_command,
    send_devotional,
    subscribe,
    subscribers,
    today,
    tomorrow,
    unknown_command,
    unsubscribe,
    yesterday,
)
from db import get_bible_version, init_db, list_subscribers, set_bible_version, upsert_subscriber


class FixedDatetime:
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 3, 17, 7, 0, tzinfo=tz)


@pytest.fixture
def seeded_cfg(tmp_path, make_cfg, write_devotionals):
    cfg = make_cfg(tmp_path)
    init_db(cfg["db_path"])
    write_devotionals(cfg["json_path"])
    return cfg


def test_subscribe_inserts_subscriber_and_sends_welcome_flow(
    seeded_cfg, make_user, make_message, make_context, run_async
) -> None:
    message = make_message()
    user = make_user(1, "tester", "Tester")
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_user=user,
        _effective_user=user,
        message=message,
    )
    context = make_context(seeded_cfg)

    with patch("bot_handlers.today", new=AsyncMock()) as today_mock:
        run_async(subscribe(update, context))

    assert list_subscribers(seeded_cfg["db_path"]) == [123]
    assert message.reply_text.await_count == 2
    today_mock.assert_awaited_once()


def test_subscribe_existing_subscriber_returns_already_subscribed_message(
    seeded_cfg, make_user, make_message, make_seed_update, make_context, run_async
) -> None:
    user = make_user(1, "tester", "Tester")
    upsert_subscriber(seeded_cfg["db_path"], make_seed_update(123, user), bible_version=111)

    message = make_message()
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_user=user,
        _effective_user=user,
        message=message,
    )

    run_async(subscribe(update, make_context(seeded_cfg)))

    assert message.reply_text.await_count == 1
    assert "already subscribed" in message.reply_text.await_args.args[0]


@pytest.mark.parametrize(
    ("handler", "target_string"),
    [
        (today, "Today"),
        (yesterday, "Yesterday"),
        (tomorrow, "Tomorrow"),
    ],
)
def test_date_commands_send_expected_devotional(
    handler,
    target_string,
    seeded_cfg,
    make_user,
    make_message,
    make_seed_update,
    make_context,
    run_async,
) -> None:
    user = make_user(1, "tester", "Tester")
    upsert_subscriber(seeded_cfg["db_path"], make_seed_update(123, user), bible_version=111)

    message = make_message()
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_user=user,
        message=message,
    )

    with patch("bot_handlers.datetime", FixedDatetime):
        run_async(handler(update, make_context(seeded_cfg)))

    assert message.reply_text.await_count >= 1
    assert target_string in message.reply_text.await_args.kwargs["text"]


def test_unsubscribe_removes_existing_subscriber(
    seeded_cfg, make_user, make_seed_update, make_message, make_context, run_async
) -> None:
    user = make_user(1, "tester", "Tester")
    upsert_subscriber(seeded_cfg["db_path"], make_seed_update(123, user), bible_version=111)

    message = make_message()
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=123), message=message)

    run_async(unsubscribe(update, make_context(seeded_cfg)))

    assert list_subscribers(seeded_cfg["db_path"]) == []
    assert "Unsubscribed" in message.reply_text.await_args.args[0]


def test_unsubscribe_non_subscriber_returns_message(
    seeded_cfg, make_message, make_context, run_async
) -> None:
    message = make_message()
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=999), message=message)

    run_async(unsubscribe(update, make_context(seeded_cfg)))

    assert "not subscribed" in message.reply_text.await_args.args[0]


def test_unknown_command_returns_help_text(seeded_cfg, make_message, run_async) -> None:
    message = make_message()
    update = SimpleNamespace(effective_message=message, message=message)

    run_async(unknown_command(update, None))

    assert "/today" in message.reply_text.await_args.kwargs["text"]
    assert "/unsubscribe" in message.reply_text.await_args.kwargs["text"]


def test_bible_without_args_shows_keyboard(
    seeded_cfg, make_user, make_message, make_context, run_async
) -> None:
    message = make_message()
    user = make_user(1, "tester", "Tester")
    update = SimpleNamespace(
        effective_message=message,
        effective_user=user,
        _effective_user=user,
    )
    context = make_context(seeded_cfg, args=[])

    run_async(bible(update, context))

    args = message.reply_text.await_args.args
    kwargs = message.reply_text.await_args.kwargs
    assert "preferred Bible version" in args[0]
    assert kwargs["reply_markup"] is not None


def test_bible_with_invalid_arg_returns_options(
    seeded_cfg, make_user, make_message, make_context, run_async
) -> None:
    message = make_message()
    user = make_user(1, "tester", "Tester")
    update = SimpleNamespace(
        effective_message=message,
        effective_user=user,
        _effective_user=user,
    )
    context = make_context(seeded_cfg, args=["bad"])

    run_async(bible(update, context))

    assert "Unknown version. Options:" in message.reply_text.await_args.args[0]


def test_bible_with_valid_arg_updates_subscriber_version(
    seeded_cfg, make_user, make_message, make_seed_update, make_context, run_async
) -> None:
    user = make_user(1, "tester", "Tester")
    upsert_subscriber(seeded_cfg["db_path"], make_seed_update(123, user), bible_version=111)

    message = make_message()
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_message=message,
        effective_user=user,
        _effective_user=user,
    )
    context = make_context(seeded_cfg, args=["esv"])

    run_async(bible(update, context))

    assert get_bible_version(seeded_cfg["db_path"], 123) == 59
    message.reply_text.assert_awaited_once_with("Bible version set to ESV!")


def test_bible_callback_updates_subscriber_version(
    seeded_cfg, make_user, make_seed_update, make_context, run_async
) -> None:
    user = make_user(1, "tester", "Tester")
    upsert_subscriber(seeded_cfg["db_path"], make_seed_update(123, user), bible_version=111)

    query = SimpleNamespace(
        data="bible:ESV",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(chat=SimpleNamespace(id=123)),
    )
    update = SimpleNamespace(callback_query=query)

    run_async(bible_callback(update, make_context(seeded_cfg)))

    assert get_bible_version(seeded_cfg["db_path"], 123) == 59
    query.edit_message_text.assert_awaited_once_with("Bible version set to ESV.")


def test_help_command_inserts_subscriber_and_replies(
    seeded_cfg, make_user, make_message, make_context, run_async
) -> None:
    user = make_user(1, "tester", "Tester")
    message = make_message()
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_user=user,
        _effective_user=user,
        message=message,
    )

    run_async(help_command(update, make_context(seeded_cfg)))

    assert list_subscribers(seeded_cfg["db_path"]) == [123]
    assert "/bible" in message.reply_text.await_args.kwargs["text"]


def test_disclaimer_inserts_subscriber_and_replies(
    seeded_cfg, make_user, make_message, make_context, run_async
) -> None:
    user = make_user(1, "tester", "Tester")
    message = make_message()
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_user=user,
        _effective_user=user,
        message=message,
    )

    run_async(disclaimer(update, make_context(seeded_cfg)))

    assert list_subscribers(seeded_cfg["db_path"]) == [123]
    assert message.reply_text.await_args.kwargs["text"] == DISCLAIMER_TEXT


def test_feedback_without_args_returns_usage(
    seeded_cfg, make_user, make_message, make_context, run_async
) -> None:
    message = make_message()
    update = SimpleNamespace(effective_user=make_user(1, "tester", "Tester"), message=message)
    context = make_context(seeded_cfg, args=[])

    run_async(feedback(update, context))

    assert "Please include your feedback" in message.reply_text.await_args.args[0]


def test_feedback_without_url_returns_offline(
    seeded_cfg, make_user, make_message, make_context, run_async
) -> None:
    message = make_message()
    update = SimpleNamespace(effective_user=make_user(1, "tester", "Tester"), message=message)
    context = make_context(seeded_cfg, args=["hello"])

    run_async(feedback(update, context))

    assert "offline" in message.reply_text.await_args.args[0]


def test_feedback_success_posts_and_logs(
    tmp_path, make_cfg, make_user, make_message, make_context, run_async
) -> None:
    cfg = make_cfg(tmp_path, feedback_url="https://example.com/feedback")
    init_db(cfg["db_path"])
    message = make_message()
    bot = SimpleNamespace(send_message=AsyncMock())
    context = make_context(cfg, args=["great", "bot"], bot=bot)
    update = SimpleNamespace(
        effective_user=make_user(1, "tester", "Tester"),
        message=message,
    )

    client = AsyncMock()
    client.post.return_value = SimpleNamespace(status_code=200)
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False

    with patch("bot_handlers.httpx.AsyncClient", return_value=client):
        run_async(feedback(update, context))

    assert "Thank you for your feedback" in message.reply_text.await_args.args[0]
    assert bot.send_message.await_args.kwargs["chat_id"] == LOG_CHAT_ID


def test_broadcast_unauthorized_returns_message(
    seeded_cfg, make_message, make_context, run_async
) -> None:
    message = make_message()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=message)

    run_async(broadcast(update, make_context(seeded_cfg, args=["hello"])))

    message.reply_text.assert_awaited_once_with("Unauthorized.")


def test_broadcast_without_args_returns_usage(
    tmp_path, make_cfg, make_message, make_context, run_async
) -> None:
    cfg = make_cfg(tmp_path, admin_ids={99})
    init_db(cfg["db_path"])
    message = make_message()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=99), message=message)

    run_async(broadcast(update, make_context(cfg, args=[])))

    message.reply_text.assert_awaited_once_with("Usage: /broadcast <message>")


def test_broadcast_sends_to_all_subscribers_for_admin(
    tmp_path, make_cfg, make_user, make_seed_update, make_message, make_context, run_async
) -> None:
    cfg = make_cfg(tmp_path, admin_ids={99})
    init_db(cfg["db_path"])
    upsert_subscriber(cfg["db_path"], make_seed_update(111, make_user(1, "one", "One")), bible_version=111)
    upsert_subscriber(cfg["db_path"], make_seed_update(222, make_user(2, "two", "Two")), bible_version=111)

    message = make_message()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=99), message=message)
    bot = SimpleNamespace(send_message=AsyncMock())
    context = make_context(cfg, args=["Hello", "subscribers"], bot=bot)

    run_async(broadcast(update, context))

    sent_chat_ids = [call.kwargs["chat_id"] for call in bot.send_message.await_args_list]
    assert sent_chat_ids == [111, 222]
    message.reply_text.assert_awaited_once_with("Broadcast sent to 2 subscribers.")


def test_subscribers_unauthorized_returns_message(
    seeded_cfg, make_message, make_context, run_async
) -> None:
    message = make_message()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_message=message)

    run_async(subscribers(update, make_context(seeded_cfg)))

    message.reply_text.assert_awaited_once_with("Unauthorized.")


def test_subscribers_admin_sends_table(
    tmp_path, make_cfg, make_user, make_seed_update, make_context, run_async
) -> None:
    cfg = make_cfg(tmp_path, admin_ids={99})
    init_db(cfg["db_path"])
    upsert_subscriber(cfg["db_path"], make_seed_update(111, make_user(1, "one", "One")), bible_version=111)
    bot = SimpleNamespace(send_message=AsyncMock())
    context = make_context(cfg, bot=bot)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=99),
        effective_message=SimpleNamespace(chat=SimpleNamespace(id=999)),
    )

    run_async(subscribers(update, context))

    assert bot.send_message.await_count >= 1
    sent_text = bot.send_message.await_args_list[0].kwargs["text"]
    assert "TOTAL SUBSCRIBERS" in sent_text


def test_send_devotional_uses_stored_bible_version(
    seeded_cfg, make_user, make_seed_update, make_context, run_async
) -> None:
    user = make_user(1, "tester", "Tester")
    upsert_subscriber(seeded_cfg["db_path"], make_seed_update(123, user), bible_version=111)
    set_bible_version(seeded_cfg["db_path"], 123, 59)

    bot = SimpleNamespace(send_message=AsyncMock())
    context = make_context(seeded_cfg, bot=bot)

    with patch("bot_handlers.datetime", FixedDatetime):
        run_async(send_devotional(context))

    assert bot.send_message.await_count >= 1
    sent_text = bot.send_message.await_args.kwargs["text"]
    assert "https://www.bible.com/bible/59/" in sent_text
