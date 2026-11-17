from __future__ import annotations

import streamlit as st

from frontend.components import api_request


def render_sign_in(base_url: str) -> None:
    try:
        state = api_request(base_url, "GET", "/api/auth/status")
    except RuntimeError as exc:
        st.error(str(exc))
        return

    status = state.get("status")
    if status == "authenticated":
        st.success("GitHub sign-in completed. Loading your available models.")
        if not st.session_state.get("auth_refresh_requested"):
            st.session_state["auth_refresh_requested"] = True
            st.rerun()
        return

    st.session_state["auth_refresh_requested"] = False
    st.subheader("Connect GitHub Copilot")
    st.caption(
        "Sign in securely on GitHub. This app never asks for your GitHub password."
    )
    if status == "pending":
        st.markdown("1. Open the GitHub verification page.")
        st.link_button("Open GitHub verification", state["verification_uri"])
        st.markdown("2. Enter this one-time code on GitHub:")
        st.code(state["user_code"])
        st.caption("Waiting for authorization. The code expires automatically.")
        _poll_sign_in(base_url)
        if st.button("Cancel sign-in"):
            try:
                api_request(base_url, "POST", "/api/auth/cancel")
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.rerun()
    else:
        if status == "error":
            st.error(str(state.get("message", "Sign-in failed. Please try again.")))
        if st.button("Sign in with GitHub", type="primary"):
            try:
                api_request(base_url, "POST", "/api/auth/start")
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.rerun()


@st.fragment(run_every="2s")
def _poll_sign_in(base_url: str) -> None:
    try:
        state = api_request(base_url, "GET", "/api/auth/status")
    except RuntimeError as exc:
        st.error(str(exc))
        return
    if state.get("status") != "pending":
        st.rerun()
