from fastapi import APIRouter, Depends

from app.engine.swarm.graph import SwarmOrchestrator
from app.models.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse)
async def submit_chat(request: ChatRequest) -> ChatResponse:
    orchestrator = SwarmOrchestrator()
    dag, reply = await orchestrator.run_goal(request.message, request.session_id)
    return ChatResponse(session_id=request.session_id, reply=reply, dag=dag)
