# Devos Telegram Bot

Python Telegram bot that sends daily Bible-in-a-year devotionals. Users can subscribe, choose a preferred Bible version, choose a daily delivery time, request devotionals for today/yesterday/tomorrow, and submit feedback.

The bot runs with long polling via `python-telegram-bot`, stores subscribers in SQLite, reads devotional content from JSON, and can be run locally or through Docker Compose.

## Requirements

- Python 3.11
- Docker and Docker Compose, if running in containers
- A Telegram bot token from [BotFather](https://t.me/BotFather)
- Devotional PDFs in `./pdf/`, or a prebuilt devotional JSON file

## Configuration

Create a `.env` file from the example and fill in your values:

```bash
cp .env.example .env
```

## Local Setup

Create a virtual environment, install dependencies, build the devotional JSON if needed, then run the bot:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python build_devotionals_json.py
python main.py
```

`build_devotionals_json.py` reads all PDFs from `./pdf/` by default and writes the configured `DEVOTIONAL_JSON` file. Use `DEVOTIONAL_PDFS` when you need an explicit PDF order:

```bash
DEVOTIONAL_PDFS=./pdf/volume-1.pdf,./pdf/volume-2.pdf python build_devotionals_json.py
```

## Docker

Build and run the service with Docker Compose:

```bash
docker compose up -d --build
```

View logs:

```bash
docker compose logs -f devos-bot
```

Restart the bot:

```bash
docker compose restart devos-bot
```

Stop the bot:

```bash
docker compose down
```

Run a one-off command inside the container image:

```bash
docker compose run --rm devos-bot python build_devotionals_json.py
```

The Compose file mounts:

- `./pdf:/app/pdf:ro` so PDFs are available read-only inside the container.
- `./data:/app/data` so generated JSON and SQLite data can persist on the host.

## Tests

Install `pytest` with the project dependencies, then run:

```bash
pip install -r requirements.txt pytest
pytest -q
```

The GitHub Actions workflow uses the same test command:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt pytest
pytest -q
```

To run tests inside the Docker image, install `pytest` in that one-off container first because the production image only installs `requirements.txt`:

```bash
docker compose run --rm devos-bot sh -lc "pip install pytest && pytest -q"
```

## Bot Commands

User commands:

- `/start` or `/subscribe`: Subscribe and start onboarding.
- `/unsubscribe`: Stop receiving daily devotionals.
- `/today`: Get today's devotional immediately.
- `/yesterday`: Get yesterday's devotional.
- `/tomorrow`: Get tomorrow's devotional.
- `/bible`: Choose a Bible version from buttons.
- `/bible NIV`: Set a Bible version directly. Other supported values are defined in `bot_constants.py`.
- `/time`: Choose a delivery time from buttons.
- `/time 08:30`: Set a delivery time directly. Times must use `HH:MM` and a 10-minute interval.
- `/feedback Your message`: Send feedback to `FEEDBACK_URL`, if configured.
- `/disclaimer`: Show the disclaimer.
- `/help`: Show the command list.

Admin commands, limited to users in `ADMIN_IDS`:

- `/senddevo DDMMYY`: Send a devotional for a specific date, for example `/senddevo 170326`.
- `/broadcast message`: Send a plain message to all subscribers.
- `/subscribers`: Show the subscriber list.

## Scheduled Jobs

The bot registers two scheduled jobs:

- `daily-devotional`: Runs every 10 minutes and sends devotionals to subscribers whose preferred send time matches the current `HH:MM`. Each subscriber is marked by date to avoid duplicate sends.
- `subscriber-logs-daily`: Runs every day at `08:00` in `TIMEZONE` and sends the subscriber list to `LOG_GROUP_ID`.

## Deployment

The included `deploy.sh` assumes the app is checked out on a server at `/home/ubuntu/devos-telegram-bot`:

```bash
#!/bin/bash
cd /home/ubuntu/devos-telegram-bot
git pull origin main
docker compose up -d --build
```

Make it executable on the server if needed:

```bash
chmod +x deploy.sh
```

## GitHub Actions

The workflow at `.github/workflows/deploy.yml` is named `Remote Update`.

It runs on every push to `main` and has two jobs:

1. `test`
   - Checks out the repository.
   - Sets up Python 3.11.
   - Installs dependencies with `pip install -r requirements.txt pytest`.
   - Runs `pytest -q`.

2. `deploy`
   - Runs only after the `test` job succeeds.
   - Uses `appleboy/ssh-action@master` to SSH into the remote server.
   - Executes `/home/ubuntu/devos-telegram-bot/deploy.sh` on that server.

Required GitHub repository secrets:

- `SSH_HOST`: Remote server hostname or IP address.
- `SSH_USER`: Remote SSH username.
- `SSH_PRIVATE_KEY`: Private key with access to the remote server.

The server must already have Docker, Docker Compose, this repository, and a valid `.env` file in `/home/ubuntu/devos-telegram-bot`.
