# EDITH-X on Snapdragon HP PCs

## Proposal

EDITH-X is an existing on-device agent. This submission retargets it at Snapdragon-powered HP PCs and adds Qualcomm AI Hub models for three laptop use cases:

1. **Meeting scribe.** Speech activity runs locally, then transcription is handed to Whisper-Small compiled for the Snapdragon X Elite Hexagon NPU.
2. **Screen and camera understanding.** A vision gate separates documents, photos, and diagrams, then MobileNet-v2 classifies frames. Requests that ask to detect objects select YOLOv7.
3. **Private copilot.** Chat, summaries, and code help select quantized Llama-3.2-3B chat, exported for the Snapdragon X Elite compute reference device.

The same QNN context binaries run on Snapdragon X and X Plus PCs, including the HP Omnibook 3. For an HP Omnibook Ultra (Snapdragon X2 Plus), confirm the X2 chipset id with `qai-hub-models chipsets` and fetch that asset.

## Why this shape

HP Snapdragon laptops are the machine people already use for notes, calls, and coursework. These use cases stay on that PC: audio, screenshots, and prompts are not uploaded to complete the task. The control graphs are ONNX models executed by ONNX Runtime. When `QNNExecutionProvider` is installed, sessions target `QnnHtp.dll`. On any other machine the CPU execution provider runs the same graphs.

## Models

| Use case | Qualcomm AI Hub model | Runtime | Chipset |
| --- | --- | --- | --- |
| Transcribe | `whisper_small` | QNN w8a8 | `qualcomm-snapdragon-x-elite` |
| Classify an image | `mobilenet_v2` | QNN w8a8 | `qualcomm-snapdragon-x-elite` |
| Detect objects | `yolov7` | QNN w8a8 | `qualcomm-snapdragon-x-elite` |
| Chat, summarize, code | `llama_v3_2_3b_chat_quantized` | QNN context binary | Snapdragon X Elite CRD |

Fetch and export commands are served by `GET /api/v1/models`.

## What changed in EDITH-X

Previously `POST /agent/task` returned a fixed four-step plan. It now runs an ONNX intent model, chooses one AI Hub model, and returns a plan that names the Snapdragon runtime. New endpoints expose the catalog, image gate, and speech-activity gate.

Qualcomm AI Hub Models is installed with x64 Python. Windows ARM64 Python is not supported for that compile step. The compiled asset is what runs on the HP PC.
