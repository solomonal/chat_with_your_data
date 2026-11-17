from __future__ import annotations

from collections.abc import Callable

from backend.copilot_client import CopilotGateway
from database.models import Conversation


class AgentOrchestrator:
    def __init__(self, gateway: CopilotGateway) -> None:
        self.gateway = gateway

    async def handle_message(
        self,
        conversation: Conversation,
        message: str,
        emit: Callable[[dict[str, object]], None],
    ) -> str:
        return await self.gateway.respond(conversation, message, emit)
