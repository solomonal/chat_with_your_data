from __future__ import annotations

import asyncio
import logging
import math
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from backend.agent_orchestrator import AgentOrchestrator
from backend.authentication import AuthenticationManager
from backend.logging_config import configure_logging
from backend.session_manager import SessionManager
from backend.streaming_manager import StreamingManager
from database.db_manager import database
from database.models import Conversation
from database.repositories import ConversationRepository

logger = logging.getLogger(__name__)
repository = ConversationRepository()
streaming = StreamingManager()
gateway: SessionManager | None = None
orchestrator: AgentOrchestrator | None = None
authentication: AuthenticationManager | None = None


class CreateConversationRequest(BaseModel):
    selected_model: str | None = None


class UpdateConversationRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    selected_model: str | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Conversation title must not be blank.")
        return value


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    selected_model: str | None = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global gateway, orchestrator, authentication
    configure_logging()
    database.initialize()
    logger.info("AI Agent Assistant backend starting")
    gateway = SessionManager(repository)
    try:
        await gateway.start()
    except Exception as exc:
        logger.error("Copilot runtime startup failed (%s)", type(exc).__name__)
    orchestrator = AgentOrchestrator(gateway)
    authentication = AuthenticationManager(gateway)
    yield
    if authentication is not None:
        await authentication.cancel()
    if gateway is not None:
        await gateway.stop()
    logger.info("AI Agent Assistant backend stopped")


app = FastAPI(title="AI Agent Assistant API", version="1.0.0", lifespan=lifespan)


def _require_gateway() -> SessionManager:
    if gateway is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "The Copilot runtime is unavailable. Check that the official SDK runtime "
                "is installed and that GitHub Copilot authentication is available."
            ),
        )
    return gateway


def _require_conversation(conversation_id: str) -> Conversation:
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


async def _stop_conversation_jobs(conversation_id: str) -> None:
    for job in list(streaming.jobs.values()):
        if job.conversation_id == conversation_id and not job.done:
            await streaming.stop(job.job_id)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "copilot_runtime": (
            "started" if gateway is not None and gateway.client is not None else "unavailable"
        ),
    }


def _require_authentication() -> AuthenticationManager:
    if authentication is None:
        raise HTTPException(status_code=503, detail="Authentication service is unavailable.")
    return authentication


@app.get("/api/auth/status")
async def authentication_status() -> dict[str, object]:
    return _require_authentication().status()


@app.post("/api/auth/start")
async def start_authentication() -> dict[str, object]:
    try:
        return await _require_authentication().start()
    except Exception as exc:
        logger.error("Could not start Copilot sign-in (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Could not start GitHub sign-in. Check the Copilot runtime and network connection.",
        ) from exc


@app.post("/api/auth/cancel")
async def cancel_authentication() -> dict[str, str]:
    await _require_authentication().cancel()
    return {"status": "idle"}


@app.get("/api/models")
async def list_models() -> list[dict[str, object]]:
    client = _require_gateway()
    try:
        models = await client.list_models()
    except Exception as exc:
        logger.error("Copilot model discovery failed (%s)", type(exc).__name__)
        try:
            authenticated = await client.is_authenticated()
        except Exception as auth_exc:
            logger.warning(
                "Could not check Copilot authentication status (%s)",
                type(auth_exc).__name__,
            )
            authenticated = None
        if authenticated is False:
            raise HTTPException(
                status_code=503,
                detail=(
                    "The Copilot runtime is not authenticated. Use Sign in with "
                    "GitHub on this page to connect your account."
                ),
            ) from exc
        raise HTTPException(
            status_code=503,
            detail=(
                "Could not retrieve models from GitHub Copilot. Verify your Copilot "
                "authentication and model access, then try again."
            ),
        ) from exc
    logger.info("Discovered %d available Copilot models", len(models))
    return models


@app.get("/api/quota")
async def premium_quota() -> dict[str, object]:
    try:
        quota = await asyncio.wait_for(_require_gateway().premium_quota(), timeout=5)
    except Exception as exc:
        logger.warning("Copilot quota retrieval failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="Premium-request quota is unavailable."
        ) from exc
    return {"premium_interactions": quota}


@app.get("/api/conversations")
async def list_conversations() -> list[dict[str, object]]:
    return [item.model_dump() for item in repository.list_conversations()]


