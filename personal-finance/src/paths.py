import os
import shutil
import sys
from pathlib import Path


APP_NAME = "Personal Finance Automation"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
BUNDLED_RULES_DIR = BUNDLED_ROOT / "rules"
BUNDLED_MIGRATIONS_DIR = BUNDLED_ROOT / "migrations"


def is_packaged_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def default_user_data_root() -> Path:
    override = os.environ.get("PERSONAL_FINANCE_HOME")
    if override:
        return Path(override).expanduser()

    if not is_packaged_app():
        return PROJECT_ROOT

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "personal-finance"


APP_DATA_ROOT = default_user_data_root()
IMPORTS_DIR = APP_DATA_ROOT / "imports"
TO_IMPORT_DIR = IMPORTS_DIR / "to_import"
PROCESSED_DIR = IMPORTS_DIR / "processed"
FAILED_DIR = IMPORTS_DIR / "failed"
DATA_DIR = APP_DATA_ROOT / "data"
DB_PATH = DATA_DIR / "finance.duckdb"
RULES_DIR = APP_DATA_ROOT / "rules"
MERCHANT_RULES_PATH = RULES_DIR / "merchant_rules.yml"
SOURCE_RULES_PATH = RULES_DIR / "source_rules.yml"
ADMIN_CLASSIFICATION_RULES_PATH = RULES_DIR / "admin_classification_rules.yml"
ADMIN_SOURCE_RULES_PATH = RULES_DIR / "admin_source_rules.yml"


def ensure_project_dirs() -> None:
    for path in (TO_IMPORT_DIR, PROCESSED_DIR, FAILED_DIR, DATA_DIR, RULES_DIR):
        path.mkdir(parents=True, exist_ok=True)
    seed_rule_file("source_rules.yml")
    seed_rule_file("merchant_rules.yml")
    seed_rule_file("admin_classification_rules.example.yml")
    seed_rule_file("admin_source_rules.example.yml")


def seed_rule_file(filename: str) -> None:
    source = BUNDLED_RULES_DIR / filename
    destination = RULES_DIR / filename
    if source.exists() and not destination.exists():
        shutil.copy2(source, destination)
