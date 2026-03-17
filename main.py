from telegram.ext import Application

from bot_config import load_config
from bot_handlers import register_handlers, register_jobs
from db import init_db


def main() -> None:
    cfg = load_config()
    init_db(cfg["db_path"])

    app = Application.builder().token(cfg["token"]).build()
    app.bot_data["cfg"] = cfg

    register_handlers(app)
    register_jobs(app, cfg)

    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