@app.post("/api/conversations", status_code=201)
async def create_conversation(
    request: CreateConversationRequest,
) -> dict[str, object]:
    if request.selected_model:
        client = _require_gateway()
        try:
            available = await client.list_models()
        except Exception as exc:
            logger.error("Copilot model discovery failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Copilot model discovery failed.") from exc
        if request.selected_model not in {str(model["id"]) for model in available}:
            raise HTTPException(status_code=422, detail="The selected model is unavailable.")
    conversation = repository.create_conversation(request.selected_model)
    logger.info("Created conversation %s", conversation.conversation_id)
    return conversation.model_dump()


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict[str, object]:
    detail = repository.get_detail(conversation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return detail.model_dump()


@app.patch("/api/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    request: UpdateConversationRequest,
) -> dict[str, object]:
    current = _require_conversation(conversation_id)
    replace_model = request.selected_model is not None
    if replace_model and request.selected_model != current.selected_model:
        client = _require_gateway()
        try:
            available = await client.list_models()
        except Exception as exc:
            logger.error("Copilot model discovery failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Copilot model discovery failed.") from exc
        if request.selected_model not in {str(model["id"]) for model in available}:
            raise HTTPException(status_code=422, detail="The selected model is unavailable.")
        await _stop_conversation_jobs(conversation_id)
    updated = repository.update_conversation(
        conversation_id,
        title=request.title,
        selected_model=request.selected_model,
        replace_model=replace_model,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if replace_model and request.selected_model != current.selected_model:
        client = _require_gateway()
        await client.reset_conversation(conversation_id)
    return updated.model_dump()


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str) -> dict[str, bool]:
    _require_conversation(conversation_id)
    await _stop_conversation_jobs(conversation_id)
    if gateway is not None:
        await gateway.reset_conversation(conversation_id)
    deleted = repository.delete_conversation(conversation_id)
    return {"deleted": deleted}


@app.delete("/api/conversations/{conversation_id}/messages")
async def clear_conversation(conversation_id: str) -> dict[str, bool]:
    _require_conversation(conversation_id)
    await _stop_conversation_jobs(conversation_id)
    if gateway is not None:
        await gateway.reset_conversation(conversation_id)
    return {"cleared": repository.clear_messages(conversation_id)}


@app.post("/api/conversations/{conversation_id}/messages", status_code=202)
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
) -> dict[str, str]:
    current = _require_conversation(conversation_id)
    client = _require_gateway()
    if request.selected_model and request.selected_model != current.selected_model:
        try:
            available = await client.list_models()
        except Exception as exc:
            logger.error("Copilot model discovery failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Copilot model discovery failed.") from exc
        if request.selected_model not in {str(model["id"]) for model in available}:
            raise HTTPException(status_code=422, detail="The selected model is unavailable.")
        await _stop_conversation_jobs(conversation_id)
        current = repository.update_conversation(
            conversation_id,
            selected_model=request.selected_model,
            replace_model=True,
        )
        if current is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
    if not current.selected_model:
        raise HTTPException(status_code=422, detail="Select an available model first.")
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Copilot agent is unavailable.")

    repository.add_message(
        conversation_id, "user", request.message, current.selected_model
    )
    job = streaming.create(conversation_id)
    logger.info("Accepted user message for conversation %s", conversation_id)

    async def run() -> None:
        usage_costs: list[float] = []
        missing_usage = False

        def emit(event: dict[str, object]) -> None:
            nonlocal missing_usage
            if event.get("type") == "usage":
                cost = event.get("cost")
                if (
                    isinstance(cost, (int, float))
                    and not isinstance(cost, bool)
                    and math.isfinite(cost)
                    and cost >= 0
                ):
                    usage_costs.append(float(cost))
                else:
                    missing_usage = True
            else:
                job.emit(event)

        try:
            response = await orchestrator.handle_message(
                current, request.message, emit
            )
            repository.add_message(
                conversation_id, "assistant", response, current.selected_model,
                premium_units=sum(usage_costs) if usage_costs else None,
                usage_incomplete=missing_usage,
            )
            job.emit({"type": "complete"})
        except asyncio.CancelledError:
            try:
                await client.abort(conversation_id)
            except Exception as exc:
                logger.warning(
                    "Could not abort Copilot session for conversation %s (%s)",
                    conversation_id,
                    type(exc).__name__,
                )
            finally:
                job.emit({"type": "cancelled"})
            raise
        except Exception as exc:
            logger.error(
                "Copilot response failed for conversation %s (%s)",
                conversation_id,
                type(exc).__name__,
            )
            job.emit(
                {
                    "type": "error",
                    "message": (
                        "The Copilot request failed. Check your model access, local "
                        "authentication, and application logs."
                    ),
                }
            )
        finally:
            job.done = True

    job.task = asyncio.create_task(run(), name=f"copilot-chat-{job.job_id}")
    return {"job_id": job.job_id}


@app.get("/api/jobs/{job_id}/events")
async def get_job_events(
    job_id: str,
    after: int = Query(default=0, ge=0),
) -> dict[str, object]:
    job = streaming.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job not found.")
    return {
        "events": job.events[after:],
        "cursor": len(job.events),
        "done": job.done,
    }


@app.post("/api/jobs/{job_id}/stop")
async def stop_job(job_id: str) -> dict[str, bool]:
    job = streaming.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job not found.")
    return {"stopped": await streaming.stop(job_id)}
