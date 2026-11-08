#!/usr/bin/env sh
set -eu
python3 install-model-runtime.py --backend "${KITTYSEARCH_INFERENCE_BACKEND:-cpu}" --cuda-version "${KITTYSEARCH_CUDA_VERSION:-cu124}"
python3 -m pip install -r requirements-build.txt
python3 -m PyInstaller --noconfirm --clean --onefile --name KITTYSEARCH --console --collect-all llama_cpp --add-data "assets:assets" kittysearch.py
printf '%s\n' 'Linux executable created at dist/KITTYSEARCH'
