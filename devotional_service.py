import json
import os
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

try:
    import fitz
except ImportError:  # pragma: no cover - optional in test environments
    fitz = None

from bot_constants import BIBLE_MAP, VERSION_ID_TO_CODE
from bot_formatting import escape_markdown_v2, md_link


BIBLE_VERSE_COUNTS_PATH = Path(__file__).resolve().parent / "data" / "bible.json"


@lru_cache(maxsize=4)
def load_pdf_text(pdf_path: str, mtime: float) -> str:
    if fitz is None:
        return ""

    if not os.path.exists(pdf_path):
        return ""

    pages = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            pages.append(page.get_text() or "")

    return "\n\n".join(pages)


def _split_book_and_reference(passage_string: str) -> tuple[str, str]:
    for book_name in sorted(BIBLE_MAP, key=len, reverse=True):
        if passage_string == book_name:
            return book_name, ""
        if passage_string.startswith(f"{book_name} "):
            return book_name, passage_string[len(book_name) + 1 :].strip()

    parts = passage_string.split(" ", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def _build_youversion_url(abbr: str, version_id: int, reference: str = "") -> str:
    url = f"https://www.bible.com/bible/{version_id}/{abbr}"
    if reference:
        url += f".{reference.replace(':', '.')}"
    return url


@lru_cache(maxsize=1)
def load_bible_verse_counts() -> dict[str, dict[int, int]]:
    if not BIBLE_VERSE_COUNTS_PATH.exists():
        return {}

    try:
        with BIBLE_VERSE_COUNTS_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}

    verse_counts: dict[str, dict[int, int]] = {}
    if not isinstance(payload, list):
        return verse_counts

    for book_entry in payload:
        if not isinstance(book_entry, dict):
            continue

        book_name = book_entry.get("book")
        chapters = book_entry.get("chapters")
        if not isinstance(book_name, str) or not isinstance(chapters, list):
            continue

        chapter_counts: dict[int, int] = {}
        for chapter_entry in chapters:
            if not isinstance(chapter_entry, dict):
                continue
            try:
                chapter = int(chapter_entry["chapter"])
                verses = int(chapter_entry["verses"])
            except (KeyError, TypeError, ValueError):
                continue
            chapter_counts[chapter] = verses

        if chapter_counts:
            verse_counts[book_name] = chapter_counts

    return verse_counts


def _chapter_verse_count(book_name: str, chapter: int) -> int | None:
    return load_bible_verse_counts().get(book_name, {}).get(chapter)


def generate_youversion_link(passage_string: str, version_id: int = 111):
    book_name, reference = _split_book_and_reference(passage_string.strip())

    abbr = BIBLE_MAP.get(book_name, book_name[:3].upper())

    chapter_range_match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", reference)
    if chapter_range_match:
        start = int(chapter_range_match.group(1))
        end = int(chapter_range_match.group(2))
        if start <= end:
            return [
                md_link(
                    f"{book_name} {chapter}",
                    _build_youversion_url(abbr, version_id, str(chapter)),
                )
                for chapter in range(start, end + 1)
            ]

    cross_chapter_match = re.fullmatch(
        r"(\d+):(\d+)\s*-\s*(\d+):(\d+)", reference
    )
    if cross_chapter_match:
        start_chapter = int(cross_chapter_match.group(1))
        start_verse = int(cross_chapter_match.group(2))
        end_chapter = int(cross_chapter_match.group(3))
        end_verse = int(cross_chapter_match.group(4))

        if start_chapter < end_chapter:
            start_chapter_last_verse = _chapter_verse_count(book_name, start_chapter)
            if start_chapter_last_verse is None:
                links = [
                    md_link(
                        f"{book_name} {start_chapter}:{start_verse}-end",
                        _build_youversion_url(
                            abbr, version_id, f"{start_chapter}:{start_verse}"
                        ),
                    )
                ]
            else:
                links = [
                    md_link(
                        f"{book_name} {start_chapter}:{start_verse}-{start_chapter_last_verse}",
                        _build_youversion_url(
                            abbr,
                            version_id,
                            f"{start_chapter}:{start_verse}-{start_chapter_last_verse}",
                        ),
                    )
                ]
            for chapter in range(start_chapter + 1, end_chapter):
                links.append(
                    md_link(
                        f"{book_name} {chapter}",
                        _build_youversion_url(abbr, version_id, str(chapter)),
                    )
                )
            links.append(
                md_link(
                    f"{book_name} {end_chapter}:1-{end_verse}",
                    _build_youversion_url(
                        abbr, version_id, f"{end_chapter}:1-{end_verse}"
                    ),
                )
            )
            return links

    return md_link(passage_string, _build_youversion_url(abbr, version_id, reference))


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
