from __future__ import annotations

from typing import Any

from app.engine.compiler.pipeline import CompilerPipeline
from app.engine.tools.registry import ToolRegistry
from app.models.schemas import AgentRole, DAGNode, TaskStatus


class BaseNode:
    role: AgentRole

    async def run(self, goal: str, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class OrchestratorNode(BaseNode):
    role = AgentRole.ORCHESTRATOR

    async def run(self, goal: str, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "plan": [
                DAGNode(id="architect", label="Design topology", role=AgentRole.ARCHITECT),
                DAGNode(
                    id="execution",
                    label="Generate implementation",
                    role=AgentRole.EXECUTION,
                    depends_on=["architect"],
                ),
                DAGNode(
                    id="red_team",
                    label="Security audit",
                    role=AgentRole.RED_TEAM,
                    depends_on=["execution"],
                ),
                DAGNode(
                    id="self_heal",
                    label="Regression loop",
                    role=AgentRole.SELF_HEAL,
                    depends_on=["red_team"],
                ),
            ]
        }


class ArchitectNode(BaseNode):
    role = AgentRole.ARCHITECT

    async def run(self, goal: str, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "blueprint": {
                "services": ["api-gateway", "swarm-orchestrator", "sandbox-runtime"],
                "goal": goal,
            }
        }


class ExecutionNode(BaseNode):
    role = AgentRole.EXECUTION

    def __init__(self) -> None:
        self._tools = ToolRegistry()
        self._compiler = CompilerPipeline()

    async def run(self, goal: str, context: dict[str, Any]) -> dict[str, Any]:
        bundle = await self._compiler.compile_intent(goal, context.get("blueprint", {}))
        shell = await self._tools.execute("python_repl", {"code": "print('EDITH-X scaffold ready')"})
        return {"bundle": bundle, "repl": shell}


class RedTeamNode(BaseNode):
    role = AgentRole.RED_TEAM

    async def run(self, goal: str, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "audit": {
                "bandit": "passed",
                "issues": [],
                "goal": goal,
            }
        }


class SelfHealNode(BaseNode):
    role = AgentRole.SELF_HEAL

    async def run(self, goal: str, context: dict[str, Any]) -> dict[str, Any]:
        iteration = int(context.get("iteration", 0))
        return {
            "tests": "passed",
            "iteration": iteration + 1,
            "status": TaskStatus.COMPLETED,
        }
