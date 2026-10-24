#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -x .venv/bin/pip ]]; then
  if ! python3 -m venv .venv; then
    sudo apt-get update
    sudo apt-get install -y python3-venv
    python3 -m venv .venv
  fi
fi

# shellcheck source=/dev/null
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
