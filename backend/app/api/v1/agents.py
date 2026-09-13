from fastapi import APIRouter

from app.engine.swarm.state import SwarmStateStore
from app.models.schemas import AgentStatus, TaskDAG

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/status", response_model=AgentStatus)
async def get_agent_status() -> AgentStatus:
    store = SwarmStateStore.shared()
    return AgentStatus(active_nodes=store.active_node_labels())


@router.get("/dag/{session_id}", response_model=TaskDAG | None)
async def get_session_dag(session_id: str) -> TaskDAG | None:
    return SwarmStateStore.shared().get_dag(session_id)
