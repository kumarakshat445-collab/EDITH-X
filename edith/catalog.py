"""Qualcomm AI Hub models selected for Snapdragon-powered HP PCs.

Context binaries compiled for Snapdragon X Elite are compatible with
Snapdragon X and X Plus. Snapdragon X2 Elite assets target the newer
Hexagon NPU used in HP Omnibook Ultra-class machines.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class HubModel:
    model_id: str
    display_name: str
    domain: str
    use_cases: tuple[str, ...]
    runtime: str
    precision: str
    chipset: str
    entry_point: str
    fetch_command: str
    notes: str


SNAPDRAGON_X_ELITE = "qualcomm-snapdragon-x-elite"

TARGET_CHIPSETS: tuple[str, ...] = (SNAPDRAGON_X_ELITE,)

HP_REFERENCE_PCS: tuple[str, ...] = (
    "HP Omnibook 3 (Snapdragon X)",
    "HP Omnibook Ultra (Snapdragon X2 Plus)",
    "Snapdragon X Elite Compute Reference Device",
)


def _fetch(model_id: str, runtime: str, precision: str, chipset: str = SNAPDRAGON_X_ELITE) -> str:
    return (
        "qai-hub-models fetch "
        f"{model_id} --runtime {runtime} --precision {precision} --chipset {chipset}"
    )


HUB_MODELS: dict[str, HubModel] = {
    "whisper_small": HubModel(
        model_id="whisper_small",
        display_name="Whisper-Small",
        domain="audio",
        use_cases=("transcribe",),
        runtime="qnn",
        precision="w8a8",
        chipset=SNAPDRAGON_X_ELITE,
        entry_point="qai_hub_models.models.whisper_small",
        fetch_command=_fetch("whisper_small", "qnn", "w8a8"),
        notes="On-device meeting transcription. ONNX Runtime can also load the float ONNX asset.",
    ),
    "mobilenet_v2": HubModel(
        model_id="mobilenet_v2",
        display_name="MobileNet-v2",
        domain="computer-vision",
        use_cases=("vision",),
        runtime="qnn",
        precision="w8a8",
        chipset=SNAPDRAGON_X_ELITE,
        entry_point="qai_hub_models.models.mobilenet_v2",
        fetch_command=_fetch("mobilenet_v2", "qnn", "w8a8"),
        notes="Image classification for screenshots and camera frames on the Hexagon NPU.",
    ),
    "yolov7": HubModel(
        model_id="yolov7",
        display_name="YOLOv7",
        domain="computer-vision",
        use_cases=("detect",),
        runtime="qnn",
        precision="w8a8",
        chipset=SNAPDRAGON_X_ELITE,
        entry_point="qai_hub_models.models.yolov7",
        fetch_command=_fetch("yolov7", "qnn", "w8a8"),
        notes="Object detection when the request asks to detect or locate objects.",
    ),
    "llama_v3_2_3b_chat_quantized": HubModel(
        model_id="llama_v3_2_3b_chat_quantized",
        display_name="Llama-3.2-3B-Chat quantized",
        domain="generative-ai",
        use_cases=("chat", "summarize", "code"),
        runtime="qnn",
        precision="quantized",
        chipset=SNAPDRAGON_X_ELITE,
        entry_point="qai_hub_models.models.llama_v3_2_3b_chat_quantized",
        fetch_command=(
            "python -m qai_hub_models.models.llama_v3_2_3b_chat_quantized.export "
            '--device "Snapdragon X Elite CRD" --skip-inferencing --skip-profiling'
        ),
        notes=(
            "Local chat, summaries, and code help. Export produces QNN context binaries "
            "for the Snapdragon X Elite CRD; the same binaries run on Snapdragon X and X Plus PCs."
        ),
    ),
}


USE_CASE_MODELS: dict[str, str] = {
    "transcribe": "whisper_small",
    "vision": "mobilenet_v2",
    "detect": "yolov7",
    "chat": "llama_v3_2_3b_chat_quantized",
    "summarize": "llama_v3_2_3b_chat_quantized",
    "code": "llama_v3_2_3b_chat_quantized",
}


def model_for_use_case(use_case: str) -> HubModel:
    model_id = USE_CASE_MODELS[use_case]
    return HUB_MODELS[model_id]
