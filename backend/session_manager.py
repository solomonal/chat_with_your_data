from __future__ import annotations

from database.repositories import ConversationRepository
from backend.copilot_client import CopilotGateway


class SessionManager(CopilotGateway):
    """Owns the SDK client and its resumable per-conversation Copilot sessions."""

    def __init__(self, repository: ConversationRepository) -> None:
        super().__init__(repository)
