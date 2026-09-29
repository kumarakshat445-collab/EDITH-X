#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v iverilog >/dev/null 2>&1 || ! command -v yosys >/dev/null 2>&1 || ! command -v verilator >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq iverilog verilator yosys python3-venv
  fi
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt

if [[ -f frontend/package.json ]]; then
  (cd frontend && npm install)
fi
