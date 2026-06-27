#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

HOST_PYTHON="${PYTHON_BIN:-python3}"
BUILD_VENV="${BUILD_VENV:-$PWD/.build-venv}"
BUILD_PYTHON="$BUILD_VENV/bin/python"
APP_PATH="dist/Credit Card Due.app"

case "$(uname -m)" in
    arm64)
        ARCH_LABEL="Apple-Silicon"
        ;;
    x86_64)
        ARCH_LABEL="Intel"
        ;;
    *)
        echo "Unsupported macOS architecture: $(uname -m)" >&2
        exit 1
        ;;
esac

ZIP_PATH="dist/Credit Card Due-macOS-${ARCH_LABEL}.zip"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$PWD/.pyinstaller}"

if [[ ! -x "$BUILD_PYTHON" ]]; then
    "$HOST_PYTHON" -m venv --copies "$BUILD_VENV"
fi

"$BUILD_PYTHON" -m pip install -r requirements.txt -r requirements-build.txt
"$BUILD_PYTHON" -m PyInstaller \
    --clean \
    --noconfirm \
    packaging/credit_card_widget.spec

SMOKE_HOME="$(mktemp -d)"
export SMOKE_HOME
trap 'rm -rf "$SMOKE_HOME"' EXIT

HOME="$SMOKE_HOME" \
    CREDIT_CARD_WIDGET_SMOKE_SEED=1 \
    QT_QPA_PLATFORM=offscreen \
    "$APP_PATH/Contents/MacOS/CreditCardDue" \
    --smoke-test

SMOKE_DB="$SMOKE_HOME/Library/Application Support/Credit Card Due/cards.duckdb"
if [[ ! -f "$SMOKE_DB" ]]; then
    echo "Packaged app did not create its per-user database." >&2
    exit 1
fi

if [[ -n "${APPLE_SIGNING_IDENTITY:-}" ]]; then
    codesign --verify --deep --strict "$APP_PATH"
fi

rm -f "dist/Credit Card Due-macOS.zip" "$ZIP_PATH"
ditto -c -k --sequesterRsrc --keepParent \
    "$APP_PATH" \
    "$ZIP_PATH"

if [[ -n "${APPLE_ID:-}" && -n "${APPLE_TEAM_ID:-}" && -n "${APPLE_APP_PASSWORD:-}" ]]; then
    if [[ -z "${APPLE_SIGNING_IDENTITY:-}" ]]; then
        echo "Notarization requires APPLE_SIGNING_IDENTITY." >&2
        exit 1
    fi

    xcrun notarytool submit "$ZIP_PATH" \
        --apple-id "$APPLE_ID" \
        --team-id "$APPLE_TEAM_ID" \
        --password "$APPLE_APP_PASSWORD" \
        --wait
    xcrun stapler staple "$APP_PATH"
    xcrun stapler validate "$APP_PATH"

    rm -f "$ZIP_PATH"
    ditto -c -k --sequesterRsrc --keepParent \
        "$APP_PATH" \
        "$ZIP_PATH"
fi

echo "Built: $APP_PATH"
echo "Share: $ZIP_PATH"
