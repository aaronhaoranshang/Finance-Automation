# Build with:
#   python -m PyInstaller --clean --noconfirm packaging/credit_card_widget.spec
from __future__ import annotations

import sys
import os
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata


project_root = Path(SPECPATH).resolve().parent
app_version = os.environ.get("APP_VERSION", "1.0.2")
bundle_identifier = os.environ.get(
    "BUNDLE_IDENTIFIER",
    "com.creditcarddue.desktop",
)
signing_identity = os.environ.get("APPLE_SIGNING_IDENTITY") or None

datas = []
try:
    datas += copy_metadata("duckdb")
except Exception:
    pass

a = Analysis(
    [str(project_root / "app.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    # DuckDB's native extension imports uuid dynamically while converting
    # result values, so static analysis cannot discover it.
    hiddenimports=["uuid"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CreditCardDue",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=signing_identity,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CreditCardDue",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Credit Card Due.app",
        icon=None,
        bundle_identifier=bundle_identifier,
        version=app_version,
        info_plist={
            "CFBundleDisplayName": "Credit Card Due",
            "CFBundleShortVersionString": app_version,
            "LSApplicationCategoryType": "public.app-category.finance",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
        },
    )
