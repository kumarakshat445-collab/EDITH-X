from fastapi import APIRouter

from app.api.v1 import agents, chat, memory, sandbox, telemetry

api_router = APIRouter()
api_router.include_router(chat.router)
api_router.include_router(agents.router)
api_router.include_router(sandbox.router)
api_router.include_router(telemetry.router)
api_router.include_router(memory.router)
