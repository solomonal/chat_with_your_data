from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import httpx

import backend.api as api_module
from backend.copilot_client import CopilotGateway
from backend.model_manager import model_to_dict
from database.db_manager import Database
from database.repositories import ConversationRepository
from tools.tool_registry import ToolRegistry
from copilot import ToolInvocation
from copilot.generated.session_events import AssistantUsageData


class FakeSession:
    def __init__(self) -> None:
        self.handler = None
        self.tool = None
        self.invoke_tool = False
        self.invoke_skill = False
        self.disconnected = False

    def on(self, handler):
        self.handler = handler
        return lambda: None

    async def send_and_wait(self, prompt: str, **kwargs):
        if self.invoke_skill:
            self.handler(
                SimpleNamespace(
                    type=SimpleNamespace(value="skill.invoked"),
                    agent_id=None,
                    data=SimpleNamespace(name="calculator"),
                )
            )
        if self.invoke_tool:
            self.tool.handler(
                ToolInvocation(
                    session_id="session",
                    tool_call_id="call",
                    tool_name=self.tool.name,
                    arguments={"a": 25, "b": 45},
                )
            )
        self.handler(
            SimpleNamespace(
                type=SimpleNamespace(value="assistant.message_delta"),
                agent_id=None,
                data=SimpleNamespace(delta_content="Mocked response"),
            )
        )
        return None

    async def disconnect(self):
        self.disconnected = True
        return None

    async def abort(self):
        return None


class FakeClient:
    def __init__(self) -> None:
        self.session = FakeSession()
        self.session_ids: list[str] = []
        self.resumed_ids: list[str] = []
        self.options: dict[str, object] = {}

    async def create_session(self, *, session_id: str, **kwargs):
        self.session_ids.append(session_id)
        self.options = kwargs
        self.session.tool = next(
            tool for tool in kwargs["tools"] if tool.name == "calculator_add"
        )
        return self.session

    async def resume_session(self, session_id: str, **kwargs):
        self.resumed_ids.append(session_id)
        self.options = kwargs
        return self.session

    async def list_models(self):
        return [SimpleNamespace(id="model-id", name="Model Name", description="Available")]

    async def get_auth_status(self):
        return SimpleNamespace(isAuthenticated=False)


def test_sdk_model_metadata_is_displayed_without_assumptions() -> None:
    model = SimpleNamespace(id="model-id", name="Model Name", description="Available")
    assert model_to_dict(model) == {
        "id": "model-id",
        "name": "Model Name",
        "description": "Available",
    }


def test_gateway_streams_mocked_sdk_response(tmp_path) -> None:
    repository = ConversationRepository(Database(tmp_path / "chat.sqlite3"))
    repository.db.initialize()
    conversation = repository.create_conversation("model-id")
    repository.add_message(conversation.conversation_id, "user", "Hello", "model-id")
    gateway = CopilotGateway(repository)
    client = FakeClient()
    gateway.client = client
    events: list[dict[str, object]] = []

    response = asyncio.run(
        gateway.respond(
            conversation,
            "Hello",
            events.append,
        )
    )

    assert response == "Mocked response"
    assert events == [{"type": "delta", "content": "Mocked response"}]
    saved = repository.get_conversation(conversation.conversation_id)
    assert saved is not None and saved.sdk_session_id in client.session_ids
    assert set(client.options["available_tools"]) == {
        *(f"custom:{tool.name}" for tool in client.options["tools"]),
        "builtin:skill",
    }
    assert client.options["enable_skills"] is True
    assert client.options["streaming"] is True
    assert client.options["enable_file_hooks"] is False
    assert client.options["enable_config_discovery"] is False
    assert client.options["enable_host_git_operations"] is False
    assert len(client.options["skill_directories"]) == 7


