import re

from wcwidth import wcswidth

from bot_constants import VERSION_ID_TO_CODE


def escape_markdown_v2(text: str) -> str:
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", text)


def escape_md_url(url: str) -> str:
    return url.replace("\\", "\\\\").replace(")", "\\)")


def md_link(text: str, url: str) -> str:
    return f"[{escape_markdown_v2(text)}]({escape_md_url(url)})"


def to_markdown(text: str) -> str:
    return text


def display_width(text: str) -> int:
    width = wcswidth(text)
    return width if width >= 0 else len(text)


def truncate(text: str, max_width: int) -> str:
    if display_width(text) <= max_width:
        return text
    if max_width <= 1:
        return text[:max_width]
    out = []
    width = 0
    for ch in text:
        ch_width = display_width(ch)
        if width + ch_width >= max_width:
            break
        out.append(ch)
        width += ch_width
    return "".join(out) + "…"


def format_subscribers_table(rows: list[tuple]) -> list[str]:
    headers = ["Chat ID", "Username", "Name", "Bible Version", "Preferred Time"]
    data = []
    for row in rows:
        if len(row) == 6:
            cid, username, first_name, bible_version, preferred_send_time, _created_at = row
        elif len(row) == 5:
            cid, username, first_name, bible_version, _created_at = row
            preferred_send_time = "07:00"
        else:
            raise ValueError(
                f"Unsupported subscriber row shape: expected 5 or 6 columns, got {len(row)}"
            )
        handle = f"@{username}" if username else "-"
        version_code = VERSION_ID_TO_CODE.get(int(bible_version), str(bible_version))
        name = first_name or "-"
        data.append(
            [
                str(cid),
                truncate(handle, 16),
                truncate(name, 16),
                truncate(version_code, 14),
                str(preferred_send_time or "07:00"),
            ]
        )

    widths = [
        max(
            display_width(headers[index]),
            max((display_width(row[index]) for row in data), default=0),
        )
        for index in range(len(headers))
    ]

    def fmt_row(columns: list[str]) -> str:
        padded = []
        for index, column in enumerate(columns):
            pad = widths[index] - display_width(column)
            padded.append(column + (" " * max(pad, 0)))
        return " | ".join(padded)

    lines = [fmt_row(headers), "-+-".join("-" * width for width in widths)]
    lines.extend(fmt_row(row) for row in data)

    total = f"*TOTAL SUBSCRIBERS:* `{len(rows)}`\n"
    chunks = []
    current = [total, "```", lines[0], lines[1]]
    current_len = sum(len(line) + 1 for line in current)

    for line in lines[2:]:
        if current_len + len(line) + 4 > 3500:
            current.append("```")
            chunks.append("\n".join(current))
            current = [total, "```", lines[0], lines[1], line]
            current_len = sum(len(item) + 1 for item in current)
        else:
            current.append(line)
            current_len += len(line) + 1

    current.append("```")
    chunks.append("\n".join(current))
    return chunks
