# Build with:
#   pyinstaller --clean --noconfirm packaging/personal_finance_app.spec
from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


project_root = Path.cwd()

datas = [
    (str(project_root / "src"), "src"),
    (str(project_root / "migrations"), "migrations"),
    (str(project_root / "rules" / "source_rules.yml"), "rules"),
    (str(project_root / "rules" / "merchant_rules.yml"), "rules"),
    (str(project_root / "rules" / "admin_classification_rules.example.yml"), "rules"),
    (str(project_root / "rules" / "admin_source_rules.example.yml"), "rules"),
]
datas += collect_data_files("streamlit")
datas += collect_data_files("plotly")
datas += collect_data_files("pyarrow")

metadata_packages = [
    "streamlit",
    "pandas",
    "duckdb",
    "plotly",
    "rapidfuzz",
    "watchdog",
    "pdfplumber",
    "pyyaml",
]
for package in metadata_packages:
    try:
        datas += copy_metadata(package)
    except Exception:
        pass

hiddenimports = []
for package in ["streamlit", "plotly", "duckdb", "pdfplumber", "watchdog", "rapidfuzz", "yaml", "openpyxl"]:
    hiddenimports += collect_submodules(package)

a = Analysis(
    [str(project_root / "desktop_app.py")],
    pathex=[str(project_root), str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PersonalFinance",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name="PersonalFinance",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Personal Finance.app",
        icon=None,
        bundle_identifier="local.personalfinance.app",
    )
