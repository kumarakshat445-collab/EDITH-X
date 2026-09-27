"""Run the Snapdragon use-case gates and print a text report."""

import json

import numpy as np

from edith.runtime import device_profile
from edith.usecases import active_provider, catalog_entries, classify_audio, classify_image, route_text


def _tone(frequency_hz: float, seconds: float = 0.25, rate: int = 16000) -> np.ndarray:
    time = np.arange(int(seconds * rate), dtype=np.float32) / rate
    return (0.5 * np.sin(2 * np.pi * frequency_hz * time)).astype(np.float32)


def main() -> None:
    prompts = [
        "Transcribe this meeting audio",
        "What objects are in this photo",
        "Summarize these notes",
        "Explain how the Hexagon NPU schedules a model",
        "Refactor this Python function",
    ]
    routes = []
    for prompt in prompts:
        result, model = route_text(prompt)
        routes.append(
            {
                "prompt": prompt,
                "use_case": result.label,
                "confidence": round(result.confidence, 4),
                "model": model.model_id,
                "provider": result.execution_provider,
            }
        )

    white = np.full((8, 8, 3), 255, dtype=np.uint8)
    photo = np.zeros((8, 8, 3), dtype=np.uint8)
    photo[:, :, 0] = 220
    checker = np.zeros((8, 8, 3), dtype=np.uint8)
    checker[::2, ::2] = 255
    checker[1::2, 1::2] = 255
    images = {
        "blank-page": classify_image(white).label,
        "saturated-photo": classify_image(photo).label,
        "checker-diagram": classify_image(checker).label,
    }
    silence = classify_audio(np.zeros(1600, dtype=np.float32)).label
    speech = classify_audio(_tone(1000)).label
    noise = classify_audio(np.random.default_rng(0).uniform(-1, 1, 4000).astype(np.float32)).label
    report = {
        "device": device_profile([active_provider()]),
        "routes": routes,
        "vision": images,
        "speech": {"silence": silence, "speech": speech, "noise": noise},
        "models": [model.model_id for model in catalog_entries()],
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
