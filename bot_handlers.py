import traceback
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot_constants import BIBLE_VERSIONS, DISCLAIMER_TEXT, LOG_CHAT_ID, TO_IGNORE_CHAT_IDS
from bot_formatting import escape_markdown_v2, format_subscribers_table, to_markdown
from db import (
    get_bible_version,
    list_subscribers,
    list_subscribers_due_for_time,
    list_subscribers_full,
    list_subscribers_with_versions,
    mark_subscriber_sent,
    remove_subscriber,
    set_bible_version,
    upsert_subscriber,
)
from devotional_service import chunk_text, extract_devotional_for_date, extract_from_json


def is_admin(cfg: dict, update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in cfg["admin_ids"])


def seconds_until_next_ten_minute_boundary(now: datetime) -> float:
    next_boundary = now.replace(second=0, microsecond=0)
    minutes_to_add = 10 - (next_boundary.minute % 10)
    if minutes_to_add == 10 and now.second == 0 and now.microsecond == 0:
        minutes_to_add = 0
    next_boundary = next_boundary + timedelta(minutes=minutes_to_add)
    return max((next_boundary - now).total_seconds(), 0.0)


async def send_devotional_to_chat(
    context: ContextTypes.DEFAULT_TYPE, cfg: dict, chat_id: int, version_id: int, now: datetime
) -> None:
    text = extract_from_json(cfg["json_path"], now, version_id)
    if not text:
        text = extract_devotional_for_date(cfg, now)

    for chunk in chunk_text(text):
        await context.bot.send_message(
            chat_id=chat_id,
            text=to_markdown(chunk),
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )


