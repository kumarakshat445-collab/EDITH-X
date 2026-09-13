from __future__ import annotations

import ast
from typing import Any, Awaitable, Callable

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolHandler] = {
            "shell": self._shell,
            "python_repl": self._python_repl,
            "ast_parser": self._ast_parser,
            "file_io": self._file_io,
            "web_crawler": self._web_crawler,
        }

    async def execute(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return await self._tools[name](payload)

    async def _shell(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"stdout": f"[sandboxed] {payload.get('command', '')}", "exit_code": 0}

    async def _python_repl(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"stdout": "EDITH-X scaffold ready", "code": payload.get("code", "")}

    async def _ast_parser(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = payload.get("source", "")
        tree = ast.parse(source) if source else ast.parse("pass")
        return {"node_count": len(list(ast.walk(tree)))}

    async def _file_io(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"path": payload.get("path"), "action": payload.get("action", "read"), "status": "scoped"}

    async def _web_crawler(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"url": payload.get("url"), "status": "blocked_in_boilerplate"}
