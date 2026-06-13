from __future__ import annotations

from pathlib import Path

import duckdb

from paths import BUNDLED_MIGRATIONS_DIR


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
) -> list[str]:
    if not migrations_dir.exists():
        raise FileNotFoundError(f"Migrations directory not found: {migrations_dir}")

    ensure_schema_migrations_table(con)
    applied_versions = {
        row[0]
        for row in con.execute("SELECT version FROM schema_migrations").fetchall()
    }

    applied_now: list[str] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        version = path.stem.split("_", 1)[0]
        if version in applied_versions:
            continue

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
            raise
        applied_now.append(path.name)

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
