"""Telegram update handling, kept separate from startup and storage.

This module owns the logic for turning a Telegram `Message` into something we
can save. It handles text now but already records a `message_type` for photos,
videos, documents, etc., so those can be expanded later without reshaping the
database.
"""

import logging
import asyncio
from tempfile import TemporaryDirectory

from telegram import Message, Update
from telegram.ext import ContextTypes

from database import StoredMessage
from database import MessageDatabase
from x_publisher import XPublisher
from health import HealthState

LOGGER = logging.getLogger(__name__)


def detect_message_type(message: Message) -> str:
    if message.text:
        return "text"
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.document:
        return "document"
    if message.audio:
        return "audio"
    if message.voice:
        return "voice"
    if message.sticker:
        return "sticker"
    if message.animation:
        return "animation"
    return "other"


def sender_details(message: Message) -> tuple[int | None, str | None, str]:
    """Return (user_id, username, full name), handling anonymous admins too."""
    if message.from_user:
        user = message.from_user
        return user.id, user.username, user.full_name
    # Anonymous admin posts / channel-originated posts use sender_chat.
    if message.sender_chat:
        sender = message.sender_chat
        return None, sender.username, sender.title or sender.full_name
    return None, None, "Unknown sender"


def build_stored_message(message: Message) -> StoredMessage:
    user_id, username, name = sender_details(message)
    return StoredMessage(
        message_id=message.message_id,
        chat_id=message.chat_id,
        sender_user_id=user_id,
        sender_username=username,
        sender_name=name,
        message_text=message.text or message.caption,
        message_type=detect_message_type(message),
        sent_at=message.date.isoformat(),
    )


def create_message_handler(
    allowed_chat_id: int | None, publisher: XPublisher, health: HealthState,
    database: MessageDatabase,
):
    async def handle_message(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = update.effective_message
        if message is None:
            return

        if allowed_chat_id is not None and message.chat_id != allowed_chat_id:
            LOGGER.warning(
                "Ignored message %s from unexpected chat %s",
                message.message_id,
                message.chat_id,
            )
            return

        stored = build_stored_message(message)
        if not database.save(stored):
            LOGGER.info("Ignoring duplicate Telegram message %s", message.message_id)
            return
        print(
            "\n--- Telegram message ---\n"
            f"message_id: {stored.message_id}\n"
            f"chat_id: {stored.chat_id}\n"
            f"sender_id: {stored.sender_user_id}\n"
            f"sender_username: {stored.sender_username or '-'}\n"
            f"sender_name: {stored.sender_name}\n"
            f"type: {stored.message_type}\n"
            f"date: {stored.sent_at}\n"
            f"text: {stored.message_text or '[no text]'}\n"
            "-------------------------",
            flush=True,
        )

        try:
            if message.photo:
                with TemporaryDirectory(prefix="telegram-x-") as temp_dir:
                    photo = message.photo[-1]
                    telegram_file = await context.bot.get_file(photo.file_id)
                    image_path = f"{temp_dir}/photo.jpg"
                    await telegram_file.download_to_drive(image_path)
                    result = await asyncio.to_thread(
                        publisher.post, stored.message_text or "", image_path
                    )
            else:
                result = await asyncio.to_thread(
                    publisher.post, stored.message_text or ""
                )

            if result.get("ok"):
                database.mark_posted(stored, result["url"])
                LOGGER.info("Posted to X: %s", result["url"])
                health.update(
                    "running", last_post_url=result["url"],
                    telegram_message_id=message.message_id,
                )
            else:
                database.mark_failed(stored, str(result.get("error", result)))
                LOGGER.error("X rejected the post: %s", result.get("error", result))
                health.update(
                    "post_failed", error=result.get("error", str(result)),
                    telegram_message_id=message.message_id,
                )
        except Exception:
            database.mark_failed(stored, "Unexpected X publishing error")
            LOGGER.exception(
                "Could not post Telegram message %s to X", message.message_id
            )
            health.update("post_failed", error="Unexpected X publishing error")

    return handle_message


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log any error the library surfaces instead of crashing the loop."""
    LOGGER.error("Update failed: update=%r error=%s", update, context.error)
