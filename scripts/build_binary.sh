#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .local/build-venv
.local/build-venv/bin/python -m pip install -r requirements.txt 'pyinstaller>=6.11,<7'
npm ci
npm run build
.local/build-venv/bin/python -m PyInstaller --clean --noconfirm work_hours.spec
