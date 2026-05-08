import json
from datetime import datetime

from devotional_service import (
    BIBLE_VERSE_COUNTS_PATH,
    extract_from_json,
    generate_youversion_link,
    load_bible_verse_counts,
)


def test_extract_from_json_formats_structured_entry_with_version_links(tmp_path) -> None:
    json_path = tmp_path / "devotionals.json"
    payload = {
        "devotionals": {
            "2026-03-17": {
                "header": "March 17",
                "date_topic": "Faithful",
                "verses": "John 3:16",
                "body": "Line one\nLine two",
                "prayer": "Help me trust You.",
            }
        }
    }
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    rendered = extract_from_json(str(json_path), datetime(2026, 3, 17), version_id=59)

    assert "Scripture" in rendered
    assert "ESV" in rendered
    assert "https://www.bible.com/bible/59/" in rendered
    assert "Prayer" in rendered


def test_generate_youversion_link_splits_multi_chapter_passages() -> None:
    links = generate_youversion_link("1 Samuel 3-5", version_id=59)

    assert links == [
        "[1 Samuel 3](https://www.bible.com/bible/59/1SA.3)",
        "[1 Samuel 4](https://www.bible.com/bible/59/1SA.4)",
        "[1 Samuel 5](https://www.bible.com/bible/59/1SA.5)",
    ]


def test_generate_youversion_link_splits_cross_chapter_verse_ranges() -> None:
    load_bible_verse_counts.cache_clear()
    links = generate_youversion_link("John 11:45-12:11", version_id=59)

    assert links == [
        "[John 11:45\\-57](https://www.bible.com/bible/59/JHN.11.45-57)",
        "[John 12:1\\-11](https://www.bible.com/bible/59/JHN.12.1-11)",
    ]


def test_generate_youversion_link_falls_back_when_verse_counts_missing(
    monkeypatch, tmp_path
) -> None:
    missing_counts_path = tmp_path / "missing-bible.json"
    monkeypatch.setattr("devotional_service.BIBLE_VERSE_COUNTS_PATH", missing_counts_path)
    load_bible_verse_counts.cache_clear()

    links = generate_youversion_link("John 11:45-12:11", version_id=59)

    assert links == [
        "[John 11:45\\-end](https://www.bible.com/bible/59/JHN.11.45)",
        "[John 12:1\\-11](https://www.bible.com/bible/59/JHN.12.1-11)",
    ]

    monkeypatch.setattr("devotional_service.BIBLE_VERSE_COUNTS_PATH", BIBLE_VERSE_COUNTS_PATH)
    load_bible_verse_counts.cache_clear()
