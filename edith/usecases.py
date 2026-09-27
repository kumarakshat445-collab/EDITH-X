"""Snapdragon AI use cases built on the on-device gates and AI Hub catalog."""

from dataclasses import dataclass

import numpy as np

from edith.catalog import HUB_MODELS, HubModel, model_for_use_case
from edith.features import intent_features, speech_features, vision_features
from edith.networks import intent_classifier, speech_classifier, vision_classifier


@dataclass(frozen=True)
class InferenceResult:
    name: str
    label: str
    confidence: float
    scores: dict[str, float]
    execution_provider: str
    features: dict[str, float]


def _provider(classifier_name: str) -> str:
    classifier = {
        "intent": intent_classifier,
        "vision": vision_classifier,
        "speech": speech_classifier,
    }[classifier_name]()
    return classifier.providers[0]


def route_text(text: str) -> tuple[InferenceResult, HubModel]:
    classifier = intent_classifier()
    features = intent_features(text)
    label, confidence, scores = classifier.predict(features)
    use_case = label
    lowered = text.lower()
    if label == "vision" and any(word in lowered for word in ("detect", "object", "locate")):
        use_case = "detect"
    model = model_for_use_case(use_case)
    feature_names = ("transcribe", "vision", "chat", "summarize", "code")
    result = InferenceResult(
        name=classifier.name,
        label=use_case,
        confidence=confidence,
        scores=scores,
        execution_provider=classifier.providers[0],
        features={name: float(features[index]) for index, name in enumerate(feature_names)},
    )
    return result, model


def classify_image(rgb: np.ndarray) -> InferenceResult:
    classifier = vision_classifier()
    features = vision_features(rgb)
    label, confidence, scores = classifier.predict(features)
    names = ("mean_luma", "mean_saturation", "edge", "white_ratio")
    return InferenceResult(
        name=classifier.name,
        label=label,
        confidence=confidence,
        scores=scores,
        execution_provider=classifier.providers[0],
        features={name: float(features[index]) for index, name in enumerate(names)},
    )


def classify_audio(samples: np.ndarray) -> InferenceResult:
    classifier = speech_classifier()
    features = speech_features(samples)
    label, confidence, scores = classifier.predict(features)
    names = ("rms", "zero_crossing_rate", "speech_band", "noise_band")
    return InferenceResult(
        name=classifier.name,
        label=label,
        confidence=confidence,
        scores=scores,
        execution_provider=classifier.providers[0],
        features={name: float(features[index]) for index, name in enumerate(names)},
    )


def build_plan(goal: str, use_case: str, model: HubModel, provider: str) -> list[str]:
    return [
        f"Run the on-device intent graph and label this goal as {use_case}.",
        f"Load Qualcomm AI Hub model {model.display_name} ({model.model_id}) for {model.domain}.",
        f"Execute with {provider}. On a Snapdragon HP PC, QNNExecutionProvider targets the Hexagon NPU.",
        "Keep the prompt, image, or audio on the PC.",
        f"Fetch the compiled asset with: {model.fetch_command}",
    ]


def active_provider() -> str:
    return _provider("intent")


def catalog_entries() -> list[HubModel]:
    return list(HUB_MODELS.values())
