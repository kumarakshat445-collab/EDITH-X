from fastapi import APIRouter

from app.models.schemas import MemoryQuery, MemoryRecord

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/query", response_model=list[MemoryRecord])
async def query_memory(request: MemoryQuery) -> list[MemoryRecord]:
    # Boilerplate semantic recall stub; PGVector wiring lands in a later iteration.
    return [
        MemoryRecord(
            id="mem-001",
            content=f"Stub recall for: {request.query}",
            score=0.91,
            metadata={"tier": request.tier},
        )
    ]
