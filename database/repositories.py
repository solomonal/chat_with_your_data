from __future__ import annotations

import json
import uuid
from pathlib import Path

from database.db_manager import Database, database
from database.models import (
    Conversation,
    ConversationDetail,
    Message,
    MessageRole,
    ToolExecution,
    utc_now,
)


class ConversationRepository:
    def __init__(self, db: Database = database) -> None:
        self.db = db

    def create_conversation(self, selected_model: str | None = None) -> Conversation:
        now = utc_now()
        conversation = Conversation(
            conversation_id=str(uuid.uuid4()),
            title="New chat",
            created_at=now,
            updated_at=now,
            selected_model=selected_model,
        )
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations
                    (conversation_id, title, created_at, updated_at, selected_model)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    conversation.conversation_id,
                    conversation.title,
                    conversation.created_at,
                    conversation.updated_at,
                    conversation.selected_model,
                ),
            )
        return conversation

    def list_conversations(self) -> list[Conversation]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [Conversation.model_validate(dict(row)) for row in rows]

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        return Conversation.model_validate(dict(row)) if row else None

    def get_detail(self, conversation_id: str) -> ConversationDetail | None:
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            return None
        with self.db.connect() as connection:
            messages = connection.execute(
                """
                SELECT * FROM messages WHERE conversation_id = ?
                ORDER BY timestamp, rowid
                """,
                (conversation_id,),
            ).fetchall()
            tools = connection.execute(
                """
                SELECT * FROM tool_executions WHERE conversation_id = ?
                ORDER BY timestamp, rowid
                """,
                (conversation_id,),
            ).fetchall()
        return ConversationDetail(
            conversation=conversation,
            messages=[Message.model_validate(dict(row)) for row in messages],
            tool_executions=[ToolExecution.model_validate(dict(row)) for row in tools],
        )

    def update_conversation(
        self,
        conversation_id: str,
        *,
        title: str | None = None,
        selected_model: str | None = None,
        replace_model: bool = False,
    ) -> Conversation | None:
        current = self.get_conversation(conversation_id)
        if current is None:
            return None
        next_title = title.strip() if title is not None else current.title
        next_model = selected_model if replace_model else current.selected_model
        session_id = current.sdk_session_id
        if replace_model and next_model != current.selected_model:
            session_id = None
        with self.db.connect() as connection:
            connection.execute(
                """
                UPDATE conversations
                SET title = ?, selected_model = ?, sdk_session_id = ?, updated_at = ?
                WHERE conversation_id = ?
                """,
                (next_title, next_model, session_id, utc_now(), conversation_id),
            )
        return self.get_conversation(conversation_id)

    def set_sdk_session(
        self, conversation_id: str, session_id: str, model: str
    ) -> None:
        with self.db.connect() as connection:
            connection.execute(
                """
                UPDATE conversations
                SET sdk_session_id = ?, selected_model = ?, updated_at = ?
                WHERE conversation_id = ?
                """,
                (session_id, model, utc_now(), conversation_id),
            )

    def delete_conversation(self, conversation_id: str) -> bool:
        with self.db.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            )
        return cursor.rowcount > 0

    def clear_messages(self, conversation_id: str) -> bool:
        if self.get_conversation(conversation_id) is None:
            return False
        with self.db.connect() as connection:
            connection.execute(
                "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
            )
            connection.execute(
                "DELETE FROM tool_executions WHERE conversation_id = ?",
                (conversation_id,),
            )
            connection.execute(
                """
                UPDATE conversations SET title = 'New chat', sdk_session_id = NULL,
                    updated_at = ? WHERE conversation_id = ?
                """,
                (utc_now(), conversation_id),
            )
        return True

    def add_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        selected_model: str | None,
        premium_units: float | None = None,
        usage_incomplete: bool = False,
    ) -> Message:
        message = Message(
            message_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role=role,
            content=content,
            timestamp=utc_now(),
            selected_model=selected_model,
            premium_units=premium_units,
            usage_incomplete=usage_incomplete,
        )
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO messages
                    (message_id, conversation_id, role, content, timestamp, selected_model,
                     premium_units, usage_incomplete)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.conversation_id,
                    message.role,
                    message.content,
                    message.timestamp,
                    message.selected_model,
                    message.premium_units,
                    message.usage_incomplete,
                ),
            )
            title = content.strip().replace("\n", " ")[:60] or "New chat"
            connection.execute(
                """
                UPDATE conversations
                SET title = CASE
                    WHEN title = 'New chat' AND ? = 'user' THEN ?
                    ELSE title
                END,
                updated_at = ?
                WHERE conversation_id = ?
                """,
                (role, title, utc_now(), conversation_id),
            )
        return message

    def add_tool_execution(
        self,
        conversation_id: str,
        tool_name: str,
        input_parameters: dict[str, object],
        execution_result: dict[str, object],
        execution_status: str,
    ) -> ToolExecution:
        execution = ToolExecution(
            execution_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            tool_name=tool_name,
            input_parameters=json.dumps(input_parameters, ensure_ascii=True),
            execution_result=json.dumps(execution_result, ensure_ascii=True),
            execution_status=execution_status,
            timestamp=utc_now(),
        )
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO tool_executions
                    (execution_id, conversation_id, tool_name, input_parameters,
                     execution_result, execution_status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution.execution_id,
                    execution.conversation_id,
                    execution.tool_name,
                    execution.input_parameters,
                    execution.execution_result,
                    execution.execution_status,
                    execution.timestamp,
                ),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
                (utc_now(), conversation_id),
            )
        return execution


def create_repository(path: Path | None = None) -> ConversationRepository:
    return ConversationRepository(Database(path) if path is not None else database)
