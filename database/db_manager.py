from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config import settings


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    selected_model TEXT,
                    sdk_session_id TEXT
                );
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)
                        ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    selected_model TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_timestamp
                    ON messages(conversation_id, timestamp);
                CREATE TABLE IF NOT EXISTS tool_executions (
                    execution_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)
                        ON DELETE CASCADE,
                    tool_name TEXT NOT NULL,
                    input_parameters TEXT NOT NULL,
                    execution_result TEXT NOT NULL,
                    execution_status TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tool_executions_conversation_timestamp
                    ON tool_executions(conversation_id, timestamp);
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(messages)")
            }
            if "premium_units" not in columns:
                connection.execute("ALTER TABLE messages ADD COLUMN premium_units REAL")
            if "usage_incomplete" not in columns:
                connection.execute(
                    "ALTER TABLE messages ADD COLUMN usage_incomplete INTEGER NOT NULL DEFAULT 0"
                )


database = Database()
