import json
import os
import re
from datetime import datetime, date
from functools import lru_cache
from typing import Optional
import fitz

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
DATE_TOPIC_RE = re.compile(r"^\d{1,2}\s+[A-Za-z]+\s*:.*$")
VERSE_RE = re.compile(r"[A-Za-z]+\s+\d")
HEADER_FOOTER_RE = re.compile(r"^BIBLE IN A YEAR DEVOTIONAL", re.IGNORECASE)


@lru_cache(maxsize=4)
def load_pdf_text(pdf_path: str, mtime: float) -> list[list[str]]:
    if not os.path.exists(pdf_path):
        return ""

    pages = []

    with fitz.open(pdf_path) as doc:
        for page_idx, page in enumerate(doc[6: 96]):
            text = page.get_text() or ""
            paragraphs = page.get_text("blocks")
            split_paragraphs = []
            for paragraph_idx, paragraph in enumerate(paragraphs):
                # The text content is the 5th element in the tuple (index 4)
                paragraph_text = paragraph[4].strip()
                if paragraph_text:
                    # skip header note, which is i == 1
                    if paragraph_idx == 1:
                        continue

                    split_paragraphs.append(paragraph_text)
        
            pages.append(split_paragraphs)
                    
    return pages


def categorize_paragraphs(paragraphs: list[str]) -> dict:
    header = None
    date_topic = None
    date_topic_lines = 0
    date_topic_needs_next = False
    verses = None
    prayer = None
    prayer_pending = False
    body_parts: list[str] = []

    cleaned = [p.strip() for p in paragraphs if p and p.strip()]
    for para in cleaned:
        if para.startswith("PRAYER:"):
            prayer_pending = True
            if para != "PRAYER:":
                prayer = para
                prayer_pending = False
            continue

        if prayer_pending:
            prayer = para
            prayer_pending = False
            continue

        if date_topic is None and DATE_TOPIC_RE.match(para):
            date_topic = para
            date_topic_lines = 1
            date_topic_needs_next = para.rstrip().endswith(":")
            continue

        if date_topic is not None and date_topic_lines < 3 and verses is None:
            # Allow up to 3 lines for the date/topic before verses begin.
            if date_topic_needs_next:
                # Force-capture the next line as topic if date line ends with ":"
                date_topic = f"{date_topic}\n{para}"
                date_topic_lines += 1
                date_topic_needs_next = False
                continue
            if not VERSE_RE.search(para):
                date_topic = f"{date_topic}\n{para}"
                date_topic_lines += 1
                continue

        if verses is None and VERSE_RE.search(para) and ("," in para or ":" in para):
            if HEADER_FOOTER_RE.search(para):
                continue
            verses = para
            continue

        if header is None and para.isupper():
            header = para
            continue

        body_parts.append(para)

    body = "\n\n".join(body_parts).strip() if body_parts else None
    if body:
        body = re.sub(r"(?<!\n)\n(?!\n)", " ", body).strip()

    if prayer:
        prayer = re.sub(r"\s*\n\s*", " ", prayer).strip()

    return {
        "header": header,
        "date_topic": date_topic,
        "verses": verses,
        "body": body,
        "prayer": prayer,
    }


def split_entries(pages: list[list[str]]) -> list[tuple[str, str]]:
    entries = []
    for page in pages:
        categorised_dict = categorize_paragraphs(page)
        entries.append(categorised_dict)

    return entries


def parse_header_date(header: str, default_year: int) -> Optional[datetime]:
    if not header:
        return None
    normalized = header.strip().replace("\n", " ")
    if not normalized:
        return None

    month_map = {m.upper(): m for m in MONTHS}

    m = re.match(
        r"^(?P<day>\d{1,2})\s+(?P<month>[A-Z]+)(?:,?\s*(?P<year>\d{4}))?:?.*$",
        normalized.upper(),
    )
    if not m:
        m = re.match(
            r"^(?P<month>[A-Z]+)\s+(?P<day>\d{1,2})(?:,?\s*(?P<year>\d{4}))?.*$",
            normalized.upper(),
        )
    if not m:
        return None

    month_key = m.group("month")
    month = month_map.get(month_key)
    if not month:
        return None

    try:
        day = int(m.group("day"))
    except (TypeError, ValueError):
        return None

    year = default_year
    year_raw = m.group("year")
    if year_raw:
        try:
            year = int(year_raw)
        except ValueError:
            year = default_year

    try:
        return datetime.strptime(f"{month} {day} {year}", "%B %d %Y")
    except ValueError:
        return None


def load_existing_meta(json_path: str) -> dict:
    if not os.path.exists(json_path):
        return {}
    try:
        with open(json_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data.get("_meta", {})
    except (json.JSONDecodeError, OSError):
        return {}

def build_json(pdf_path: str, json_path: str, default_year: int) -> None:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    mtime = os.path.getmtime(pdf_path)
    meta = load_existing_meta(json_path)

    combined = load_pdf_text(pdf_path, mtime)
    if not combined:
        raise RuntimeError("PDF appears empty or unreadable.")

    entries = split_entries(combined)
    devotionals: dict[str, str] = {}
    skipped = 0
    skipped_dates = []

    for devo_dict in entries:
        parsed_date = parse_header_date(devo_dict["date_topic"], default_year=default_year)
        if not parsed_date:
            skipped += 1
            skipped_dates.append(devo_dict["date_topic"])
            continue
        cutoff = datetime(2026, 2, 22).date()
        if parsed_date.date() < cutoff:
            continue
        parsed_date_string = parsed_date.strftime('%d-%m-%Y')
        devotionals[parsed_date_string] = devo_dict

    payload = {
        "_meta": {
            "source_pdf": pdf_path,
            "source_mtime": mtime,
            "default_year": default_year,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "entries": len(devotionals),
            "skipped": skipped,
        },
        "devotionals": devotionals,
    }

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    print(f"Wrote {len(devotionals)} entries to {json_path} (skipped {skipped}).")


def main() -> None:
    pdf_path = os.getenv("DEVOTIONAL_PDF", "./bible-in-a-year-2026-volume-1-2.pdf")
    json_path = os.getenv("DEVOTIONAL_JSON", "./devotionals.json")
    default_year = int(os.getenv("DEVOTIONAL_YEAR", "2026"))
    build_json(pdf_path=pdf_path, json_path=json_path, default_year=default_year)


if __name__ == "__main__":
    main()
