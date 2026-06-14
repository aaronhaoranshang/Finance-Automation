from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from backup import backup_database_file
from paths import BUNDLED_MIGRATIONS_DIR


logger = logging.getLogger(__name__)

REQUIRED_METADATA_TABLES = [
    "schema_migrations",
    "transaction_type_master",
    "category_master",
    "merchant_rule",
    "source_profile",
    "source_detection_rule",
    "source_column_mapping",
    "import_batch",
    "raw_import_row",
    "transaction_classification_audit",
]


def run_migrations(
    con: duckdb.DuckDBPyConnection,
    migrations_dir: Path = BUNDLED_MIGRATIONS_DIR,
    db_path: Path | None = None,
    backup_before_migrations: bool = True,
) -> list[str]:
    if not migrations_dir.exists():
        raise FileNotFoundError(f"Migrations directory not found: {migrations_dir}")

    existing_tables = {
        row[0]
        for row in con.execute("SHOW TABLES").fetchall()
    }
    ensure_schema_migrations_table(con)
    applied_versions = {
        row[0]
        for row in con.execute("SELECT version FROM schema_migrations").fetchall()
    }
    pending_paths = [
        path
        for path in sorted(migrations_dir.glob("*.sql"))
        if path.stem.split("_", 1)[0] not in applied_versions
    ]
    if backup_before_migrations and db_path is not None and db_path.exists() and existing_tables and pending_paths:
        try:
            con.execute("CHECKPOINT")
            backup_path = backup_database_file(db_path, reason="pre_migration")
            logger.info("Created pre-migration database backup: %s", backup_path)
        except Exception as exc:
            logger.exception("Could not create pre-migration backup for %s", db_path)
            raise RuntimeError(f"Could not create a database backup before migration: {exc}") from exc

    applied_now: list[str] = []
    for path in pending_paths:
        version = path.stem.split("_", 1)[0]

        sql = path.read_text(encoding="utf-8")
        con.execute("BEGIN")
        try:
            con.execute(sql)
            con.execute(
                """
                INSERT INTO schema_migrations (version, filename)
                VALUES (?, ?)
                """,
                [version, path.name],
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            logger.exception("Migration failed: %s", path.name)
            raise
        applied_now.append(path.name)
        logger.info("Applied migration: %s", path.name)

    return applied_now


def ensure_schema_migrations_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )


def verify_metadata_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    existing_tables = {
        row[0]
        for row in con.execute("SHOW TABLES").fetchall()
    }
    return [table for table in REQUIRED_METADATA_TABLES if table not in existing_tables]
