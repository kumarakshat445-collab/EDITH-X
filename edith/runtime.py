"""ONNX Runtime sessions aimed at Snapdragon HP PCs.

Windows on Arm laptops such as the HP Omnibook 3 and Omnibook Ultra expose
the Hexagon NPU through the Qualcomm AI Engine Direct execution provider
(QNNExecutionProvider). Other machines use the CPU provider so the same
graphs still run for development and tests.
"""

import os
import platform

import onnxruntime as ort

from edith.catalog import HP_REFERENCE_PCS, TARGET_CHIPSETS


def snapdragon_pc() -> bool:
    override = os.environ.get("EDITH_SNAPDRAGON_PC", "").strip().lower()
    if override in {"1", "true", "yes"}:
        return True
    if override in {"0", "false", "no"}:
        return False
    system = platform.system().lower()
    machine = platform.machine().lower()
    return system == "windows" and machine in {"arm64", "aarch64"}


def qnn_backend_path() -> str:
    return os.environ.get("QNN_BACKEND_PATH", "QnnHtp.dll")


def execution_providers() -> list[str | tuple[str, dict[str, str]]]:
    available = set(ort.get_available_providers())
    if "QNNExecutionProvider" not in available:
        return ["CPUExecutionProvider"]
    return [
        ("QNNExecutionProvider", {"backend_path": qnn_backend_path()}),
        "CPUExecutionProvider",
    ]


def device_profile(active_providers: list[str] | None = None) -> dict[str, object]:
    providers = active_providers or ["CPUExecutionProvider"]
    using_npu = any(provider.startswith("QNN") for provider in providers)
    return {
        "os": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "snapdragon_pc": snapdragon_pc(),
        "npu_active": using_npu,
        "execution_providers": providers,
        "ort_available_providers": list(ort.get_available_providers()),
        "qnn_backend_path": qnn_backend_path() if using_npu else None,
        "target_chipsets": list(TARGET_CHIPSETS),
        "hp_reference_pcs": list(HP_REFERENCE_PCS),
        "binary_compatibility": (
            "Snapdragon X Elite context binaries also run on Snapdragon X and X Plus PCs. "
            "For Snapdragon X2, confirm the chipset id with `qai-hub-models chipsets` before fetching."
        ),
        "deployment_note": (
            "Compile Qualcomm AI Hub assets with x64 Python, then run the QNN "
            "context binary on the Snapdragon PC. Qualcomm AI Hub Models does not "
            "support Windows ARM64 Python for the compile step."
        ),
    }
