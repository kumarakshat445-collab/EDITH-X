from fastapi import FastAPI
from pydantic import BaseModel, Field

from edith import __version__

app = FastAPI(
    title="EDITH-X",
    description="Autonomous AI agent API",
    version=__version__,
)


class AgentStatus(BaseModel):
    name: str = "EDITH-X"
    version: str = __version__
    mode: str = "autonomous"
    status: str = "ready"


class TaskRequest(BaseModel):
    goal: str = Field(..., min_length=1, description="What the agent should accomplish")
    context: str | None = Field(default=None, description="Optional background context")


class TaskResponse(BaseModel):
    goal: str
    plan: list[str]
    status: str = "accepted"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "edith-x"}


@app.get("/agent/status", response_model=AgentStatus)
def agent_status() -> AgentStatus:
    return AgentStatus()


@app.post("/agent/task", response_model=TaskResponse)
def submit_task(request: TaskRequest) -> TaskResponse:
    plan = [
        "Analyze the requested goal",
        "Gather relevant context",
        "Execute the autonomous workflow",
        "Report results",
    ]
    if request.context:
        plan.insert(1, f"Incorporate context: {request.context[:80]}")

    return TaskResponse(goal=request.goal, plan=plan)
