import json
from datetime import datetime

from devotional_service import extract_from_json


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
