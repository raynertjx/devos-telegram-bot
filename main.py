import json
import os
import re
from datetime import datetime, time as dtime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import fitz
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
from db import (
    init_db,
    list_subscribers,
    list_subscribers_full,
    remove_subscriber,
    upsert_subscriber,
)

DISCLAIMER_TEXT = (
    "⚠️ *DISCLAIMER*\n\n"
    "Hi\\, I'm *Rayner*\\! I created this Telegram bot to make accessing these "
    "daily devotionals more convenient for everyone\\.\n\n"
    "The content is referenced from the digital PDF available on the "
    "*Lighthouse Evangelism* "
    "[website](https://lighthouse\\.org\\.sg/devotional\\-volume\\-1/)\\. "
    "Please note that I have *not modified* the devotional content in any way whatsoever\\.\n\n"
    "If you have any feedback or find any issues with the bot\\, feel free to reach out to me directly "
    "at @raynertjx\\. I'd love to hear from you\\!\n\n"
    "_This bot is a personal project and is not an official publication of Lighthouse Evangelism\\._"
)

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

BIBLE_MAP = {
    # Old Testament
    "Genesis": "GEN", "Exodus": "EXO", "Leviticus": "LEV", "Numbers": "NUM",
    "Deuteronomy": "DEU", "Joshua": "JOS", "Judges": "JDG", "Ruth": "RUT",
    "1 Samuel": "1SA", "2 Samuel": "2SA", "1 Kings": "1KI", "2 Kings": "2KI",
    "1 Chronicles": "1CH", "2 Chronicles": "2CH", "Ezra": "EZR", "Nehemiah": "NEH",
    "Esther": "EST", "Job": "JOB", "Psalms": "PSA", "Psalm": "PSA",
    "Proverbs": "PRO", "Ecclesiastes": "ECC", "Song of Solomon": "SNG",
    "Song of Songs": "SNG", "Isaiah": "ISA", "Jeremiah": "JER",
    "Lamentations": "LAM", "Ezekiel": "EZK", "Daniel": "DAN", "Hosea": "HOS",
    "Joel": "JOL", "Amos": "AMO", "Obadiah": "OBA", "Jonah": "JON",
    "Micah": "MIC", "Nahum": "NAM", "Habakkuk": "HAB", "Zephaniah": "ZEP",
    "Haggai": "HAG", "Zechariah": "ZEC", "Malachi": "MAL",

    # New Testament
    "Matthew": "MAT", "Mark": "MRK", "Luke": "LUK", "John": "JHN",
    "Acts": "ACT", "Romans": "ROM", "1 Corinthians": "1CO", "2 Corinthians": "2CO",
    "Galatians": "GAL", "Ephesians": "EPH", "Philippians": "PHP", "Colossians": "COL",
    "1 Thessalonians": "1TH", "2 Thessalonians": "2TH", "1 Timothy": "1TI",
    "2 Timothy": "2TI", "Titus": "TIT", "Philemon": "PHM", "Hebrews": "HEB",
    "James": "JAS", "1 Peter": "1PE", "2 Peter": "2PE", "1 John": "1JN",
    "2 John": "2JN", "3 John": "3JN", "Jude": "JUD", "Revelation": "REV"
}

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

def escape_md_url(url: str) -> str:
    return url.replace("\\", "\\\\").replace(")", "\\)")

def md_link(text: str, url: str) -> str:
    return f"[{escape_markdown_v2(text)}]({escape_md_url(url)})"

def generate_youversion_link(passage_string, version_id=111):
    parts = passage_string.split(" ", 1)
    book_name = parts[0]
    reference = parts[1] if len(parts) > 1 else ""

    abbr = BIBLE_MAP.get(book_name, book_name[:3].upper())

    # Split pure chapter range like "12-13" into separate links
    if reference and ":" not in reference and "-" in reference:
        start_end = reference.split("-", 1)
        if len(start_end) == 2 and start_end[0].isdigit() and start_end[1].isdigit():
            start = int(start_end[0])
            end = int(start_end[1])
            links = []
            for chapter in range(start, end + 1):
                url = f"https://www.bible.com/bible/{version_id}/{abbr}.{chapter}"
                label = f"{book_name} {chapter}"
                links.append(md_link(label, url))
            return links

    clean_ref = reference.replace(":", ".") if reference else ""
    url = f"https://www.bible.com/bible/{version_id}/{abbr}" + (f".{clean_ref}" if clean_ref else "")
    return md_link(passage_string, url)


