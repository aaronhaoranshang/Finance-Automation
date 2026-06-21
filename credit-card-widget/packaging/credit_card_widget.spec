# Build with:
#   python -m PyInstaller --clean --noconfirm packaging/credit_card_widget.spec
from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata


project_root = Path.cwd()

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
    codesign_identity=None,
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
        bundle_identifier="com.aaronshang.creditcarddue",
        info_plist={
            "CFBundleDisplayName": "Credit Card Due",
            "CFBundleShortVersionString": "1.0.1",
            "NSHighResolutionCapable": True,
        },
    )
