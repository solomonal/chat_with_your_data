from __future__ import annotations

import sqlite3

from database.db_manager import Database
from database.repositories import ConversationRepository


def test_conversation_messages_and_tools_persist(tmp_path) -> None:
    repository = ConversationRepository(Database(tmp_path / "chat.sqlite3"))
    repository.db.initialize()
    conversation = repository.create_conversation("model-from-sdk")
    repository.add_message(
        conversation.conversation_id, "user", "Hello", "model-from-sdk"
    )
    repository.add_message(
        conversation.conversation_id, "assistant", "Hi there", "model-from-sdk"
    )
    repository.add_tool_execution(
        conversation.conversation_id,
        "calculator_add",
        {"a": 1, "b": 2},
        {"result": 3},
        "success",
    )

    detail = repository.get_detail(conversation.conversation_id)
    assert detail is not None
    assert [message.role for message in detail.messages] == ["user", "assistant"]
    assert detail.conversation.selected_model == "model-from-sdk"
    assert detail.tool_executions[0].tool_name == "calculator_add"


def test_delete_cascades_and_clear_keeps_conversation(tmp_path) -> None:
    repository = ConversationRepository(Database(tmp_path / "chat.sqlite3"))
    repository.db.initialize()
    conversation = repository.create_conversation("model-from-sdk")
    repository.add_message(conversation.conversation_id, "user", "Hello", "model")

    assert repository.clear_messages(conversation.conversation_id)
    detail = repository.get_detail(conversation.conversation_id)
    assert detail is not None and detail.messages == []
    assert detail.conversation.sdk_session_id is None
    assert repository.delete_conversation(conversation.conversation_id)
    assert repository.get_conversation(conversation.conversation_id) is None


def test_legacy_messages_migrate_and_usage_persists(tmp_path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE conversations (
                conversation_id TEXT PRIMARY KEY, title TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                selected_model TEXT, sdk_session_id TEXT
            );
            CREATE TABLE messages (
                message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                role TEXT NOT NULL, content TEXT NOT NULL,
                timestamp TEXT NOT NULL, selected_model TEXT
            );
            INSERT INTO conversations VALUES ('chat', 'old', '1', '1', 'model', NULL);
            INSERT INTO messages VALUES ('msg', 'chat', 'assistant', 'old response', '1', 'model');
        """)
    db = Database(path)
    db.initialize()
    db.initialize()
    repository = ConversationRepository(db)
    repository.add_message("chat", "assistant", "new response", "model", 0.0, True)
    detail = repository.get_detail("chat")
    assert detail is not None
    assert detail.messages[0].content == "old response"
    assert detail.messages[0].premium_units is None
    assert detail.messages[1].premium_units == 0.0
    assert detail.messages[1].usage_incomplete is True
