#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
BACKEND="${KITTYSEARCH_INFERENCE_BACKEND:-cpu}"
CUDA_VERSION="${KITTYSEARCH_CUDA_VERSION:-cu124}"

cd "$SCRIPT_DIR"
"$PYTHON" install-model-runtime.py --backend "$BACKEND" --cuda-version "$CUDA_VERSION"
"$PYTHON" -m pip install -r requirements-build.txt
"$PYTHON" -m PyInstaller --noconfirm --clean --onefile --name KITTYSEARCH \
  --console --collect-all llama_cpp --add-data "assets:assets" kittysearch.py
printf 'Linux executable created at %s\n' "$SCRIPT_DIR/dist/KITTYSEARCH"