def test_usage_includes_subagents_and_deduplicates_event_ids(tmp_path) -> None:
    repository = ConversationRepository(Database(tmp_path / "chat.sqlite3"))
    repository.db.initialize()
    conversation = repository.create_conversation("model-id")
    repository.add_message(conversation.conversation_id, "user", "Hello", "model-id")
    gateway = CopilotGateway(repository)
    client = FakeClient()
    gateway.client = client
    original_send = client.session.send_and_wait

    async def send_with_usage(prompt, **kwargs):
        usage = SimpleNamespace(
            id=uuid.uuid4(),
            type=SimpleNamespace(value="assistant.usage"),
            agent_id="subagent",
            data=AssistantUsageData(model="actual-model", cost=0.25),
        )
        client.session.handler(usage)
        client.session.handler(usage)
        client.session.handler(SimpleNamespace(
            id=uuid.uuid4(),
            type=SimpleNamespace(value="assistant.usage"),
            agent_id=None,
            data=AssistantUsageData(model="another-model", cost=None),
        ))
        return await original_send(prompt, **kwargs)

    client.session.send_and_wait = send_with_usage
    events = []
    asyncio.run(gateway.respond(conversation, "Hello", events.append))
    assert [event for event in events if event["type"] == "usage"] == [
        {"type": "usage", "model": "actual-model", "cost": 0.25},
        {"type": "usage", "model": "another-model", "cost": None},
    ]


def test_premium_quota_uses_account_rpc(tmp_path) -> None:
    class Account:
        async def get_quota(self, request):
            assert request.git_hub_token is None
            return SimpleNamespace(quota_snapshots={
                "premium_interactions": SimpleNamespace(
                    remaining_percentage=75.0,
                    is_unlimited_entitlement=False,
                    used_requests=25,
                    entitlement_requests=100,
                    reset_date="2026-07-01",
                )
            })

    gateway = CopilotGateway(ConversationRepository(Database(tmp_path / "chat.sqlite3")))
    gateway.client = SimpleNamespace(rpc=SimpleNamespace(account=Account()))
    assert asyncio.run(gateway.premium_quota()) == {
        "remaining_percentage": 75.0,
        "unlimited": False,
        "used_requests": 25,
        "entitlement_requests": 100,
        "reset_date": "2026-07-01",
    }


def test_model_multiplier_uses_sdk_billing_metadata() -> None:
    model = SimpleNamespace(id="model", billing=SimpleNamespace(multiplier=0.0))
    assert model_to_dict(model)["premium_multiplier"] == 0.0


def test_gateway_resumes_saved_sdk_session(tmp_path) -> None:
    repository = ConversationRepository(Database(tmp_path / "chat.sqlite3"))
    repository.db.initialize()
    conversation = repository.create_conversation("model-id")
    repository.set_sdk_session(conversation.conversation_id, "saved-session", "model-id")
    conversation = repository.get_conversation(conversation.conversation_id)
    assert conversation is not None
    repository.add_message(conversation.conversation_id, "user", "Hello", "model-id")
    gateway = CopilotGateway(repository)
    client = FakeClient()
    gateway.client = client

    response = asyncio.run(gateway.respond(conversation, "Hello", lambda _: None))

    assert response == "Mocked response"
    assert client.resumed_ids == ["saved-session"]
    assert client.session_ids == []


def test_reset_conversation_disconnects_cached_session(tmp_path) -> None:
    gateway = CopilotGateway(
        ConversationRepository(Database(tmp_path / "chat.sqlite3"))
    )
    session = FakeSession()
    gateway._sessions["conversation"] = ("model-id", session)

    asyncio.run(gateway.reset_conversation("conversation"))

    assert session.disconnected
    assert "conversation" not in gateway._sessions


