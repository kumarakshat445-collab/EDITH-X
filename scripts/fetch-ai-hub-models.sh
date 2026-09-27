#!/usr/bin/env bash
set -euo pipefail

if ! command -v qai-hub-models >/dev/null 2>&1; then
  echo "Install the catalog CLI first: pip install qai_hub_models_cli" >&2
  exit 1
fi

chipset="${EDITH_CHIPSET:-qualcomm-snapdragon-x-elite}"
out="${1:-models/snapdragon}"
mkdir -p "$out"

qai-hub-models fetch whisper_small --runtime qnn --precision w8a8 --chipset "$chipset"
qai-hub-models fetch mobilenet_v2 --runtime qnn --precision w8a8 --chipset "$chipset"
qai-hub-models fetch yolov7 --runtime qnn --precision w8a8 --chipset "$chipset"

echo "Llama-3.2-3B chat is exported through AI Hub Workbench:"
echo "python -m qai_hub_models.models.llama_v3_2_3b_chat_quantized.export --device \"Snapdragon X Elite CRD\" --skip-inferencing --skip-profiling"
echo "Place downloaded assets in $out"
