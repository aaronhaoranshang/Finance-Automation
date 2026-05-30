Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
if (-not $env:PYINSTALLER_CONFIG_DIR) {
    $env:PYINSTALLER_CONFIG_DIR = Join-Path (Get-Location) ".pyinstaller"
}
& $PythonBin -m pip install -r requirements.txt -r requirements-build.txt
& $PythonBin -m PyInstaller --clean --noconfirm packaging\personal_finance_app.spec

Write-Host "Built Windows app in dist\PersonalFinance\PersonalFinance.exe"
