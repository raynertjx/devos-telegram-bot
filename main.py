import html
import json
import os
import re
import sqlite3
from datetime import datetime, time as dtime
from functools import lru_cache
from zoneinfo import ZoneInfo

import fitz
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

DATE_RE = re.compile(
    rf"^(?:{'|'.join(MONTHS)})\s+\d{{1,2}}(?:,\s*\d{{4}})?",
    re.MULTILINE,
)


def load_config() -> dict:
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    pdf_path = os.getenv("DEVOTIONAL_PDF", "./bible-in-a-year-2026-volume-1-2.pdf")
    json_path = os.getenv("DEVOTIONAL_JSON", "./devotionals.json")
    send_time = os.getenv("SEND_TIME", "07:00")
    timezone = os.getenv("TIMEZONE", "Asia/Singapore")
    admin_ids_raw = os.getenv("ADMIN_IDS", "349988134")

    if not token:
        raise RuntimeError("BOT_TOKEN is required")

    hour, minute = [int(p) for p in send_time.split(":", 1)]
    admin_ids = [
        int(part.strip())
        for part in admin_ids_raw.split(",")
        if part.strip().isdigit()
    ]

    return {
        "token": token,
        "chat_id": int(chat_id) if chat_id else None,
        "pdf_path": pdf_path,
        "json_path": json_path,
        "send_time": dtime(hour=hour, minute=minute),
        "timezone": timezone,
        "admin_ids": set(admin_ids),
        "db_path": os.getenv("SUBSCRIBERS_DB", "./subscribers.sqlite3"),
    }


@lru_cache(maxsize=4)
def load_pdf_text(pdf_path: str, mtime: float) -> str:
    if not os.path.exists(pdf_path):
        return ""

    pages = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text = page.get_text() or ""
            pages.append(text)

    return "\n\n".join(pages)


def split_entries(text: str) -> list[tuple[str, str]]:
    matches = list(DATE_RE.finditer(text))
    if not matches:
        return []

    entries = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        entry = text[start:end].strip()
        header = match.group(0).strip()
        entries.append((header, entry))
    return entries


def find_entry_for_date(entries: list[tuple[str, str]], target_date: datetime) -> str:
    month = target_date.strftime("%B")
    day = target_date.day
    year = target_date.year
    candidates = (
        f"{month} {day}, {year}",
        f"{month} {day}",
    )

    for header, entry in entries:
        for candidate in candidates:
            if header.startswith(candidate):
                return entry
    return ""


def chunk_text(text: str, max_len: int = 3800) -> list[str]:
    if len(text) <= max_len:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n\n", 0, max_len)
        if cut == -1:
            cut = remaining.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].lstrip()
    return chunks


def extract_devotional_for_date(pdf_path: str, target_date: datetime) -> str:
    if not os.path.exists(pdf_path):
        return "Devotional PDF not found. Please upload or set DEVOTIONAL_PDF."

    mtime = os.path.getmtime(pdf_path)
    combined = load_pdf_text(pdf_path, mtime)
    if not combined:
        return "Devotional PDF appears empty or unreadable."

    entries = split_entries(combined)
    entry = find_entry_for_date(entries, target_date)
    return entry or "Devotional not found for today."


@lru_cache(maxsize=2)
def load_devotionals_json(json_path: str, mtime: float) -> dict:
    if not os.path.exists(json_path):
        return {}
    try:
        with open(json_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("devotionals", {})
    except (json.JSONDecodeError, OSError):
        return {}


def extract_from_json(json_path: str, target_date: datetime) -> str:
    if not os.path.exists(json_path):
        return ""
    mtime = os.path.getmtime(json_path)
    devotionals = load_devotionals_json(json_path, mtime)
    key = target_date.strftime("%Y-%m-%d")
    return devotionals.get(key, "")


def to_html_pre(text: str) -> str:
    escaped = html.escape(text)
    return f"<pre>{escaped}</pre>"


def init_db(cfg: dict) -> None:
    with sqlite3.connect(cfg["db_path"]) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                chat_type TEXT,
                created_at TEXT
            )
            """
        )
        conn.commit()


def upsert_subscriber(cfg: dict, update: Update) -> None:
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return
    with sqlite3.connect(cfg["db_path"]) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO subscribers
            (chat_id, username, first_name, last_name, chat_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                chat.id,
                user.username,
                user.first_name,
                user.last_name,
                chat.type,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def remove_subscriber(cfg: dict, update: Update) -> bool:
    chat = update.effective_chat
    if not chat:
        return False
    with sqlite3.connect(cfg["db_path"]) as conn:
        cur = conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat.id,))
        conn.commit()
        return cur.rowcount > 0


def list_subscribers(cfg: dict) -> list[int]:
    with sqlite3.connect(cfg["db_path"]) as conn:
        rows = conn.execute("SELECT chat_id FROM subscribers").fetchall()
    return [row[0] for row in rows]


def is_admin(cfg: dict, update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in cfg["admin_ids"])


async def send_devotional(context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.now(tz)
    text = extract_from_json(cfg["json_path"], now)
    if not text:
        text = extract_devotional_for_date(cfg["pdf_path"], now)

    chat_ids = list_subscribers(cfg)
    if not chat_ids and cfg["chat_id"]:
        chat_ids = [cfg["chat_id"]]

    for chat_id in chat_ids:
        for chunk in chunk_text(text):
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=to_html_pre(chunk),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except Exception:
                continue


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    upsert_subscriber(cfg, update)
    await update.message.reply_text(
        "You're subscribed! You'll receive daily devotionals here from Lighthouse Evangelism's Bible In A Year Devotional, at 0700hrs (SGT)."
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    removed = remove_subscriber(cfg, update)
    if removed:
        await update.message.reply_text("Unsubscribed. You will no longer receive messages.")
    else:
        await update.message.reply_text("You're not subscribed.")


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.now(tz)
    text = extract_from_json(cfg["json_path"], now)
    if not text:
        text = extract_devotional_for_date(cfg["pdf_path"], now)

    for chunk in chunk_text(text):
        await update.message.reply_text(
            text=to_html_pre(chunk),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return
    await update.message.reply_text(
        f"user_id={user.id}\nchat_id={chat.id}\nchat_type={chat.type}"
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    if not is_admin(cfg, update):
        await update.message.reply_text("Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    message = " ".join(context.args)
    chat_ids = list_subscribers(cfg)
    sent = 0
    for chat_id in chat_ids:
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


def main() -> None:
    cfg = load_config()
    init_db(cfg)

    app = Application.builder().token(cfg["token"]).build()
    app.bot_data["cfg"] = cfg

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("broadcast", broadcast))

    tz = ZoneInfo(cfg["timezone"])
    app.job_queue.run_daily(
        send_devotional,
        time=cfg["send_time"],
        days=(0, 1, 2, 3, 4, 5, 6),
        name="daily-devotional",
        # timezone=tz,
    )

    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
