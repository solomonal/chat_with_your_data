from __future__ import annotations

import threading
import time
from typing import Any

import httpx
import streamlit as st
import uvicorn

from backend.api import app as api_app
from config import settings


@st.cache_resource
def ensure_backend() -> str:
    if settings.api_base_url:
        return settings.api_base_url.rstrip("/")

    base_url = f"http://{settings.backend_host}:{settings.backend_port}"
    server = uvicorn.Server(
        uvicorn.Config(
            api_app,
            host=settings.backend_host,
            port=settings.backend_port,
            log_level=settings.log_level.lower(),
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, name="chat-api", daemon=True)
    thread.start()
    deadline = time.monotonic() + 120
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{base_url}/api/health", timeout=1)
            response.raise_for_status()
            return base_url
        except httpx.HTTPError as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(
        f"Could not start the local FastAPI backend at {base_url}."
    ) from last_error


def api_request(
    base_url: str,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    try:
        response = httpx.request(
            method,
            f"{base_url}{path}",
            json=json,
            params=params,
            timeout=60,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not reach the application backend: {exc}") from exc
    if response.is_error:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(str(detail))
    return response.json()
