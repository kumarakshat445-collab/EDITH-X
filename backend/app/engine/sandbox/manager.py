from __future__ import annotations

from uuid import UUID

from app.core.config import get_settings
from app.models.schemas import SandboxCreateRequest, SandboxSession


class SandboxManager:
    """Ephemeral sandbox lifecycle manager (K8s Job / DinD adapter stub)."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._sessions: dict[str, SandboxSession] = {}

    async def provision(self, request: SandboxCreateRequest) -> SandboxSession:
        session = SandboxSession(runtime=request.runtime, status="ready")
        session.logs.append(
            f"Provisioned isolated sandbox using image={self._settings.sandbox_image} "
            f"cpu={self._settings.sandbox_cpu_limit} mem={self._settings.sandbox_memory_mb}MB"
        )
        self._sessions[str(session.id)] = session
        return session

    def get(self, session_id: str) -> SandboxSession:
        session = self._sessions.get(session_id)
        if not session:
            raise KeyError(session_id)
        return session
