"""Feature extractors that feed the on-device ONNX gates."""

import numpy as np

INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "transcribe": ("transcribe", "transcript", "whisper", "dictate", "speech-to-text", "meeting audio"),
    "vision": ("image", "photo", "screenshot", "picture", "camera", "detect", "diagram", "object"),
    "chat": ("explain", "chat", "ask", "question", "help"),
    "summarize": ("summarize", "summary", "tl;dr", "brief"),
    "code": ("code", "python", "bug", "function", "compile", "refactor"),
}


def intent_features(text: str) -> np.ndarray:
    lowered = " ".join(text.lower().split())
    scores = []
    for keywords in INTENT_KEYWORDS.values():
        score = 0.0
        for keyword in keywords:
            if keyword in lowered:
                score += 2.0 if lowered.startswith(keyword) else 1.0
        scores.append(score)
    return np.asarray(scores, dtype=np.float32)


def vision_features(rgb: np.ndarray) -> np.ndarray:
    image = np.asarray(rgb)
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("rgb must have shape (height, width, 3)")
    pixels = image.astype(np.float32)
    if pixels.max() > 1.0:
        pixels = pixels / 255.0
    luma = 0.2126 * pixels[:, :, 0] + 0.7152 * pixels[:, :, 1] + 0.0722 * pixels[:, :, 2]
    peak = pixels.max(axis=2)
    floor = pixels.min(axis=2)
    saturation = np.where(peak > 1e-6, (peak - floor) / np.maximum(peak, 1e-6), 0.0)
    horizontal = np.abs(np.diff(luma, axis=1)).mean() if luma.shape[1] > 1 else 0.0
    vertical = np.abs(np.diff(luma, axis=0)).mean() if luma.shape[0] > 1 else 0.0
    edge = (float(horizontal) + float(vertical)) / 2.0
    white_ratio = float((luma > 0.85).mean())
    return np.asarray([float(luma.mean()), float(saturation.mean()), edge, white_ratio], dtype=np.float32)


def speech_features(samples: np.ndarray) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    if audio.size == 0:
        raise ValueError("samples must contain at least one value")
    rms = float(np.sqrt(np.mean(audio * audio) + 1e-12))
    signs = np.sign(audio)
    signs[signs == 0] = 1
    crossings = np.abs(np.diff(signs)) > 0 if audio.size > 1 else np.array([False])
    zero_crossing_rate = float(np.mean(crossings))
    speech_band = rms if 0.03 < zero_crossing_rate < 0.22 else 0.0
    noise_band = rms if zero_crossing_rate >= 0.22 else 0.0
    return np.asarray([rms, zero_crossing_rate, speech_band, noise_band], dtype=np.float32)
