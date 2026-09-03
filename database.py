"""SQLite storage layer.

Uses a `UNIQUE(chat_id, message_id)` constraint plus `INSERT OR IGNORE` so the
same message is never stored twice, even if the program restarts and the bot
re-delivers an update it already saw.
"""

from pathlib import Path
from sqlite3 import connect, Connection
from dataclasses import dataclass


@dataclass(frozen=True)
class StoredMessage:
    message_id: int
    chat_id: int
    sender_user_id: int | None
    sender_username: str | None
    sender_name: str
    message_text: str | None
    message_type: str
    sent_at: str


class MessageDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    sender_user_id INTEGER,
                    sender_username TEXT,
                    sender_name TEXT NOT NULL,
                    message_text TEXT,
                    message_type TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    publish_status TEXT NOT NULL DEFAULT 'pending',
                    publish_url TEXT,
                    last_error TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(chat_id, message_id)
                )
                """
            )
            # Lightweight migration for databases created by older versions.
            columns = {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
            for name, definition in (("publish_status", "TEXT NOT NULL DEFAULT 'pending'"),
                                     ("publish_url", "TEXT"), ("last_error", "TEXT"),
                                     ("attempts", "INTEGER NOT NULL DEFAULT 0")):
                if name not in columns:
                    connection.execute(f"ALTER TABLE messages ADD COLUMN {name} {definition}")

    def save(self, message: StoredMessage) -> bool:
        """Persist a message. Returns False when it was already collected."""
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO messages (
                    message_id, chat_id, sender_user_id, sender_username,
                    sender_name, message_text, message_type, sent_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.chat_id,
                    message.sender_user_id,
                    message.sender_username,
                    message.sender_name,
                    message.message_text,
                    message.message_type,
                    message.sent_at,
                ),
            )
            return cursor.rowcount == 1

    def count(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM messages").fetchone()
            return row[0] if row else 0

    def mark_posted(self, message: StoredMessage, url: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE messages SET publish_status='posted', publish_url=?, attempts=attempts+1 WHERE chat_id=? AND message_id=?", (url, message.chat_id, message.message_id))

    def mark_failed(self, message: StoredMessage, error: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE messages SET publish_status='failed', last_error=?, attempts=attempts+1 WHERE chat_id=? AND message_id=?", (error[:500], message.chat_id, message.message_id))
