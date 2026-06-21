#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

HOST_PYTHON="${PYTHON_BIN:-python3}"
BUILD_VENV="${BUILD_VENV:-$PWD/.build-venv}"
BUILD_PYTHON="$BUILD_VENV/bin/python"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$PWD/.pyinstaller}"

if [[ ! -x "$BUILD_PYTHON" ]]; then
    "$HOST_PYTHON" -m venv --copies "$BUILD_VENV"
fi

"$BUILD_PYTHON" -m pip install -r requirements.txt -r requirements-build.txt
"$BUILD_PYTHON" -m PyInstaller \
    --clean \
    --noconfirm \
    packaging/credit_card_widget.spec

SMOKE_DIR="$(mktemp -d)"
trap 'rm -rf "$SMOKE_DIR"' EXIT
export CREDIT_CARD_WIDGET_DB_PATH="$SMOKE_DIR/cards.duckdb"

"$BUILD_PYTHON" - <<'PY'
from datetime import date

from db import add_card, init_db

today = date.today()
init_db()
add_card(
    "Packaging Smoke Test",
    today.day,
    6 if today.day >= 6 else 25,
    5,
    today=today,
)
PY

QT_QPA_PLATFORM=offscreen \
    "dist/Credit Card Due.app/Contents/MacOS/CreditCardDue" \
    --smoke-test

unset CREDIT_CARD_WIDGET_DB_PATH

rm -f "dist/Credit Card Due-macOS.zip"
ditto -c -k --sequesterRsrc --keepParent \
    "dist/Credit Card Due.app" \
    "dist/Credit Card Due-macOS.zip"

echo "Built: dist/Credit Card Due.app"
echo "Share: dist/Credit Card Due-macOS.zip"
