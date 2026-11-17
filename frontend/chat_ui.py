from __future__ import annotations

import json
from typing import Any

import streamlit as st

from frontend.components import api_request


def render_chat(
    base_url: str,
    conversation_id: str,
    model_id: str | None,
    model_name: str | None,
) -> None:
    try:
        detail = api_request(
            base_url, "GET", f"/api/conversations/{conversation_id}"
        )
    except RuntimeError as exc:
        st.error(str(exc))
        return

    if st.session_state.get("chat_error"):
        st.error(st.session_state.pop("chat_error"))

    st.markdown(
        f'<span class="model-chip">Model: {model_name or model_id or "Not selected"}</span>',
        unsafe_allow_html=True,
    )
    for message in detail.get("messages", []):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                units = message.get("premium_units")
                if units is None:
                    cost_label = "Premium units: unavailable"
                else:
                    qualifier = "at least " if message.get("usage_incomplete") else ""
                    cost_label = f"Premium units: {qualifier}{units:g}"
                st.markdown(
                    f'<div class="response-cost">{cost_label}</div>',
                    unsafe_allow_html=True,
                )

    if st.session_state.get("active_job"):
        _render_active_job(base_url, conversation_id)

    if detail.get("tool_executions"):
        with st.expander("Tool activity"):
            for execution in reversed(detail["tool_executions"][-10:]):
                st.caption(
                    f"{execution['tool_name']} — {execution['execution_status']} "
                    f"({execution['timestamp']})"
                )
                try:
                    result = json.loads(execution["execution_result"])
                except (TypeError, json.JSONDecodeError):
                    st.caption("Tool result is not available in a displayable format.")
                    continue
                if execution["tool_name"] == "read_workspace_file":
                    content = result.get("content")
                    if isinstance(content, str) and len(content) > 1_000:
                        result["content"] = content[:1_000] + "\n… (truncated)"
                st.json(result, expanded=False)


@st.fragment(run_every="0.8s")
def _render_active_job(base_url: str, conversation_id: str) -> None:
    active = st.session_state.get("active_job")
    if not active:
        return
    try:
        update = api_request(
            base_url,
            "GET",
            f"/api/jobs/{active['job_id']}/events",
            params={"after": active["cursor"]},
        )
        for event in update["events"]:
            _apply_event(active, event)
        active["cursor"] = update["cursor"]
        if update["done"]:
            active["done"] = True
    except RuntimeError as exc:
        active["error"] = str(exc)
        active["done"] = True

    if active.get("done"):
        if active.get("error"):
            st.session_state["chat_error"] = active["error"]
        st.session_state["active_job"] = None
        st.rerun()

    if active.get("conversation_id") == conversation_id:
        for skill_name in active.get("skills", []):
            st.caption(f"Using skill: {skill_name}")
        for tool in active.get("tools", []):
            label = f"{tool['name']}"
            if tool["status"] == "running":
                st.caption(f"⏳ Using tool: {label}")
            else:
                st.caption(f"✓ Finished tool: {label}")
        if active.get("content"):
            with st.chat_message("assistant"):
                st.markdown(active["content"])
        elif not active.get("error"):
            st.caption("Thinking…")
        if active.get("error"):
            st.error(active["error"])
    else:
        st.info("A response is still generating in another conversation.")

    if st.button("Stop generation", key=f"stop-{active['job_id']}"):
        try:
            api_request(base_url, "POST", f"/api/jobs/{active['job_id']}/stop")
        except RuntimeError as exc:
            st.error(str(exc))


def render_composer(
    base_url: str,
    conversation_id: str,
    model_id: str | None,
) -> None:
    prompt = st.chat_input(
        "Message your assistant…",
        disabled=not model_id or bool(st.session_state.get("active_job")),
        key=f"chat-input-{conversation_id}",
    )
    if prompt:
        try:
            result = api_request(
                base_url,
                "POST",
                f"/api/conversations/{conversation_id}/messages",
                json={"message": prompt, "selected_model": model_id},
            )
        except RuntimeError as exc:
            st.error(str(exc))
        else:
            st.session_state["active_job"] = {
                "job_id": result["job_id"],
                "conversation_id": conversation_id,
                "cursor": 0,
                "content": "",
                "skills": [],
                "tools": [],
                "error": None,
                "done": False,
            }
            st.rerun()


def _apply_event(active: dict[str, Any], event: dict[str, Any]) -> None:
    event_type = event.get("type")
    if event_type == "delta":
        active["content"] += str(event.get("content", ""))
    elif event_type == "skill_invoked":
        name = str(event.get("skill_name", ""))
        if name and name not in active["skills"]:
            active["skills"].append(name)
    elif event_type == "tool_start":
        active["tools"].append(
            {"name": event.get("tool_name", "tool"), "status": "running"}
        )
    elif event_type == "tool_complete":
        for tool in reversed(active["tools"]):
            if (
                tool["name"] == event.get("tool_name")
                and tool["status"] == "running"
            ):
                tool["status"] = str(event.get("status", "complete"))
                break
    elif event_type == "error":
        active["error"] = event.get("message", "The response failed.")