def test_cached_session_routes_tool_events_to_current_stream(tmp_path) -> None:
    repository = ConversationRepository(Database(tmp_path / "chat.sqlite3"))
    repository.db.initialize()
    conversation = repository.create_conversation("model-id")
    repository.add_message(conversation.conversation_id, "user", "First", "model-id")
    gateway = CopilotGateway(repository)
    client = FakeClient()
    gateway.client = client

    asyncio.run(gateway.respond(conversation, "First", lambda _: None))
    repository.add_message(conversation.conversation_id, "user", "Calculate", "model-id")
    client.session.invoke_tool = True
    client.session.invoke_skill = True
    second_events: list[dict[str, object]] = []

    asyncio.run(gateway.respond(conversation, "Calculate", second_events.append))

    assert [event["type"] for event in second_events] == [
        "skill_invoked",
        "tool_start",
        "tool_complete",
        "delta",
    ]


def test_model_discovery_uses_runtime_results(tmp_path) -> None:
    gateway = CopilotGateway(
        ConversationRepository(Database(tmp_path / "chat.sqlite3"))
    )
    client = FakeClient()
    gateway.client = client

    assert asyncio.run(gateway.list_models()) == [
        {"id": "model-id", "name": "Model Name", "description": "Available"}
    ]


def test_gateway_reports_sdk_authentication_status(tmp_path) -> None:
    gateway = CopilotGateway(
        ConversationRepository(Database(tmp_path / "chat.sqlite3"))
    )
    gateway.client = FakeClient()

    assert asyncio.run(gateway.is_authenticated()) is False


def test_model_api_reports_unauthenticated_runtime(monkeypatch) -> None:
    class UnauthenticatedGateway:
        async def list_models(self):
            raise RuntimeError("model discovery failed")

        async def is_authenticated(self):
            return False

    monkeypatch.setattr(api_module, "gateway", UnauthenticatedGateway())

    async def request():
        transport = httpx.ASGITransport(app=api_module.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.get("/api/models")

    response = asyncio.run(request())
    assert response.status_code == 503
    assert "not authenticated" in response.json()["detail"]
    assert "Sign in with GitHub" in response.json()["detail"]


def test_model_api_does_not_mislabel_other_failures_as_authentication(monkeypatch) -> None:
    class AuthenticatedGateway:
        async def list_models(self):
            raise RuntimeError("model discovery failed")

        async def is_authenticated(self):
            return True

    monkeypatch.setattr(api_module, "gateway", AuthenticatedGateway())

    async def request():
        transport = httpx.ASGITransport(app=api_module.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.get("/api/models")

    response = asyncio.run(request())
    assert response.status_code == 503
    assert "Could not retrieve models" in response.json()["detail"]
    assert "not authenticated" not in response.json()["detail"]


def test_model_api_returns_sdk_model_ids(monkeypatch) -> None:
    class ModelGateway:
        async def list_models(self):
            return [{"id": "runtime-model", "name": "Runtime Model"}]

    monkeypatch.setattr(api_module, "gateway", ModelGateway())

    async def request():
        transport = httpx.ASGITransport(app=api_module.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.get("/api/models")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.json() == [{"id": "runtime-model", "name": "Runtime Model"}]


def test_calculator_tool_handler_returns_structured_result(tmp_path) -> None:
    repository = ConversationRepository(Database(tmp_path / "chat.sqlite3"))
    repository.db.initialize()
    conversation = repository.create_conversation("model-id")
    events: list[dict[str, object]] = []
    registry = ToolRegistry(conversation.conversation_id, repository, events.append)
    tool = next(item for item in registry.build() if item.name == "calculator_add")

    result = tool.handler(
        ToolInvocation(
            session_id="session",
            tool_call_id="call",
            tool_name=tool.name,
            arguments={"a": 25, "b": 45},
        )
    )

    assert result is not None
    assert result.result_type == "success"
    assert '"result": 70.0' in result.text_result_for_llm
    assert [event["type"] for event in events] == ["tool_start", "tool_complete"]
    detail = repository.get_detail(conversation.conversation_id)
    assert detail is not None
    assert detail.tool_executions[0].execution_status == "success"