def generate_verse_links(verses):
    split_verses = [v.strip() for v in verses.split(",") if v.strip()]
    links = []
    for v in split_verses:
        link = generate_youversion_link(v)
        if isinstance(link, list):
            links.extend(link)
        else:
            links.append(link)
    return ", ".join(links)


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


def extract_devotional_for_date(cfg: dict, target_date: datetime) -> str:
    json_path = cfg.get("json_path")
    if not json_path or not os.path.exists(json_path):
        return escape_markdown_v2(
            "Devotional JSON not found. Please upload or set DEVOTIONAL_JSON."
        )

    text = extract_from_json(json_path, target_date)
    return text or escape_markdown_v2("Devotional not found for today.")


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
    key_iso = target_date.strftime("%Y-%m-%d")
    key_dmy = target_date.strftime("%d-%m-%Y")
    entry = devotionals.get(key_iso) or devotionals.get(key_dmy)
    if not entry:
        return ""
    if isinstance(entry, str):
        return entry
    return format_devotional_entry(entry, target_date)


def format_devotional_entry(entry: dict, target_date: datetime) -> str:
    parts = []

    day_word = "Today"
    now = datetime.now(target_date.tzinfo) if target_date.tzinfo else datetime.now()
    if target_date.date() < now.date():
        day_word = "Yesterday"
    elif target_date.date() > now.date():
        day_word = "Tomorrow"

    formatted_date_string = target_date.strftime("%b %d, %Y (%a)")
    top_line = f"🗓️ {day_word}'s Devotional - {formatted_date_string}"
    parts.append(f"*{escape_markdown_v2(top_line)}*")

    header = entry.get("header")
    if header:
        parts.append(f"*{escape_markdown_v2(str(header).strip())}*")

    date_topic = entry.get("date_topic")
    if date_topic:
        parts.append(f"*{escape_markdown_v2(str(date_topic).strip())}*")

    verses = entry.get("verses")
    if verses:
        verses_string = generate_verse_links(verses)
        parts.append(f"*{escape_markdown_v2('📖 Scripture')}*\n\n{verses_string}")

    body = entry.get("body")
    if body:
        parts.append(escape_markdown_v2(str(body).strip()))

    prayer = entry.get("prayer")
    if prayer:
        parts.append(f"*{escape_markdown_v2('🙏🏼 Prayer')}*\n\n{escape_markdown_v2(str(prayer).strip())}")

    return "\n\n".join(parts).strip()


def escape_markdown_v2(text: str) -> str:
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", text)


def to_markdown(text: str) -> str:
    return text




def is_admin(cfg: dict, update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in cfg["admin_ids"])


