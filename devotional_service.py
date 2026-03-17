import json
import os
import re
from datetime import datetime
from functools import lru_cache

import fitz

from bot_constants import BIBLE_MAP, VERSION_ID_TO_CODE
from bot_formatting import escape_markdown_v2, md_link


@lru_cache(maxsize=4)
def load_pdf_text(pdf_path: str, mtime: float) -> str:
    if not os.path.exists(pdf_path):
        return ""

    pages = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            pages.append(page.get_text() or "")

    return "\n\n".join(pages)


def generate_youversion_link(passage_string: str, version_id: int = 111):
    parts = passage_string.split(" ", 1)
    book_name = parts[0]
    reference = parts[1] if len(parts) > 1 else ""

    abbr = BIBLE_MAP.get(book_name, book_name[:3].upper())

    if reference and ":" not in reference and "-" in reference:
        start_end = reference.split("-", 1)
        if len(start_end) == 2 and start_end[0].isdigit() and start_end[1].isdigit():
            start = int(start_end[0])
            end = int(start_end[1])
            links = []
            for chapter in range(start, end + 1):
                url = f"https://www.bible.com/bible/{version_id}/{abbr}.{chapter}"
                links.append(md_link(f"{book_name} {chapter}", url))
            return links

    clean_ref = reference.replace(":", ".") if reference else ""
    url = f"https://www.bible.com/bible/{version_id}/{abbr}"
    if clean_ref:
        url += f".{clean_ref}"
    return md_link(passage_string, url)


def generate_verse_links(verses: str, version_id: int) -> str:
    links = []
    for verse in [value.strip() for value in verses.split(",") if value.strip()]:
        link = generate_youversion_link(verse, version_id=version_id)
        if isinstance(link, list):
            links.extend(link)
        else:
            links.append(link)
    return ", ".join(links)


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
    del target_date
    json_path = cfg.get("json_path")
    if not json_path or not os.path.exists(json_path):
        return escape_markdown_v2(
            "Devotional JSON not found. Please upload or set DEVOTIONAL_JSON."
        )
    return escape_markdown_v2("Devotional not found for today.")


@lru_cache(maxsize=2)
def load_devotionals_json(json_path: str, mtime: float) -> dict:
    del mtime
    if not os.path.exists(json_path):
        return {}
    try:
        with open(json_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("devotionals", {})
    except (json.JSONDecodeError, OSError):
        return {}


def extract_from_json(json_path: str, target_date: datetime, version_id: int) -> str:
    if not os.path.exists(json_path):
        return ""
    devotionals = load_devotionals_json(json_path, os.path.getmtime(json_path))
    key_iso = target_date.strftime("%Y-%m-%d")
    key_dmy = target_date.strftime("%d-%m-%Y")
    entry = devotionals.get(key_iso) or devotionals.get(key_dmy)
    if not entry:
        return ""
    if isinstance(entry, str):
        return entry
    return format_devotional_entry(entry, target_date, version_id)


def format_devotional_entry(entry: dict, target_date: datetime, version_id: int) -> str:
    parts = []

    day_word = "Today"
    now = datetime.now(target_date.tzinfo) if target_date.tzinfo else datetime.now()
    if target_date.date() < now.date():
        day_word = "Yesterday"
    elif target_date.date() > now.date():
        day_word = "Tomorrow"

    top_line = f"🗓️ {day_word}'s Devotional - {target_date.strftime('%b %d, %Y (%a)')}"
    parts.append(f"*{escape_markdown_v2(top_line)}*")

    header = entry.get("header")
    if header:
        parts.append(f"*{escape_markdown_v2(str(header).strip())}*")

    date_topic = entry.get("date_topic")
    if date_topic:
        parts.append(f"*{escape_markdown_v2(str(date_topic).strip())}*")

    verses = entry.get("verses")
    if verses:
        version_code = VERSION_ID_TO_CODE[version_id]
        parts.append(
            f"*{escape_markdown_v2(f'📖 Scripture ({version_code})')}*\n\n"
            f"{generate_verse_links(verses, version_id)}"
        )

    body = entry.get("body")
    if body:
        cleaned_body = re.sub(r"(?<!\n)\n(?!\n)", "", str(body).strip())
        parts.append(escape_markdown_v2(cleaned_body))

    prayer = entry.get("prayer")
    if prayer:
        parts.append(
            f"*{escape_markdown_v2('🙏🏼 Prayer')}*\n\n{escape_markdown_v2(prayer)}"
        )

    return "\n\n".join(parts).strip()