async def send_devotional(context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    now = datetime.now(ZoneInfo(cfg["timezone"]))
    target_date = now.date().isoformat()
    preferred_send_time = now.strftime("%H:%M")
    subscribers = list_subscribers_due_for_time(
        cfg["db_path"], preferred_send_time, target_date
    )
    if (
        not subscribers
        and cfg["chat_id"]
        and preferred_send_time == cfg["send_time"].strftime("%H:%M")
    ):
        subscribers = [(cfg["chat_id"], 111)]

    for chat_id, version_id in subscribers:
        if chat_id in TO_IGNORE_CHAT_IDS:
            continue
        try:
            await send_devotional_to_chat(context, cfg, chat_id, version_id, now)
            mark_subscriber_sent(cfg["db_path"], chat_id, target_date)
        except Exception as exc:
            print(f"[send_devotional] Failed to send to chat_id={chat_id}: {exc}")
            traceback.print_exc()


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    chat = update.effective_chat
    already = False
    if chat:
        already = chat.id in list_subscribers(cfg["db_path"])
    if already:
        await update.message.reply_text(
            "You're already subscribed\\! You will receieve the daily devotionals every morning at *0700hrs \\(SGT\\)*\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    upsert_subscriber(cfg["db_path"], update, bible_version=111)
    await update.message.reply_text(
        text=DISCLAIMER_TEXT,
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True,
    )

    user_first_name = update._effective_user.first_name
    welcome_text = (
        f"Hello {user_first_name}, you're subscribed\\! ✨\n\n"
        "You'll receive daily devotionals here from "
        "Lighthouse Evangelism's *Bible In A Year* "
        "every morning at *0700hrs \\(SGT\\)*\\.\n\n"
        "Here are some commands to get started:\n"
        "\\- /today \\- get today's material\n"
        "\\- /yesterday \\- get yesterday's material\n"
        "\\- /tomorrow \\- get tomorrow's material\n"
        "\\- /bible \\- change bible version\n"
        "\\- /unsubscribe \\- unsubscribe from daily devotionals\n\n"
        "Here's today's devotional to get you started\\. God bless\\! 🙏\n"
    )
    await update.message.reply_text(text=welcome_text, parse_mode="MarkdownV2")
    await today(update, context)


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    removed = remove_subscriber(cfg["db_path"], update)
    if removed:
        await update.message.reply_text(
            "Unsubscribed\\. You will no longer receive the daily devotionals\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    await update.message.reply_text(
        "You're not subscribed\\.", parse_mode=ParseMode.MARKDOWN_V2
    )


async def send_devotional_for_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE, target_date: datetime
) -> None:
    cfg = context.application.bot_data["cfg"]
    chat = update.effective_chat
    version_id = get_bible_version(cfg["db_path"], chat.id) if chat else 111
    text = extract_from_json(cfg["json_path"], target_date, version_id)
    if not text:
        text = extract_devotional_for_date(cfg, target_date)

    for chunk in chunk_text(text):
        await update.message.reply_text(
            text=to_markdown(chunk),
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    await send_devotional_for_date(
        update, context, datetime.now(ZoneInfo(cfg["timezone"]))
    )


async def yesterday(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    await send_devotional_for_date(
        update, context, datetime.now(ZoneInfo(cfg["timezone"])) - timedelta(days=1)
    )


async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    await send_devotional_for_date(
        update, context, datetime.now(ZoneInfo(cfg["timezone"])) + timedelta(days=1)
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    message = update.effective_message
    if not message:
        return
    text = (
        "Sorry\\, I don't understand that command\\. Try these commands instead\\:\\\n\n"
        "\\- /today \\- get today's material\n"
        "\\- /yesterday \\- get yesterday's material\n"
        "\\- /tomorrow \\- get tomorrow's material\n"
        "\\- /bible \\- change bible version\n"
        "\\- /subscribe \\- start receiving daily devotionals\n"
        "\\- /unsubscribe \\- stop receiving daily devotionals"
    )
    await update.message.reply_text(text=text, parse_mode="MarkdownV2")


async def bible(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    user_first_name = update._effective_user.first_name
    cfg = context.application.bot_data["cfg"]
    if not context.args:
        rows = [
            [InlineKeyboardButton(code, callback_data=f"bible:{code}")]
            for code in sorted(BIBLE_VERSIONS.keys())
        ]
        await message.reply_text(
            f"Hello {user_first_name}! Please select your preferred Bible version from the list below:",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    choice = context.args[0].upper()
    if choice not in BIBLE_VERSIONS:
        await message.reply_text(
            f"Unknown version. Options: {', '.join(sorted(BIBLE_VERSIONS.keys()))}",
        )
        return

    chat = update.effective_chat
    if not chat:
        return
    set_bible_version(cfg["db_path"], chat.id, BIBLE_VERSIONS[choice])
    await message.reply_text(f"Bible version set to {choice}!")


async def bible_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    if not data.startswith("bible:"):
        return
    choice = data.split(":", 1)[1].upper()
    if choice not in BIBLE_VERSIONS:
        await query.edit_message_text("Unknown version.")
        return
    chat = query.message.chat if query.message else None
    if not chat:
        return
    cfg = context.application.bot_data["cfg"]
    set_bible_version(cfg["db_path"], chat.id, BIBLE_VERSIONS[choice])
    await query.edit_message_text(f"Bible version set to {choice}.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    upsert_subscriber(cfg["db_path"], update, bible_version=111)
    user_first_name = update._effective_user.first_name
    text = (
        f"Hello {user_first_name}, here are some commands to get you started:\\\n\n"
        "\\- /today \\- get today's material\n"
        "\\- /yesterday \\- get yesterday's material\n"
        "\\- /tomorrow \\- get tomorrow's material\n"
        "\\- /bible \\- change bible version\n"
        "\\- /subscribe \\- start receiving daily devotionals\n"
        "\\- /unsubscribe \\- stop receiving daily devotionals"
    )
    await update.message.reply_text(text=text, parse_mode="MarkdownV2")


async def disclaimer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    upsert_subscriber(cfg["db_path"], update, bible_version=111)
    await update.message.reply_text(text=DISCLAIMER_TEXT, parse_mode="MarkdownV2")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    if not is_admin(cfg, update):
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    message = " ".join(context.args)
    sent = 0
    for chat_id in list_subscribers(cfg["db_path"]):
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                disable_web_page_preview=True,
            )
            sent += 1
        except Exception:
            continue
    await update.message.reply_text(f"Broadcast sent to {sent} subscribers.")


async def send_subscriber_list_to_chat(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int
) -> None:
    cfg = context.application.bot_data["cfg"]
    rows = list_subscribers_full(cfg["db_path"])
    if not rows:
        await context.bot.send_message(
            chat_id=chat_id,
            text=escape_markdown_v2("No subscribers."),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    for chunk in format_subscribers_table(rows):
        await context.bot.send_message(
            chat_id=chat_id,
            text=chunk,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )


async def subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(context.application.bot_data["cfg"], update):
        message = update.effective_message
        if message:
            await message.reply_text("Unauthorized.")
        return
    message = update.effective_message
    if not message:
        return
    await send_subscriber_list_to_chat(context, message.chat.id)


async def send_logs(context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_subscriber_list_to_chat(context, LOG_CHAT_ID)


async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    user = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "Please include your feedback after the command\\.\nExample: `/feedback This bot is great\\!`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if not cfg.get("feedback_url"):
        await update.message.reply_text(
            "Feedback system is currently offline\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    async with httpx.AsyncClient() as client:
        payload = {
            "chat_id": user.id,
            "username": f"@{user.username}" if user.username else user.first_name,
            "message": " ".join(context.args),
        }
        try:
            response = await client.post(
                cfg["feedback_url"], json=payload, follow_redirects=True
            )
            if response.status_code == 200:
                await update.message.reply_text(
                    "Thank you for your feedback\\! The developer will take a look at it\\. 😄",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                log_message = (
                    "📩 **New Feedback\\!**\n"
                    f"From: {user.first_name} \\(@{user.username}\\)\n"
                    f"ID: `{user.id}`\n\n"
                    f"Message: {' '.join(context.args)}"
                )
                await context.bot.send_message(
                    chat_id=LOG_CHAT_ID,
                    text=log_message,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            else:
                await update.message.reply_text(
                    "Failed to send feedback\\. Please try again later\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
        except Exception:
            traceback.print_exc()
            await update.message.reply_text(
                "An error occurred while sending feedback\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("yesterday", yesterday))
    app.add_handler(CommandHandler("tomorrow", tomorrow))
    app.add_handler(CommandHandler("bible", bible))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("start", subscribe))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))
    app.add_handler(CallbackQueryHandler(bible_callback, pattern=r"^bible:"))
    app.add_handler(CommandHandler("feedback", feedback))
    app.add_handler(CommandHandler("disclaimer", disclaimer))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("subscribers", subscribers))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))


def register_jobs(app: Application, cfg: dict) -> None:
    tz = ZoneInfo(cfg["timezone"])
    first_run_in_seconds = seconds_until_next_ten_minute_boundary(datetime.now(tz))
    app.job_queue.run_repeating(
        send_devotional,
        interval=600,
        first=first_run_in_seconds,
        name="daily-devotional",
    )
    for idx, run_time in enumerate(
        (
            dtime(hour=8, minute=0, tzinfo=tz),
            dtime(hour=14, minute=0, tzinfo=tz),
            dtime(hour=20, minute=0, tzinfo=tz),
        ),
        start=1,
    ):
        app.job_queue.run_daily(
            send_logs,
            time=run_time,
            days=(0, 1, 2, 3, 4, 5, 6),
            name=f"subscriber-logs-{idx}",
        )
