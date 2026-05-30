#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-python}"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$PWD/.pyinstaller}"
"$PYTHON_BIN" -m pip install -r requirements.txt -r requirements-build.txt
"$PYTHON_BIN" -m PyInstaller --clean --noconfirm packaging/personal_finance_app.spec

echo "Built macOS app in dist/Personal Finance.app"
