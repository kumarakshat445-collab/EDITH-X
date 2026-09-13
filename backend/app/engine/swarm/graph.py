from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.api.v1.telemetry import hub
from app.engine.swarm.nodes import (
    ArchitectNode,
    ExecutionNode,
    OrchestratorNode,
    RedTeamNode,
    SelfHealNode,
)
from app.engine.swarm.state import SwarmGraphState, SwarmStateStore
from app.models.schemas import AgentRole, TaskDAG, TaskStatus, TelemetryFrame


class SwarmOrchestrator:
    def __init__(self) -> None:
        self._store = SwarmStateStore.shared()
        self._nodes = {
            AgentRole.ORCHESTRATOR: OrchestratorNode(),
            AgentRole.ARCHITECT: ArchitectNode(),
            AgentRole.EXECUTION: ExecutionNode(),
            AgentRole.RED_TEAM: RedTeamNode(),
            AgentRole.SELF_HEAL: SelfHealNode(),
        }
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(SwarmGraphState)

        async def orchestrator(state: SwarmGraphState) -> SwarmGraphState:
            result = await self._nodes[AgentRole.ORCHESTRATOR].run(state["goal"], state)
            dag_nodes = result["plan"]
            dag = TaskDAG(goal=state["goal"], nodes=dag_nodes)
            state["dag"] = dag
            self._store.save_dag(state["session_id"], dag)
            await self._emit(state["session_id"], "dag_planned", {"nodes": [n.id for n in dag_nodes]})
            return state

        async def architect(state: SwarmGraphState) -> SwarmGraphState:
            await self._mark_running(state, "architect")
            blueprint = await self._nodes[AgentRole.ARCHITECT].run(state["goal"], state.get("artifacts", {}))
            state.setdefault("artifacts", {})["blueprint"] = blueprint["blueprint"]
            await self._mark_complete(state, "architect")
            return state

        async def execution(state: SwarmGraphState) -> SwarmGraphState:
            await self._mark_running(state, "execution")
            output = await self._nodes[AgentRole.EXECUTION].run(state["goal"], state.get("artifacts", {}))
            state.setdefault("artifacts", {})["execution"] = output
            await self._mark_complete(state, "execution")
            return state

        async def red_team(state: SwarmGraphState) -> SwarmGraphState:
            await self._mark_running(state, "red_team")
            audit = await self._nodes[AgentRole.RED_TEAM].run(state["goal"], state.get("artifacts", {}))
            state.setdefault("artifacts", {})["audit"] = audit["audit"]
            await self._mark_complete(state, "red_team")
            return state

        async def self_heal(state: SwarmGraphState) -> SwarmGraphState:
            await self._mark_running(state, "self_heal")
            result = await self._nodes[AgentRole.SELF_HEAL].run(
                state["goal"],
                {"iteration": state.get("iteration", 0), **state.get("artifacts", {})},
            )
            state["iteration"] = result["iteration"]
            await self._mark_complete(state, "self_heal")
            return state

        graph.add_node("orchestrator", orchestrator)
        graph.add_node("architect", architect)
        graph.add_node("execution", execution)
        graph.add_node("red_team", red_team)
        graph.add_node("self_heal", self_heal)

        graph.set_entry_point("orchestrator")
        graph.add_edge("orchestrator", "architect")
        graph.add_edge("architect", "execution")
        graph.add_edge("execution", "red_team")
        graph.add_edge("red_team", "self_heal")
        graph.add_edge("self_heal", END)

        return graph.compile()

    async def run_goal(self, goal: str, session_id: str) -> tuple[TaskDAG, str]:
        initial: SwarmGraphState = {
            "session_id": session_id,
            "goal": goal,
            "artifacts": {},
            "errors": [],
            "iteration": 0,
        }
        final = await self._graph.ainvoke(initial)
        dag = final["dag"]
        reply = (
            f"EDITH-X planned and executed DAG for goal: {goal}. "
            f"Nodes completed: {sum(1 for n in dag.nodes if n.status == TaskStatus.COMPLETED)}/{len(dag.nodes)}."
        )
        return dag, reply

    async def _emit(self, session_id: str, event: str, payload: dict[str, Any]) -> None:
        await hub.broadcast(
            TelemetryFrame(type=event, session_id=session_id, payload=payload)
        )

    async def _mark_running(self, state: SwarmGraphState, node_id: str) -> None:
        self._store.update_node_status(state["session_id"], node_id, TaskStatus.RUNNING)
        self._store.set_active_nodes(state["session_id"], [node_id])
        await self._emit(state["session_id"], "node_running", {"node_id": node_id})

    async def _mark_complete(self, state: SwarmGraphState, node_id: str) -> None:
        self._store.update_node_status(state["session_id"], node_id, TaskStatus.COMPLETED)
        await self._emit(state["session_id"], "node_completed", {"node_id": node_id})
