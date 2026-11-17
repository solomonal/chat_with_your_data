from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MessageRole = Literal["user", "assistant"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Conversation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    selected_model: str | None = None
    sdk_session_id: str | None = None


class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: str
    conversation_id: str
    role: MessageRole
    content: str
    timestamp: str
    selected_model: str | None = None
    premium_units: float | None = None
    usage_incomplete: bool = False


class ToolExecution(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    execution_id: str
    conversation_id: str
    tool_name: str
    input_parameters: str
    execution_result: str
    execution_status: str
    timestamp: str


class ConversationDetail(BaseModel):
    conversation: Conversation
    messages: list[Message] = Field(default_factory=list)
    tool_executions: list[ToolExecution] = Field(default_factory=list)
