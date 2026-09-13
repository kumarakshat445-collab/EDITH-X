from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.schemas import TelemetryFrame

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


class TelemetryHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(session_id, set()).add(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        if session_id in self._connections:
            self._connections[session_id].discard(websocket)

    async def broadcast(self, frame: TelemetryFrame) -> None:
        dead: list[WebSocket] = []
        for socket in self._connections.get(frame.session_id, set()):
            try:
                await socket.send_json(frame.model_dump(mode="json"))
            except Exception:
                dead.append(socket)
        for socket in dead:
            self.disconnect(frame.session_id, socket)


hub = TelemetryHub()


@router.websocket("/stream/{session_id}")
async def telemetry_stream(websocket: WebSocket, session_id: str) -> None:
    await hub.connect(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(session_id, websocket)
