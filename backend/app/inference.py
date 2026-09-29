"""Inference backends.

The active backend is whatever can actually run. A missing NPU, a missing
ONNX file, or a failed session load is reported as such and the rule engine
takes the request.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .paths import MODEL_MANIFEST, REPO_ROOT
from .settings import Settings, load_settings


@dataclass
class EngineStatus:
    backend_id: str
    label: str
    level: str
    model: str
    precision: str
    execution: str
    network: str
    detail: str
    npu_active: bool
    npu_library_present: bool
    onnx_installed: bool
    onnx_providers: list[str] = field(default_factory=list)
    cloud_allowed: bool = False
    cloud_configured: bool = False
    model_loaded: bool = False
    telemetry_note: str = "Telemetry unavailable"
    rule_engine_latency_ms: float | None = None

    def as_dict(self) -> dict:
        return {
            "backend_id": self.backend_id,
            "label": self.label,
            "level": self.level,
            "model": self.model,
            "precision": self.precision,
            "execution": self.execution,
            "network": self.network,
            "detail": self.detail,
            "npu_active": self.npu_active,
            "npu_library_present": self.npu_library_present,
            "onnx_installed": self.onnx_installed,
            "onnx_providers": self.onnx_providers,
            "cloud_allowed": self.cloud_allowed,
            "cloud_configured": self.cloud_configured,
            "model_loaded": self.model_loaded,
            "telemetry": {
                "inference_latency_ms": None,
                "tokens_per_sec": None,
                "cpu_utilization_pct": None,
                "npu_utilization_pct": None,
                "memory_mb": None,
                "note": self.telemetry_note,
            },
            "rule_engine_latency_ms": self.rule_engine_latency_ms,
        }


_LAST_LATENCY_MS: float | None = None


def note_latency(ms: float) -> None:
    global _LAST_LATENCY_MS
    _LAST_LATENCY_MS = round(ms, 2)


def _qnn_library_present() -> bool:
    if shutil.which("qnn-net-run") or shutil.which("qnn-context-binary-generator"):
        return True
    candidates = [
        Path("/usr/lib/libQnnHtp.so"),
        Path("/usr/local/lib/libQnnHtp.so"),
        Path("/opt/qcom/aistack/lib/x86_64-linux-clang/libQnnHtp.so"),
        REPO_ROOT / "models" / "libQnnHtp.so",
    ]
    return any(path.is_file() for path in candidates)


def _onnx_providers() -> tuple[bool, list[str]]:
    try:
        import onnxruntime as ort  # type: ignore
    except Exception:
        return False, []
    try:
        return True, list(ort.get_available_providers())
    except Exception:
        return True, []


def model_rows() -> list[dict]:
    manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    rows = []
    for item in manifest["models"]:
        row = dict(item)
        rel = item.get("path")
        if rel:
            path = REPO_ROOT / rel
            row["installed"] = path.is_file()
            row["size_bytes"] = path.stat().st_size if path.is_file() else None
            row["status"] = "installed" if path.is_file() else "not-installed"
        else:
            row["installed"] = item.get("status") == "active"
        rows.append(row)
    return rows


def _try_onnx_session(providers: list[str]) -> tuple[bool, str]:
    """Return whether a generative session is actually usable.

    Loading an arbitrary graph is not enough to answer RTL questions, and a
    missing tokenizer means we still cannot decode tokens. The function only
    reports a live session when both the graph and a tokenizer vocabulary exist.
    """
    model = REPO_ROOT / "models" / "model.onnx"
    vocab = REPO_ROOT / "models" / "tokenizer"
    if not model.is_file():
        return False, "models/model.onnx is not installed."
    if not any(vocab.glob("*")):
        return False, "models/model.onnx is present but models/tokenizer is empty."
    try:
        import onnxruntime as ort  # type: ignore
    except Exception as exc:
        return False, f"ONNX Runtime failed to import: {exc}"
    prefer = [p for p in ("QNNExecutionProvider", "CPUExecutionProvider") if p in providers]
    if not prefer:
        prefer = providers[:1]
    try:
        ort.InferenceSession(str(model), providers=prefer or None)
    except Exception as exc:
        return False, f"ONNX session was not created: {exc}"
    return False, (
        "ONNX session creation is not used for text generation yet. "
        "A generative decode loop is not bundled, so HEXA-R stays on the rule engine."
    )


def engine_status(settings: Settings | None = None) -> EngineStatus:
    settings = settings or load_settings()
    onnx_installed, providers = _onnx_providers()
    npu_lib = _qnn_library_present()
    qnn_provider = "QNNExecutionProvider" in providers
    loaded, load_detail = _try_onnx_session(providers)
    npu_active = bool(loaded and qnn_provider and settings.backend_preference in {"auto", "qnn"})

    if npu_active:
        return EngineStatus(
            backend_id="qnn",
            label="Snapdragon NPU — Active",
            level="npu",
            model="ONNX model",
            precision="model file",
            execution="On-device",
            network="Offline",
            detail="Qualcomm QNN execution provider accepted a session.",
            npu_active=True,
            npu_library_present=True,
            onnx_installed=onnx_installed,
            onnx_providers=providers,
            cloud_allowed=settings.allow_cloud,
            cloud_configured=False,
            model_loaded=True,
            rule_engine_latency_ms=_LAST_LATENCY_MS,
        )

    detail_parts = [
        "Qualcomm NPU backend is not active. HEXA-R is using the on-device RTL rule engine.",
        "Static analysis and simulation do not need a language model.",
    ]
    if not onnx_installed:
        detail_parts.append("ONNX Runtime is not installed.")
    else:
        detail_parts.append("ONNX Runtime providers: " + (", ".join(providers) or "none") + ".")
    if not npu_lib and not qnn_provider:
        detail_parts.append("No Qualcomm QNN library or QNNExecutionProvider was detected.")
    elif qnn_provider and not loaded:
        detail_parts.append(load_detail)
    else:
        detail_parts.append(load_detail)
    if settings.allow_cloud:
        detail_parts.append(
            "Cloud AI is allowed in settings, but no cloud provider is configured. Requests stay on device."
        )

    return EngineStatus(
        backend_id="rule-engine",
        label="CPU fallback",
        level="fallback",
        model="HEXA-R RTL Analyst",
        precision="deterministic",
        execution="On-device",
        network="Offline",
        detail=" ".join(detail_parts),
        npu_active=False,
        npu_library_present=npu_lib or qnn_provider,
        onnx_installed=onnx_installed,
        onnx_providers=providers,
        cloud_allowed=settings.allow_cloud,
        cloud_configured=False,
        model_loaded=False,
        rule_engine_latency_ms=_LAST_LATENCY_MS,
    )


class timed:
    def __enter__(self) -> "timed":
        self._t = time.perf_counter()
        return self

    def __exit__(self, *_) -> None:
        note_latency((time.perf_counter() - self._t) * 1000)
