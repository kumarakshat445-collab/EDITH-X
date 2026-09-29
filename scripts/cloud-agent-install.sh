#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# python3 -m venv needs ensurepip, which Ubuntu ships in python3-venv.
if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv
fi

# A failed venv create leaves a directory without pip. Recreate it.
if [[ ! -x .venv/bin/python ]] || ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  rm -rf .venv
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
