import numpy as np
from fastapi.testclient import TestClient

from edith.demo import _tone
from edith.main import app
from edith.usecases import classify_audio, classify_image, route_text

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_routes_map_to_ai_hub_models() -> None:
    cases = {
        "Transcribe this meeting audio": ("transcribe", "whisper_small"),
        "Detect objects in this photo": ("detect", "yolov7"),
        "Summarize these notes": ("summarize", "llama_v3_2_3b_chat_quantized"),
        "Explain how the Hexagon NPU schedules a model": ("chat", "llama_v3_2_3b_chat_quantized"),
        "Refactor this Python function": ("code", "llama_v3_2_3b_chat_quantized"),
    }
    for text, (use_case, model_id) in cases.items():
        result, model = route_text(text)
        assert result.label == use_case
        assert model.model_id == model_id
        assert result.execution_provider == "CPUExecutionProvider"
        assert result.confidence > 0.5


def test_vision_gates() -> None:
    white = np.full((8, 8, 3), 255, dtype=np.uint8)
    photo = np.zeros((8, 8, 3), dtype=np.uint8)
    photo[:, :, 0] = 220
    checker = np.zeros((8, 8, 3), dtype=np.uint8)
    checker[::2, ::2] = 255
    checker[1::2, 1::2] = 255
    assert classify_image(white).label == "document"
    assert classify_image(photo).label == "photo"
    assert classify_image(checker).label == "diagram"


def test_speech_activity_gate() -> None:
    silence = classify_audio(np.zeros(1600, dtype=np.float32))
    speech = classify_audio(_tone(1000))
    noise = classify_audio(np.random.default_rng(0).uniform(-1, 1, 4000).astype(np.float32))
    assert silence.label == "silence"
    assert speech.label == "speech"
    assert noise.label == "noise"


def test_task_endpoint_selects_whisper() -> None:
    response = client.post("/agent/task", json={"goal": "Transcribe this meeting audio"})
    body = response.json()
    assert response.status_code == 200
    assert body["use_case"] == "transcribe"
    assert body["ai_hub_model"] == "whisper_small"
    assert body["ai_hub_runtime"] == "qnn"
    assert "whisper_small" in body["plan"][-1]


def test_model_catalog_targets_snapdragon_x_elite() -> None:
    response = client.get("/api/v1/models")
    assert response.status_code == 200
    models = {item["model_id"]: item for item in response.json()}
    assert set(models) == {
        "whisper_small",
        "mobilenet_v2",
        "yolov7",
        "llama_v3_2_3b_chat_quantized",
    }
    for item in models.values():
        assert item["chipset"] == "qualcomm-snapdragon-x-elite"
        assert "qai-hub-models" in item["fetch_command"] or "qai_hub_models" in item["fetch_command"]


def test_vision_and_speech_http() -> None:
    white = [255, 255, 255] * 16
    vision = client.post("/api/v1/usecases/vision", json={"width": 4, "height": 4, "rgb": white})
    assert vision.status_code == 200
    assert vision.json()["label"] == "document"
    assert vision.json()["ai_hub_model"] == "mobilenet_v2"

    speech = client.post(
        "/api/v1/usecases/speech",
        json={"samples": _tone(1000)[:800].tolist(), "sample_rate_hz": 16000},
    )
    assert speech.status_code == 200
    assert speech.json()["label"] == "speech"
    assert speech.json()["ai_hub_model"] == "whisper_small"


def test_vision_rejects_short_buffer() -> None:
    response = client.post("/api/v1/usecases/vision", json={"width": 2, "height": 2, "rgb": [0, 0, 0]})
    assert response.status_code == 422


def test_status_describes_hp_targets() -> None:
    body = client.get("/agent/status").json()
    assert body["mode"] == "snapdragon-on-device"
    assert body["device"]["npu_active"] is False
    assert "HP Omnibook 3 (Snapdragon X)" in body["device"]["hp_reference_pcs"]
    assert "qualcomm-snapdragon-x-elite" in body["device"]["target_chipsets"]
