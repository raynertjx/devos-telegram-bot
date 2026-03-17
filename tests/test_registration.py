import asyncio
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler

from bot_handlers import (
    register_handlers,
    register_jobs,
    seconds_until_next_ten_minute_boundary,
)


def build_application() -> Application:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return Application.builder().token("123:TEST").build()


def test_register_handlers_wires_expected_commands_and_callbacks() -> None:
    app = build_application()

    register_handlers(app)

    handlers = app.handlers[0]

    command_names = sorted(
        next(iter(handler.commands))
        for handler in handlers
        if isinstance(handler, CommandHandler)
    )
    assert command_names == sorted(
        [
            "today",
            "yesterday",
            "tomorrow",
            "bible",
            "time",
            "subscribe",
            "start",
            "unsubscribe",
            "feedback",
            "disclaimer",
            "help",
            "broadcast",
            "subscribers",
        ]
    )

    callback_handlers = [
        handler for handler in handlers if isinstance(handler, CallbackQueryHandler)
    ]
    assert sorted(handler.pattern.pattern for handler in callback_handlers) == [
        "^bible:",
        "^time(?:hours|:)",
        "^timehour:",
    ]

    message_handlers = [
        handler for handler in handlers if isinstance(handler, MessageHandler)
    ]
    assert len(message_handlers) == 1


def test_register_jobs_wires_daily_devotional_and_log_jobs() -> None:
    app = build_application()
    cfg = {
        "send_time": dtime(hour=7, minute=0, tzinfo=ZoneInfo("Asia/Singapore")),
        "timezone": "Asia/Singapore",
    }

    register_jobs(app, cfg)

    job_names = sorted(job.name for job in app.job_queue.jobs())
    assert job_names == [
        "daily-devotional",
        "subscriber-logs-1",
        "subscriber-logs-2",
        "subscriber-logs-3",
    ]


def test_seconds_until_next_ten_minute_boundary_from_offset_time() -> None:
    now = datetime(2026, 3, 17, 7, 3, 15)

    assert seconds_until_next_ten_minute_boundary(now) == 405.0


def test_seconds_until_next_ten_minute_boundary_from_exact_boundary() -> None:
    now = datetime(2026, 3, 17, 7, 10, 0)

    assert seconds_until_next_ten_minute_boundary(now) == 0.0
