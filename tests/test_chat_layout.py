from __future__ import annotations

from streamlit.testing.v1 import AppTest

import frontend.chat_ui as chat_ui


def test_chat_composer_is_pinned_and_sends_message(monkeypatch) -> None:
    requests = []

    def request(base_url, method, path, **kwargs):
        requests.append((method, path, kwargs))
        if method == "POST":
            return {"job_id": "job-1"}
        if path.startswith("/api/jobs/"):
            return {"events": [], "cursor": 0, "done": False}
        return {
            "conversation": {},
            "messages": [
                {"role": "user", "content": f"Message {i}"}
                for i in range(20)
            ],
            "tool_executions": [],
        }

    monkeypatch.setattr(chat_ui, "api_request", request)
    app = AppTest.from_string(
        "from frontend.chat_ui import render_chat, render_composer\n"
        "render_chat('http://test', 'chat-1', 'model-1', 'Model')\n"
        "render_composer('http://test', 'chat-1', 'model-1')\n",
        default_timeout=20,
    ).run()

    assert not app.exception
    assert len(app.chat_message) == 20
    assert app.chat_input[0].proto.is_auto_positioned_at_bottom
    app.chat_input[0].set_value("Follow-up").run()
    assert not app.exception
    assert any(
        method == "POST"
        and path == "/api/conversations/chat-1/messages"
        and data["json"] == {"message": "Follow-up", "selected_model": "model-1"}
        for method, path, data in requests
    )
    assert app.chat_input[0].disabled


def test_assistant_usage_is_rendered_at_right(monkeypatch) -> None:
    monkeypatch.setattr(chat_ui, "api_request", lambda *args, **kwargs: {
        "messages": [
            {"role": "assistant", "content": "old"},
            {"role": "assistant", "content": "partial", "premium_units": 0.25,
             "usage_incomplete": True},
            {"role": "assistant", "content": "free", "premium_units": 0.0},
        ],
        "tool_executions": [],
    })
    app = AppTest.from_string(
        "from frontend.chat_ui import render_chat\n"
        "render_chat('http://test', 'chat', 'model', 'Model')\n"
    ).run()
    assert not app.exception
    rendered = [element.value for element in app.markdown]
    assert any("Premium units: unavailable" in item for item in rendered)
    assert any("Premium units: at least 0.25" in item for item in rendered)
    assert any("Premium units: 0" in item for item in rendered)


def test_streaming_and_completion_in_another_conversation(monkeypatch) -> None:
    requests = []
    updates = [
        {"events": [{"type": "delta", "content": "Hello"}], "cursor": 1, "done": False},
        {"events": [], "cursor": 1, "done": True},
    ]

    def request(base_url, method, path, **kwargs):
        requests.append((method, path, kwargs))
        if path.startswith("/api/jobs/"):
            return updates.pop(0)
        return {"messages": [{"role": "user", "content": "Saved history"}],
                "tool_executions": []}

    monkeypatch.setattr(chat_ui, "api_request", request)
    app = AppTest.from_string(
        "from frontend.chat_ui import render_chat, render_composer\n"
        "render_chat('http://test', 'chat-2', 'model', 'Model')\n"
        "render_composer('http://test', 'chat-2', 'model')\n"
    )
    app.session_state["active_job"] = {
        "job_id": "job-1", "conversation_id": "chat-1", "cursor": 0,
        "content": "", "skills": [], "tools": [], "error": None, "done": False,
    }
    app.run()
    assert not app.exception
    assert app.session_state["active_job"]["content"] == "Hello"
    assert app.chat_input[0].disabled
    assert any("another conversation" in item.value for item in app.info)
    app.run()
    assert not app.exception
    assert app.session_state["active_job"] is None
    assert not app.chat_input[0].disabled
    assert [entry[2]["params"]["after"] for entry in requests
            if entry[1].startswith("/api/jobs/")] == [0, 1]


def test_stop_generation_posts_to_current_job(monkeypatch) -> None:
    calls = []

    def request(base_url, method, path, **kwargs):
        calls.append((method, path))
        if method == "POST":
            return {"stopped": True}
        if path.startswith("/api/jobs/"):
            return {"events": [], "cursor": 0, "done": False}
        return {"messages": [], "tool_executions": []}

    monkeypatch.setattr(chat_ui, "api_request", request)
    app = AppTest.from_string(
        "from frontend.chat_ui import render_chat\n"
        "render_chat('http://test', 'chat', 'model', 'Model')\n"
    )
    app.session_state["active_job"] = {
        "job_id": "job", "conversation_id": "chat", "cursor": 0,
        "content": "", "skills": [], "tools": [], "error": None, "done": False,
    }
    app.run()
    app.button(key="stop-job").click().run()
    assert not app.exception
    assert ("POST", "/api/jobs/job/stop") in calls
