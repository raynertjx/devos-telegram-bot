# Devos Telegram Bot (Base Template)

Base Python template for a Telegram bot that sends a daily devotional extracted from a PDF.

## Setup

1. Create a `.env` file from `.env.example` and fill in values.
2. Install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Run:

```bash
python main.py
```

## Notes

- The PDF extraction is intentionally minimal. Update `extract_devotional_for_date` in `main.py` to match the PDF's structure.
- The bot uses polling, scheduled with `run_daily` in the configured `TIMEZONE`.
- Users subscribe by messaging `/start`, and can unsubscribe with `/stop`.
- `ADMIN_IDS` is a comma-separated list of numeric Telegram user IDs allowed to use `/broadcast`.
- `CHAT_ID` is optional (fallback target if no subscribers exist).
- The message is sent in `<pre>` HTML to preserve line breaks and spacing.
- Use `/today` to test the current day's devotional immediately.
