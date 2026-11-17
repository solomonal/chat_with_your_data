from __future__ import annotations

import sys
import math
from pathlib import Path
from typing import Any

import streamlit as st

project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from frontend.chat_ui import render_chat, render_composer
from frontend.auth_ui import render_sign_in
from frontend.components import api_request, ensure_backend


def _load_styles() -> None:
    stylesheet = Path(__file__).with_name("styles.css")
    st.markdown(stylesheet.read_text(encoding="utf-8"), unsafe_allow_html=True)


def _model_label(model: dict[str, Any]) -> str:
    name = str(model.get("name") or model["id"])
    return name if name == model["id"] else f"{name} · {model['id']}"


def _initialize_page() -> tuple[str | None, list[dict[str, Any]], str | None]:
    st.set_page_config(
        page_title="AI Agent Assistant",
        page_icon="✦",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _load_styles()
    try:
        base_url = ensure_backend()
    except (RuntimeError, OSError) as exc:
        return None, [], str(exc)
    try:
        models = api_request(base_url, "GET", "/api/models")
    except (RuntimeError, OSError) as exc:
        return base_url, [], str(exc)
    return base_url, models, None


def _select_conversation() -> None:
    st.session_state["conversation_id"] = st.session_state["conversation-history"]


def _render_sidebar(
    base_url: str,
    models: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    st.sidebar.markdown("## ✦ AI Agent Assistant")
    st.sidebar.caption("Powered by your authenticated GitHub Copilot runtime")
    st.sidebar.success("Backend connected")

    if models:
        with st.sidebar.expander("Premium usage", expanded=True):
            st.caption("Account-wide premium-request quota")
            try:
                quota = api_request(base_url, "GET", "/api/quota").get(
                    "premium_interactions"
                )
            except (RuntimeError, OSError):
                quota = None
            if quota is None:
                st.caption("Quota usage unavailable.")
            elif quota.get("unlimited"):
                st.caption("Unlimited entitlement")
            else:
                remaining = quota.get("remaining_percentage")
                if (
                    isinstance(remaining, (int, float))
                    and not isinstance(remaining, bool)
                    and math.isfinite(remaining)
                    and 0 <= remaining <= 100
                ):
                    st.metric("Quota used", f"{100 - remaining:.1f}%")
                else:
                    st.caption("Quota percentage unavailable.")
                used = quota.get("used_requests")
                entitlement = quota.get("entitlement_requests")
                if isinstance(used, int) and isinstance(entitlement, int):
                    st.caption(f"{used} of {entitlement} premium requests used")
                if quota.get("reset_date"):
                    st.caption(f"Resets: {quota['reset_date']}")

        options = [str(model["id"]) for model in models]
        model_lookup = {str(model["id"]): model for model in models}
        conversations = api_request(base_url, "GET", "/api/conversations")
        selected_id = st.session_state.get("conversation_id")
        current = next(
            (item for item in conversations if item["conversation_id"] == selected_id),
            None,
        )
        if current is None and conversations:
            current = conversations[0]
            st.session_state["conversation_id"] = current["conversation_id"]
        initial_model = (
            current.get("selected_model")
            if current and current.get("selected_model") in options
            else ("" if current and current.get("selected_model") else options[0])
        )
        select_options = ["", *options] if initial_model == "" else options
        selection_key = f"model-selector-{current['conversation_id']}" if current else "model-selector-new"
        if initial_model == "" and st.session_state.get(selection_key) not in select_options:
            st.session_state[selection_key] = ""
        selected_model = st.sidebar.selectbox(
            "Copilot model",
            select_options,
            index=select_options.index(initial_model),
            format_func=lambda value: (
                "Choose an available model…" if not value else _model_label(model_lookup[value])
            ),
            key=selection_key,
            help="Models are fetched live from your authenticated Copilot runtime.",
            disabled=bool(st.session_state.get("active_job")),
        )
        model = model_lookup.get(selected_model)
        if model and model.get("description"):
            st.sidebar.caption(str(model["description"]))
        if model:
            multiplier = model.get("premium_multiplier")
            if multiplier is None:
                st.sidebar.caption("Selected model's premium multiplier: unavailable")
            else:
                st.sidebar.caption(
                    f"Selected model's premium multiplier: {multiplier:g}× per request"
                )
        st.sidebar.caption(
            "Quota is account-wide, not a per-model percentage. "
            "Premium units are not a dollar charge."
        )
        if current and current.get("selected_model") and not model:
            st.sidebar.warning(
                f"The saved model {current['selected_model']} is unavailable. "
                "Choose another model to switch this conversation."
            )
    else:
        conversations = api_request(base_url, "GET", "/api/conversations")
        current = None
        selected_model = None
        st.sidebar.warning("No Copilot models are available.")

    if st.sidebar.button("＋ New chat", use_container_width=True, disabled=not models):
        conversation = api_request(
            base_url,
            "POST",
            "/api/conversations",
            json={"selected_model": selected_model},
        )
        st.session_state["conversation_id"] = conversation["conversation_id"]
        st.rerun()

    st.sidebar.markdown("### Conversations")
    conversations = api_request(base_url, "GET", "/api/conversations")
    if conversations:
        labels = {
            item["conversation_id"]: item["title"] or "New chat"
            for item in conversations
        }
        ids = list(labels)
        selected_id = st.session_state.get("conversation_id")
        if selected_id not in ids:
            selected_id = ids[0]
            st.session_state["conversation_id"] = selected_id
        selected_id = st.sidebar.radio(
            "History",
            ids,
            index=ids.index(selected_id),
            format_func=lambda value: labels[value],
            label_visibility="collapsed",
            key="conversation-history",
            on_change=_select_conversation,
        )
        st.session_state["conversation_id"] = selected_id
        current = next(item for item in conversations if item["conversation_id"] == selected_id)
        if st.session_state.get("delete_conversation_id") not in (None, selected_id):
            st.session_state.pop("delete_conversation_id", None)
        if selected_model and selected_model != current.get("selected_model"):
            api_request(
                base_url,
                "PATCH",
                f"/api/conversations/{selected_id}",
                json={"selected_model": selected_model},
            )
            st.rerun()

        if st.session_state.get("delete_conversation_id") == selected_id:
            st.sidebar.warning(
                f"Delete “{labels[selected_id]}” and its saved messages and tool activity? "
                "This cannot be undone."
            )
            confirm, cancel = st.sidebar.columns(2)
            if confirm.button("Confirm delete", key=f"confirm-delete-{selected_id}"):
                result = api_request(
                    base_url, "DELETE", f"/api/conversations/{selected_id}"
                )
                if not result.get("deleted"):
                    raise RuntimeError("The conversation could not be deleted.")
                active = st.session_state.get("active_job")
                if active and active.get("conversation_id") == selected_id:
                    st.session_state.pop("active_job", None)
                st.session_state.pop("delete_conversation_id", None)
                st.session_state.pop("conversation_id", None)
                st.rerun()
            if cancel.button("Cancel", key=f"cancel-delete-{selected_id}"):
                st.session_state.pop("delete_conversation_id", None)
                st.rerun()
        elif st.sidebar.button(
            "Delete selected chat", key=f"delete-{selected_id}", use_container_width=True
        ):
            st.session_state["delete_conversation_id"] = selected_id
            st.rerun()

        with st.sidebar.expander("Conversation settings"):
            title = st.text_input(
                "Rename conversation",
                value=current["title"],
                key=f"title-{selected_id}",
            )
            if st.button("Save title", key=f"save-title-{selected_id}"):
                api_request(
                    base_url,
                    "PATCH",
                    f"/api/conversations/{selected_id}",
                    json={"title": title},
                )
                st.rerun()
            if st.button("Clear messages", key=f"clear-{selected_id}"):
                api_request(
                    base_url,
                    "DELETE",
                    f"/api/conversations/{selected_id}/messages",
                )
                st.session_state.pop("active_job", None)
                st.rerun()
    else:
        selected_id = None
        st.sidebar.caption("Your saved conversations will appear here.")

    with st.sidebar.expander("Settings and connection"):
        st.caption("Authentication is provided by the official Copilot runtime.")
        st.caption("The app does not extract or display credentials.")
        st.caption("Workspace file tools are read-only and limited to the configured workspace.")
        st.code("COPILOT_WORKSPACE_DIR", language="text")

    return selected_id, selected_model


def main() -> None:
    base_url, models, startup_error = _initialize_page()
    st.markdown('<div class="app-eyebrow">Your workspace copilot</div>', unsafe_allow_html=True)
    st.title("AI Agent Assistant")
    st.caption(
        "A multi-model assistant with streaming responses, persistent chats, and "
        "skill-guided tools."
    )

    if base_url is None:
        st.error(startup_error or "The local application backend is unavailable.")
        st.info(
            "Install the dependencies and SDK runtime, then authenticate with GitHub "
            "Copilot using its supported local authentication flow. No token is "
            "collected by this app."
        )
        return
    if startup_error:
        st.warning(startup_error)
        try:
            health = api_request(base_url, "GET", "/api/health")
        except RuntimeError as exc:
            st.error(str(exc))
        else:
            if health.get("copilot_runtime") == "started":
                render_sign_in(base_url)
    try:
        conversation_id, selected_model = _render_sidebar(base_url, models)
    except RuntimeError as exc:
        st.error(str(exc))
        return
    if not models:
        if startup_error:
            st.info("Saved conversations can still be viewed while Copilot is unavailable.")
        else:
            st.info(
                "No models are currently available from Copilot. Verify your model "
                "access, then refresh the page. Saved conversations can still be viewed."
            )
    if conversation_id is None:
        if models:
            st.info("Create a new chat to get started.")
        return
    model = next((item for item in models if item["id"] == selected_model), None)
    if model is not None:
        display_model = _model_label(model)
    elif conversation_id:
        try:
            detail = api_request(
                base_url, "GET", f"/api/conversations/{conversation_id}"
            )
            saved_model = detail["conversation"].get("selected_model")
        except RuntimeError:
            saved_model = None
        display_model = f"{saved_model} (unavailable)" if saved_model else None
    else:
        display_model = None
    render_chat(
        base_url,
        conversation_id,
        selected_model,
        display_model,
    )
    render_composer(base_url, conversation_id, selected_model)


main()