async def send_devotional(context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.now(tz)
    text = extract_from_json(cfg["json_path"], now)
    if not text:
        text = extract_devotional_for_date(cfg, now)

    chat_ids = list_subscribers(cfg["db_path"])
    if not chat_ids and cfg["chat_id"]:
        chat_ids = [cfg["chat_id"]]

    for chat_id in chat_ids:
        for chunk in chunk_text(text):
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=to_markdown(chunk),
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=True,
                )
            except Exception:
                continue


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    upsert_subscriber(cfg["db_path"], update)
    user_first_name = update._effective_user.first_name
    welcome_text = (
        f"Hello {user_first_name}, you're subscribed\\! ✨\n\n"
        f"You'll receive daily devotionals here from "
        f"Lighthouse Evangelism's *Bible In A Year* "
        f"every morning at *0700hrs \\(SGT\\)*\\.\n\n"
        f"Here are some commands to get started:\n"
        f"\\- /today \\- get today's material\n"
        f"\\- /yesterday \\- get yesterday's material\n"
        f"\\- /tomorrow \\- get tomorrow's material\n"
        f"\\- /bible \\- change bible version\n"
        f"\\- /unsubscribe \\- unsubscribe from daily devotionals\n\n"
        f"God bless\\! 🙏\n"
    )

    await update.message.reply_text(text=welcome_text, parse_mode='MarkdownV2')
    await update.message.reply_text(
        text=DISCLAIMER_TEXT,
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True
    )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    removed = remove_subscriber(cfg["db_path"], update)
    if removed:
        await update.message.reply_text(
            "Unsubscribed\\. You will no longer receive the daily devotionals\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            "You're not subscribed\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.now(tz)
    text = extract_from_json(cfg["json_path"], now)
    if not text:
        text = extract_devotional_for_date(cfg, now)

    for chunk in chunk_text(text):
        await update.message.reply_text(
            text=to_markdown(chunk),
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )

async def yesterday(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    tz = ZoneInfo(cfg["timezone"])
    yesterday_date = datetime.now(tz) - timedelta(days=1)
    text = extract_from_json(cfg["json_path"], yesterday_date)
    if not text:
        text = extract_devotional_for_date(cfg, yesterday_date)

    for chunk in chunk_text(text):
        await update.message.reply_text(
            text=to_markdown(chunk),
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )

        
async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    tz = ZoneInfo(cfg["timezone"])
    tomorrow_date = datetime.now(tz) + timedelta(days=1)
    text = extract_from_json(cfg["json_path"], tomorrow_date)
    if not text:
        text = extract_devotional_for_date(cfg, tomorrow_date)

    for chunk in chunk_text(text):
        await update.message.reply_text(
            text=to_markdown(chunk),
            parse_mode=ParseMode.MARKDOWN_V2,
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


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    upsert_subscriber(cfg["db_path"], update)
    user_first_name = update._effective_user.first_name
    text = (
        f"Hello {user_first_name}, here are some commands to get you started:\\\n\n"
        f"\\- /today \\- get today's material\n"
        f"\\- /yesterday \\- get yesterday's material\n"
        f"\\- /tomorrow \\- get tomorrow's material\n"
        f"\\- /bible \\- change bible version\n"
        f"\\- /subscribe \\- start receiving daily devotionals\n"
        f"\\- /unsubscribe \\- stop receiving daily devotionals"
    )
    await update.message.reply_text(text=text, parse_mode='MarkdownV2')


async def disclaimer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    upsert_subscriber(cfg["db_path"], update)
    await update.message.reply_text(text=DISCLAIMER_TEXT, parse_mode='MarkdownV2')


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    if not is_admin(cfg, update):
        await update.message.reply_text("Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    message = " ".join(context.args)
    chat_ids = list_subscribers(cfg["db_path"])
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


async def subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    if not is_admin(cfg, update):
        message = update.effective_message
        if message:
            await message.reply_text("Unauthorized.")
        return

    rows = list_subscribers_full(cfg["db_path"])
    if not rows:
        message = update.effective_message
        if message:
            await message.reply_text("No subscribers.")
        return

    lines = []
    for chat_id, username, first_name, bible_version, created_at in rows:
        handle = f"@{username}" if username else "-"
        line = f"{chat_id} | {handle} | {first_name} | {bible_version} | {created_at}"
        lines.append(escape_markdown_v2(line))

    text = "*Subscribers*\n" + "\n".join(lines)
    message = update.effective_message
    if not message:
        return
    for chunk in chunk_text(text, max_len=3500):
        await message.reply_text(
            text=chunk,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )


def main() -> None:
    cfg = load_config()
    init_db(cfg["db_path"])

    app = Application.builder().token(cfg["token"]).build()
    app.bot_data["cfg"] = cfg

    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("yesterday", yesterday))
    app.add_handler(CommandHandler("tomorrow", tomorrow))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CommandHandler("disclaimer", disclaimer))
    # app.add_handler(CommandHandler("whoami", whoami))

    # admin functions
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("subscribers", subscribers))

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
