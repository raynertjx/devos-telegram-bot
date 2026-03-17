import os
from datetime import time as dtime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from bot_constants import LOG_GROUP_ID


def load_config() -> dict:
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    feedback_url = os.getenv("FEEDBACK_URL")
    pdf_path = os.getenv("DEVOTIONAL_PDF", "./bible-in-a-year-2026-volume-1-2.pdf")
    json_path = os.getenv("DEVOTIONAL_JSON", "./devotionals.json")
    send_time = os.getenv("SEND_TIME", "07:00")
    timezone = os.getenv("TIMEZONE", "Asia/Singapore")
    admin_ids_raw = os.getenv("ADMIN_IDS", "349988134")
    log_group_id = int(os.getenv("LOG_GROUP_ID", str(LOG_GROUP_ID)))

    if not token:
        raise RuntimeError("BOT_TOKEN is required")

    hour, minute = [int(part) for part in send_time.split(":", 1)]
    admin_ids = {
        int(part.strip())
        for part in admin_ids_raw.split(",")
        if part.strip().isdigit()
    }
    tz = ZoneInfo(timezone)
    send_time_aware = dtime(hour=hour, minute=minute, tzinfo=tz)

    return {
        "token": token,
        "chat_id": int(chat_id) if chat_id else None,
        "pdf_path": pdf_path,
        "feedback_url": feedback_url,
        "json_path": json_path,
        "send_time": send_time_aware,
        "timezone": timezone,
        "admin_ids": admin_ids,
        "db_path": os.getenv("SUBSCRIBERS_DB", "./subscribers.sqlite3"),
        "log_group_id": log_group_id,
    }
