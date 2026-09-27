# EDITH-X V2

On-device agent for Snapdragon-powered HP PCs. Goals are classified by a local ONNX model, then dispatched to a Qualcomm AI Hub model compiled for the Hexagon NPU.

## Use cases

- **Meeting scribe** — speech activity gate, then Whisper-Small (`whisper_small`)
- **Screen and camera** — document / photo / diagram gate, then MobileNet-v2 or YOLOv7
- **Private copilot** — chat, summary, and code help via quantized Llama-3.2-3B

X Elite context binaries also run on Snapdragon X and X Plus PCs (HP Omnibook 3). See `docs/PROPOSAL.md`.

## Development

```bash
./scripts/cloud-agent-install.sh
source .venv/bin/activate

uvicorn edith.main:app --host 0.0.0.0 --port 8000 --reload
python -m edith.demo
pytest
```

Open `http://localhost:8000/docs`.

Fetch compiled assets on x64 Python (Windows ARM64 Python cannot install the AI Hub compile tools):

```bash
./scripts/fetch-ai-hub-models.sh
```

On the HP PC, set `QNN_BACKEND_PATH` to `QnnHtp.dll` so ONNX Runtime uses `QNNExecutionProvider`.

## API

- `GET /health`
- `GET /agent/status`
- `POST /agent/task`
- `GET /api/v1/models`
- `POST /api/v1/usecases/route`
- `POST /api/v1/usecases/vision`
- `POST /api/v1/usecases/speech`
