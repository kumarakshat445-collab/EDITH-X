"""Small ONNX control models executed by ONNX Runtime.

These graphs are the on-device router, vision gate, and speech-activity gate.
On a Snapdragon PC the same sessions prefer the QNN execution provider so the
Hexagon NPU runs the graph. Heavier Qualcomm AI Hub assets (Whisper-Small,
MobileNet-v2, YOLOv7, Llama-3.2-3B) plug in beside this control plane.
"""

from functools import lru_cache

import numpy as np
import onnx
import onnxruntime as ort
from onnx import TensorProto, helper, numpy_helper

from edith.runtime import execution_providers


def build_linear_softmax(name: str, weight: np.ndarray, bias: np.ndarray) -> onnx.ModelProto:
    classes, features = weight.shape
    weight_init = numpy_helper.from_array(np.ascontiguousarray(weight, dtype=np.float32), name="W")
    bias_init = numpy_helper.from_array(
        np.ascontiguousarray(bias, dtype=np.float32).reshape(1, classes),
        name="B",
    )
    graph = helper.make_graph(
        nodes=[
            helper.make_node("Gemm", ["input", "W", "B"], ["logits"], transB=1),
            helper.make_node("Softmax", ["logits"], ["probabilities"], axis=1),
        ],
        name=name,
        inputs=[helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, features])],
        outputs=[helper.make_tensor_value_info("probabilities", TensorProto.FLOAT, [1, classes])],
        initializer=[weight_init, bias_init],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model


INTENT_LABELS = ("transcribe", "vision", "chat", "summarize", "code")
VISION_LABELS = ("document", "photo", "diagram")
SPEECH_LABELS = ("silence", "speech", "noise")


def intent_model() -> onnx.ModelProto:
    weight = np.diag([3.0, 3.0, 3.0, 3.0, 3.0]).astype(np.float32)
    bias = np.array([0.0, 0.0, 0.4, 0.0, 0.0], dtype=np.float32)
    return build_linear_softmax("edith_intent", weight, bias)


def vision_model() -> onnx.ModelProto:
    # Features: mean luma, mean saturation, edge strength, white ratio.
    weight = np.array(
        [
            [0.0, -3.0, 0.0, 5.0],
            [0.2, 5.0, 0.0, -1.0],
            [0.0, -2.0, 5.0, -1.0],
        ],
        dtype=np.float32,
    )
    bias = np.zeros(3, dtype=np.float32)
    return build_linear_softmax("edith_vision_gate", weight, bias)


def speech_model() -> onnx.ModelProto:
    # Features: rms, zero-crossing rate, speech-band energy, noise-band energy.
    weight = np.array(
        [
            [-4.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 8.0, -2.0],
            [0.0, 0.0, -1.0, 8.0],
        ],
        dtype=np.float32,
    )
    bias = np.array([0.15, 0.0, 0.0], dtype=np.float32)
    return build_linear_softmax("edith_speech_activity", weight, bias)


class OnnxClassifier:
    def __init__(self, name: str, labels: tuple[str, ...], model: onnx.ModelProto) -> None:
        self.name = name
        self.labels = labels
        self.session = ort.InferenceSession(model.SerializeToString(), providers=execution_providers())
        self.providers = list(self.session.get_providers())

    def predict(self, features: np.ndarray) -> tuple[str, float, dict[str, float]]:
        array = np.asarray(features, dtype=np.float32).reshape(1, -1)
        probabilities = self.session.run(None, {"input": array})[0][0]
        index = int(np.argmax(probabilities))
        scores = {label: float(probabilities[i]) for i, label in enumerate(self.labels)}
        return self.labels[index], scores[self.labels[index]], scores


@lru_cache(maxsize=1)
def intent_classifier() -> OnnxClassifier:
    return OnnxClassifier("edith_intent", INTENT_LABELS, intent_model())


@lru_cache(maxsize=1)
def vision_classifier() -> OnnxClassifier:
    return OnnxClassifier("edith_vision_gate", VISION_LABELS, vision_model())


@lru_cache(maxsize=1)
def speech_classifier() -> OnnxClassifier:
    return OnnxClassifier("edith_speech_activity", SPEECH_LABELS, speech_model())
