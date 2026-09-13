# EDITH-X

Autonomous AI agent runtime.

## Development

```bash
./scripts/cloud-agent-install.sh
source .venv/bin/activate
uvicorn edith.main:app --host 0.0.0.0 --port 8000 --reload
```

## API

- `GET /health` — service health check
- `GET /agent/status` — agent readiness
- `POST /agent/task` — submit a goal for autonomous execution

Example:

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/agent/status
curl -s -X POST http://localhost:8000/agent/task \
  -H 'Content-Type: application/json' \
  -d '{"goal":"Summarize the repository README"}'
```
