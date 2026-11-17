from __future__ import annotations

import asyncio
from types import SimpleNamespace

import frontend.auth_ui as auth_ui
from copilot.generated.rpc import (
    AuthLoginResultStatus,
    AuthLoginStepKind,
)
from streamlit.testing.v1 import AppTest

from backend.authentication import AuthenticationManager


class FakeLogin:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False
        self.url = "https://github.com/login/device"
        self.result_status = AuthLoginResultStatus.COMPLETED

    async def begin(self, params):
        assert params.method.value == "device-code"
        return SimpleNamespace(
            flow_id="flow",
            step=SimpleNamespace(
                kind=AuthLoginStepKind.DEVICE_CODE,
                user_code="TEST-CODE",
                verification_uri=self.url,
                expires_in=60,
            ),
        )

    async def advance(self, params, *, timeout):
        self.started.set()
        await self.release.wait()
        return SimpleNamespace(
            kind=AuthLoginStepKind.COMPLETED,
            result=SimpleNamespace(status=self.result_status),
        )

    async def cancel(self, params):
        self.cancelled = True


class FakeSession:
    def __init__(self, login: FakeLogin) -> None:
        self.rpc = SimpleNamespace(accounts=SimpleNamespace(login=login))
        self.disconnected = False

    async def disconnect(self):
        self.disconnected = True


class FakeGateway:
    def __init__(self) -> None:
        self.login = FakeLogin()
        self.session = FakeSession(self.login)
        self.client = self
        self.authenticated = False

    async def is_authenticated(self):
        return self.authenticated

    async def create_session(self, *, available_tools, **options):
        assert available_tools == []
        assert options["enable_file_hooks"] is False
        assert options["enable_config_discovery"] is False
        return self.session


def test_device_sign_in_completes_and_cleans_up() -> None:
    async def run():
        gateway = FakeGateway()
        manager = AuthenticationManager(gateway)
        state = await manager.start()
        assert state["status"] == "pending"
        assert state["user_code"] == "TEST-CODE"
        assert state["verification_uri"] == "https://github.com/login/device"
        await gateway.login.started.wait()
        gateway.authenticated = True
        gateway.login.release.set()
        await manager._task
        assert manager.status() == {"status": "authenticated"}
        assert gateway.session.disconnected
        assert gateway.login.cancelled

    asyncio.run(run())


def test_sign_in_cancel_cleans_up_and_hides_device_code() -> None:
    async def run():
        gateway = FakeGateway()
        manager = AuthenticationManager(gateway)
        await manager.start()
        await gateway.login.started.wait()
        await manager.cancel()
        assert manager.status() == {"status": "idle"}
        assert gateway.login.cancelled
        assert gateway.session.disconnected

    asyncio.run(run())


def test_plaintext_storage_consent_is_not_automatically_granted() -> None:
    async def run():
        gateway = FakeGateway()
        gateway.login.result_status = AuthLoginResultStatus.NEEDS_PLAINTEXT_CONSENT
        manager = AuthenticationManager(gateway)
        await manager.start()
        gateway.login.release.set()
        await manager._task
        assert manager.status()["status"] == "error"
        assert "plaintext" in manager.status()["message"]
        assert gateway.login.cancelled

    asyncio.run(run())


def test_rejects_non_github_verification_link() -> None:
    async def run():
        gateway = FakeGateway()
        gateway.login.url = "https://example.com/login/device"
        manager = AuthenticationManager(gateway)
        try:
            await manager.start()
        except RuntimeError as exc:
            assert "unsupported login step" in str(exc)
        else:
            raise AssertionError("Unexpected verification link accepted")
        assert gateway.login.cancelled
        assert gateway.session.disconnected

    asyncio.run(run())


def test_sign_in_page_displays_device_code(monkeypatch) -> None:
    state = {"status": "idle"}

    def request(base_url, method, path):
        if path == "/api/auth/start":
            state.update(
                status="pending",
                user_code="TEST-CODE",
                verification_uri="https://github.com/login/device",
            )
        return dict(state)

    monkeypatch.setattr(auth_ui, "api_request", request)
    app = AppTest.from_string(
        "from frontend.auth_ui import render_sign_in\n"
        "render_sign_in('http://127.0.0.1:8765')\n",
        default_timeout=20,
    ).run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert app.code[0].value == "TEST-CODE"
    assert app.get("link_button")[0].url == "https://github.com/login/device"


def test_pending_sign_in_updates_when_authorization_finishes(monkeypatch) -> None:
    states = iter([
        {"status": "pending", "user_code": "TEST-CODE",
         "verification_uri": "https://github.com/login/device"},
        {"status": "authenticated"},
        {"status": "authenticated"},
        {"status": "authenticated"},
    ])
    monkeypatch.setattr(auth_ui, "api_request", lambda *args: next(states))
    app = AppTest.from_string(
        "from frontend.auth_ui import render_sign_in\n"
        "render_sign_in('http://test')\n",
        default_timeout=20,
    ).run()
    assert not app.exception
    assert any("sign-in completed" in item.value for item in app.success)
