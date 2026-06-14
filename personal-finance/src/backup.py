from __future__ import annotations

import json
import logging
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import duckdb

from paths import BACKUPS_DIR, DB_PATH, ensure_project_dirs


logger = logging.getLogger(__name__)


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_database_file(
    db_path: Path = DB_PATH,
    backups_dir: Path = BACKUPS_DIR,
    reason: str = "backup",
) -> Path:
    ensure_project_dirs()
    if not db_path.exists():
        raise FileNotFoundError(f"Database file does not exist: {db_path}")

    safe_reason = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in reason).strip("_")
    destination = backups_dir / f"finance_{safe_reason or 'backup'}_{timestamp()}.duckdb"
    shutil.copy2(db_path, destination)
    return destination


def export_backup(
    db_path: Path = DB_PATH,
    backups_dir: Path = BACKUPS_DIR,
    include_metadata: bool = True,
) -> Path:
    ensure_project_dirs()
    if not db_path.exists():
        raise FileNotFoundError(f"Database file does not exist: {db_path}")

    backup_path = backups_dir / f"finance_backup_{timestamp()}.zip"
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(db_path, arcname="finance.duckdb")
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "app": "Personal Finance Automation",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "database_file": "finance.duckdb",
                    "metadata_included": include_metadata,
                },
                indent=2,
            ),
        )
        if include_metadata:
            write_metadata_exports(archive, db_path)
    return backup_path


def write_metadata_exports(archive: zipfile.ZipFile, db_path: Path) -> None:
    metadata_queries = {
        "metadata/import_batch.csv": "SELECT * FROM import_batch ORDER BY imported_at DESC",
        "metadata/raw_import_row.csv": "SELECT * FROM raw_import_row ORDER BY import_batch_id, row_number",
        "metadata/merchant_rule.csv": "SELECT * FROM merchant_rule ORDER BY owner_type, priority, rule_id",
        "metadata/category_master.csv": "SELECT * FROM category_master ORDER BY category, subcategory, owner_type",
    }
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            for arcname, query in metadata_queries.items():
                archive.writestr(arcname, con.execute(query).df().to_csv(index=False))
        finally:
            con.close()
    except Exception as exc:
        logger.warning("Could not include metadata exports in backup: %s", exc)
        archive.writestr("metadata/export_warning.txt", f"Metadata export failed: {exc}")


def restore_backup(
    backup_bytes: bytes,
    db_path: Path = DB_PATH,
) -> Path | None:
    ensure_project_dirs()
    rollback_backup = backup_database_file(db_path, reason="pre_restore") if db_path.exists() else None
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "uploaded_backup"
        temp_path.write_bytes(backup_bytes)
        restored_db = extract_database_from_backup(temp_path)
        try:
            shutil.copy2(restored_db, db_path)
        except Exception:
            if rollback_backup and rollback_backup.exists():
                shutil.copy2(rollback_backup, db_path)
            raise
    return rollback_backup


def extract_database_from_backup(path: Path) -> Path:
    if zipfile.is_zipfile(path):
        extract_dir = path.parent / "extract"
        with zipfile.ZipFile(path) as archive:
            candidates = [
                name
                for name in archive.namelist()
                if Path(name).name in {"finance.duckdb", "finance.db"}
                or Path(name).suffix in {".duckdb", ".db"}
            ]
            if not candidates:
                raise ValueError("Backup zip does not contain a DuckDB database file.")
            archive.extract(candidates[0], extract_dir)
            return extract_dir / candidates[0]
    return path
