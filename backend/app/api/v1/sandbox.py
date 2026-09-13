from fastapi import APIRouter

from app.engine.sandbox.manager import SandboxManager
from app.models.schemas import SandboxCreateRequest, SandboxSession

router = APIRouter(prefix="/sandbox", tags=["sandbox"])
manager = SandboxManager()


@router.post("/sessions", response_model=SandboxSession)
async def create_sandbox_session(request: SandboxCreateRequest) -> SandboxSession:
    return await manager.provision(request)


@router.get("/sessions/{session_id}", response_model=SandboxSession)
async def get_sandbox_session(session_id: str) -> SandboxSession:
    return manager.get(session_id)
