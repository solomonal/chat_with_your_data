from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import backend.api as api
import frontend.components as components
from backend.streaming_manager import StreamingManager
from database.db_manager import Database
from database.repositories import ConversationRepository


@pytest.mark.parametrize(
    ("costs", "expected", "incomplete"),
    [
        ([0.25, 1.0, 0.0], 1.25, False),
        ([0.25, None], 0.25, True),
        ([None], None, True),
        ([], None, False),
        ([0.0], 0.0, False),
        ([0.25, float("nan"), -1.0], 0.25, True),
    ],
)
def test_response_usage_is_saved_per_job(
    tmp_path, monkeypatch, costs, expected, incomplete
) -> None:
    repository = ConversationRepository(Database(tmp_path / "chat.sqlite3"))
    repository.db.initialize()
    conversation = repository.create_conversation("model")
    streaming = StreamingManager()

    class Orchestrator:
        async def handle_message(self, current, message, emit):
            for cost in costs:
                emit({"type": "usage", "model": "actual", "cost": cost})
            return "answer"

    monkeypatch.setattr(api, "repository", repository)
    monkeypatch.setattr(api, "streaming", streaming)
    monkeypatch.setattr(api, "gateway", object())
    monkeypatch.setattr(api, "orchestrator", Orchestrator())

    async def send():
        result = await api.send_message(
            conversation.conversation_id, api.SendMessageRequest(message="Hello")
        )
        job = streaming.get(result["job_id"])
        assert job is not None and job.task is not None
        await job.task
        assert job.events[-1] == {"type": "complete"}

    asyncio.run(send())
    detail = repository.get_detail(conversation.conversation_id)
    assert detail is not None
    response = detail.messages[-1]
    assert response.role == "assistant"
    assert response.premium_units == expected
    assert response.usage_incomplete is incomplete


def test_quota_failure_is_reported_without_internal_error(monkeypatch) -> None:
    class Gateway:
        async def premium_quota(self):
            raise RuntimeError("sensitive runtime details")

    monkeypatch.setattr(api, "gateway", Gateway())

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api.app), base_url="http://test"
        ) as client:
            return await client.get("/api/quota")

    response = asyncio.run(request())
    assert response.status_code == 503
    assert response.json()["detail"] == "Premium-request quota is unavailable."


def test_failed_response_does_not_assign_usage_to_another_message(tmp_path, monkeypatch) -> None:
    repository = ConversationRepository(Database(tmp_path / "chat.sqlite3"))
    repository.db.initialize()
    conversation = repository.create_conversation("model")
    streaming = StreamingManager()

    class Orchestrator:
        async def handle_message(self, current, message, emit):
            emit({"type": "usage", "model": "actual", "cost": 1.0})
            raise RuntimeError("request failed")

    monkeypatch.setattr(api, "repository", repository)
    monkeypatch.setattr(api, "streaming", streaming)
    monkeypatch.setattr(api, "gateway", object())
    monkeypatch.setattr(api, "orchestrator", Orchestrator())

    async def send():
        result = await api.send_message(
            conversation.conversation_id, api.SendMessageRequest(message="Hello")
        )
        job = streaming.get(result["job_id"])
        assert job is not None and job.task is not None
        await job.task
        assert job.events[-1]["type"] == "error"

    asyncio.run(send())
    detail = repository.get_detail(conversation.conversation_id)
    assert detail is not None
    assert len(detail.messages) == 1
    assert detail.messages[0].role == "user"
    assert detail.messages[0].premium_units is None


@pytest.mark.parametrize(
    ("quota", "metric", "caption"),
    [
        ({"unlimited": False, "remaining_percentage": 75.0,
          "used_requests": 25, "entitlement_requests": 100}, "25.0%", None),
        ({"unlimited": True}, None, "Unlimited entitlement"),
        ({"unlimited": False, "remaining_percentage": None}, None,
         "Quota percentage unavailable."),
        (None, None, "Quota usage unavailable."),
    ],
)
def test_sidebar_displays_account_quota(monkeypatch, quota, metric, caption) -> None:
    monkeypatch.setattr(components, "ensure_backend", lambda: "http://test")

    def request(base_url, method, path, **kwargs):
        if path == "/api/models":
            return [{"id": "model", "premium_multiplier": 0.25}]
        if path == "/api/quota":
            return {"premium_interactions": quota}
        if path == "/api/conversations":
            return []
        raise AssertionError(path)

    monkeypatch.setattr(components, "api_request", request)
    app_path = Path(__file__).resolve().parent.parent / "frontend" / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=20).run()
    assert not app.exception
    assert (app.metric[0].value if app.metric else None) == metric
    captions = [item.value for item in app.caption]
    if caption:
        assert caption in captions
    assert any("0.25× per request" in item for item in captions)
