from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMPORTS_DIR = PROJECT_ROOT / "imports"
TO_IMPORT_DIR = IMPORTS_DIR / "to_import"
PROCESSED_DIR = IMPORTS_DIR / "processed"
FAILED_DIR = IMPORTS_DIR / "failed"
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "finance.duckdb"
RULES_DIR = PROJECT_ROOT / "rules"
MERCHANT_RULES_PATH = RULES_DIR / "merchant_rules.yml"
SOURCE_RULES_PATH = RULES_DIR / "source_rules.yml"


def ensure_project_dirs() -> None:
    for path in (TO_IMPORT_DIR, PROCESSED_DIR, FAILED_DIR, DATA_DIR, RULES_DIR):
        path.mkdir(parents=True, exist_ok=True)
