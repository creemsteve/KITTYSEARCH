#!/usr/bin/env sh
set -eu
python3 -m pip install -r requirements-build.txt
python3 -m PyInstaller --noconfirm --clean --onefile --name kittysearch --console kittysearch.py
printf '%s\n' 'Linux executable created at dist/kittysearch'
