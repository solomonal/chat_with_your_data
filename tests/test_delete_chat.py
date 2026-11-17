from __future__ import annotations

import asyncio
from pathlib import Path

from streamlit.testing.v1 import AppTest

import backend.api as api
import frontend.chat_ui as chat_ui
import frontend.components as components
from backend.streaming_manager import StreamingManager
from database.db_manager import Database
from database.repositories import ConversationRepository


def _app(monkeypatch, *, models=True, failure=False, different_models=False):
    conversations = [
        {"conversation_id": "first", "title": "First chat", "selected_model": "model"},
        {"conversation_id": "second", "title": "Second chat", "selected_model": "model"},
    ]
    if different_models:
        conversations[1]["selected_model"] = "other-model"
    requests = []

    def request(base_url, method, path, **kwargs):
        requests.append((method, path))
        if path == "/api/models":
            return [{"id": "model"}, {"id": "other-model"}] if models else []
        if path == "/api/quota":
            return {"premium_interactions": None}
        if path == "/api/conversations":
            return list(conversations)
        if path.startswith("/api/conversations/"):
            conversation_id = path.rsplit("/", 1)[-1]
            if method == "DELETE":
                if failure:
                    raise RuntimeError("Delete failed")
                conversations[:] = [
                    item for item in conversations
                    if item["conversation_id"] != conversation_id
                ]
                return {"deleted": True}
            return {
                "conversation": next(
                    item for item in conversations
                    if item["conversation_id"] == conversation_id
                ),
                "messages": [],
                "tool_executions": [],
            }
        if path.startswith("/api/jobs/"):
            return {"events": [], "cursor": 0, "done": False}
        raise AssertionError((method, path))

    monkeypatch.setattr(components, "ensure_backend", lambda: "http://test")
    monkeypatch.setattr(components, "api_request", request)
    monkeypatch.setattr(chat_ui, "api_request", request)
    path = Path(__file__).resolve().parent.parent / "frontend" / "app.py"
    return AppTest.from_file(str(path), default_timeout=20).run(), conversations, requests


def test_delete_selected_chat_requires_confirmation_and_preserves_others(monkeypatch):
    app, conversations, requests = _app(monkeypatch)
    app.radio[0].set_value("second").run()
    app.button(key="delete-second").click().run()
    assert not app.exception
    assert "Second chat" in app.warning[-1].value
    assert not any(method == "DELETE" for method, _ in requests)
    app.button(key="cancel-delete-second").click().run()
    assert len(conversations) == 2
    app.button(key="delete-second").click().run()
    app.button(key="confirm-delete-second").click().run()
    assert not app.exception
    assert [item["conversation_id"] for item in conversations] == ["first"]
    assert ("DELETE", "/api/conversations/second") in requests
    assert app.radio[0].value == "first"

    app.button(key="delete-first").click().run()
    app.button(key="confirm-delete-first").click().run()
    assert not app.exception
    assert not conversations
    assert len(app.radio) == 0


def test_deletion_available_without_models_and_failure_is_visible(monkeypatch):
    app, conversations, requests = _app(monkeypatch, models=False, failure=True)
    app.button(key="delete-first").click().run()
    app.button(key="confirm-delete-first").click().run()
    assert not app.exception
    assert any("Delete failed" in item.value for item in app.error)
    assert len(conversations) == 2
    assert ("DELETE", "/api/conversations/first") in requests


def test_switching_chats_clears_pending_confirmation(monkeypatch):
    app, conversations, requests = _app(monkeypatch, different_models=True)
    app.button(key="delete-first").click().run()
    app.radio[0].set_value("second").run()
    assert not app.exception
    assert "confirm-delete-second" not in [button.key for button in app.button]
    assert len(conversations) == 2
    assert not any(method == "DELETE" for method, _ in requests)
    assert not any(method == "PATCH" for method, _ in requests)
    assert app.selectbox[0].value == "other-model"


def test_deleting_other_chat_keeps_active_job(monkeypatch):
    app, _, _ = _app(monkeypatch)
    app.session_state["active_job"] = {
        "job_id": "job", "conversation_id": "first", "cursor": 0,
        "content": "", "skills": [], "tools": [], "error": None, "done": False,
    }
    app.radio[0].set_value("second").run()
    app.button(key="delete-second").click().run()
    app.button(key="confirm-delete-second").click().run()
    assert not app.exception
    assert app.session_state["active_job"]["conversation_id"] == "first"


def test_deleting_active_chat_clears_its_job(monkeypatch):
    app, _, _ = _app(monkeypatch)
    app.session_state["active_job"] = {
        "job_id": "job", "conversation_id": "first", "cursor": 0,
        "content": "", "skills": [], "tools": [], "error": None, "done": False,
    }
    app.button(key="delete-first").click().run()
    app.button(key="confirm-delete-first").click().run()
    assert not app.exception
    assert "active_job" not in app.session_state


def test_delete_api_stops_job_and_removes_only_target_history(tmp_path, monkeypatch):
    repository = ConversationRepository(Database(tmp_path / "chat.sqlite3"))
    repository.db.initialize()
    target = repository.create_conversation("model")
    other = repository.create_conversation("model")
    repository.add_message(target.conversation_id, "user", "target", "model")
    repository.add_message(other.conversation_id, "user", "keep", "model")
    repository.add_tool_execution(target.conversation_id, "tool", {}, {}, "success")
    streaming = StreamingManager()
    reset_ids = []

    class Gateway:
        async def reset_conversation(self, conversation_id):
            reset_ids.append(conversation_id)

    monkeypatch.setattr(api, "repository", repository)
    monkeypatch.setattr(api, "streaming", streaming)
    monkeypatch.setattr(api, "gateway", Gateway())

    async def delete():
        job = streaming.create(target.conversation_id)
        job.task = asyncio.create_task(asyncio.sleep(60))
        await asyncio.sleep(0)
        assert await api.delete_conversation(target.conversation_id) == {"deleted": True}
        assert job.task.cancelled()

    asyncio.run(delete())
    assert reset_ids == [target.conversation_id]
    assert repository.get_detail(target.conversation_id) is None
    assert repository.get_detail(other.conversation_id).messages[0].content == "keep"
    with repository.db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tool_executions").fetchone()[0] == 0
