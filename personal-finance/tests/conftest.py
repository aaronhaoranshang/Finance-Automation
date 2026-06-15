from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
LOCAL_MODULES = [
    "app",
    "backup",
    "categorize",
    "db",
    "finance",
    "ingest",
    "metadata",
    "migrations",
    "normalize",
    "paths",
    "pdf_extract",
    "reclassify",
    "source_admin",
    "source_metadata",
    "services",
    "services.backup_service",
    "services.category_service",
    "services.dashboard_service",
    "services.import_service",
    "services.review_service",
    "services.rule_service",
    "services.transaction_service",
    "ui",
    "ui.components",
    "ui.constants",
    "ui.theme",
    "ui.pages",
    "ui.pages.audit",
    "ui.pages.category_breakdown",
    "ui.pages.drilldown",
    "ui.pages.imports",
    "ui.pages.merchant_rules",
    "ui.pages.merchants",
    "ui.pages.monthly_detail",
    "ui.pages.overview",
    "ui.pages.recurring",
    "ui.pages.review_queue",
    "ui.pages.settings",
    "ui.pages.setup",
    "ui.pages.transactions",
    "watcher",
]


@pytest.fixture()
def app_modules(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    monkeypatch.setenv("PERSONAL_FINANCE_HOME", str(tmp_path / "app_home"))
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    for module_name in LOCAL_MODULES:
        sys.modules.pop(module_name, None)

    loaded = {
        "paths": importlib.import_module("paths"),
        "db": importlib.import_module("db"),
        "metadata": importlib.import_module("metadata"),
        "categorize": importlib.import_module("categorize"),
        "normalize": importlib.import_module("normalize"),
        "ingest": importlib.import_module("ingest"),
        "reclassify": importlib.import_module("reclassify"),
        "backup": importlib.import_module("backup"),
    }
    return SimpleNamespace(**loaded)
