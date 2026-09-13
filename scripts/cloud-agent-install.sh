#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r backend/requirements.txt

if command -v npm >/dev/null 2>&1; then
  cd frontend
  npm ci 2>/dev/null || npm install
fi
