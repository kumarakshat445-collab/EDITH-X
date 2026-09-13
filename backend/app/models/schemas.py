from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    ARCHITECT = "architect"
    EXECUTION = "execution"
    RED_TEAM = "red_team"
    SELF_HEAL = "self_heal"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class DAGNode(BaseModel):
    id: str
    label: str
    role: AgentRole
    depends_on: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    output: dict[str, Any] = Field(default_factory=dict)


class TaskDAG(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    goal: str
    nodes: list[DAGNode]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    session_id: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    dag: TaskDAG | None = None


class AgentStatus(BaseModel):
    name: str = "EDITH-X"
    version: str = "2.0.0"
    mode: str = "autonomous"
    active_nodes: list[str] = Field(default_factory=list)


class SandboxCreateRequest(BaseModel):
    runtime: str = "python"
    entrypoint: str = "main.py"
    source_bundle: dict[str, str] = Field(default_factory=dict)


class SandboxSession(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    status: str = "provisioning"
    runtime: str
    logs: list[str] = Field(default_factory=list)


class TelemetryFrame(BaseModel):
    type: str
    session_id: str
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MemoryQuery(BaseModel):
    query: str
    tier: str = "semantic"
    top_k: int = 5


class MemoryRecord(BaseModel):
    id: str
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
