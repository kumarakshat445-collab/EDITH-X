from __future__ import annotations

from typing import Any, TypedDict

from app.models.schemas import DAGNode, TaskDAG, TaskStatus


class SwarmGraphState(TypedDict, total=False):
    session_id: str
    goal: str
    dag: TaskDAG
    artifacts: dict[str, Any]
    errors: list[str]
    iteration: int


class SwarmStateStore:
    _instance: SwarmStateStore | None = None

    def __init__(self) -> None:
        self._dags: dict[str, TaskDAG] = {}
        self._active_nodes: dict[str, list[str]] = {}

    @classmethod
    def shared(cls) -> SwarmStateStore:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def save_dag(self, session_id: str, dag: TaskDAG) -> None:
        self._dags[session_id] = dag

    def get_dag(self, session_id: str) -> TaskDAG | None:
        return self._dags.get(session_id)

    def set_active_nodes(self, session_id: str, labels: list[str]) -> None:
        self._active_nodes[session_id] = labels

    def active_node_labels(self) -> list[str]:
        labels: list[str] = []
        for values in self._active_nodes.values():
            labels.extend(values)
        return labels

    def update_node_status(self, session_id: str, node_id: str, status: TaskStatus) -> None:
        dag = self._dags.get(session_id)
        if not dag:
            return
        for node in dag.nodes:
            if node.id == node_id:
                node.status = status
