"""Entry point: start the Telegram message collector.

Run with:
    ./.venv/bin/python main.py

It long-polls the Telegram Bot API and prints every new group message.
"""

import logging

from telegram.ext import Application, MessageHandler, filters

from collector import create_message_handler, handle_error
from config import load_settings
from x_publisher import XPublisher
from health import HealthState
from database import MessageDatabase


def main() -> int:
    settings = load_settings()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    application = Application.builder().token(settings.bot_token).build()
    publisher = XPublisher(settings.x_session_path)
    health = HealthState(settings.health_path)
    database = MessageDatabase(settings.database_path)
    database.initialize()
    health.update("running", x_user_id=publisher.user_id)
    logging.info("X session ready for user ID %s", publisher.user_id or "unknown")

    # Handle every message (text now; photos/videos/documents structured later).
    application.add_handler(
        MessageHandler(
            filters.TEXT | filters.PHOTO,
            create_message_handler(settings.chat_id, publisher, health, database),
        )
    )
    application.add_error_handler(handle_error)

    logging.info("Starting long-poll...")
    # Telegram expects update type names here, not MessageHandler filters.
    application.run_polling(allowed_updates=["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
