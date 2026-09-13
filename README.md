# EDITH-X V2

Autonomous sentient-tier operating core and Nexus Poly-Engine monorepo.

## Architecture

- **Backend** (`backend/`): FastAPI ASGI core, LangGraph swarm orchestration, sandbox/compiler engines, WebSocket telemetry.
- **Frontend** (`frontend/`): Next.js 14 command center HUD with live neural stream, sandbox viewport, and Monaco workbench.

## Development

```bash
./scripts/cloud-agent-install.sh
source .venv/bin/activate

# Backend
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend && npm run dev
```

Open `http://localhost:3000/command-center`.

## API

- `GET /health`
- `POST /api/v1/chat/`
- `GET /api/v1/agents/status`
- `WS /api/v1/telemetry/stream/{session_id}`
