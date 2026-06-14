from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from migrations import run_migrations, verify_metadata_tables
from paths import DB_PATH, ensure_project_dirs


TRANSACTION_COLUMNS = [
    "transaction_id",
    "transaction_date",
    "posted_date",
    "institution",
    "account_name",
    "merchant_raw",
    "merchant_clean",
    "amount",
    "transaction_type",
    "scope",
    "currency",
    "category",
    "subcategory",
    "source_file",
    "ingested_at",
]


def connect(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    ensure_project_dirs()
    database_existed = db_path.exists() and db_path.stat().st_size > 0
    con = duckdb.connect(str(db_path))
    init_db(con, db_path=db_path, backup_before_migrations=database_existed)
    return con


def init_db(
    con: duckdb.DuckDBPyConnection,
    db_path: Path | None = None,
    backup_before_migrations: bool = True,
) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id VARCHAR PRIMARY KEY,
            transaction_date DATE,
            posted_date DATE,
            institution VARCHAR,
            account_name VARCHAR,
            merchant_raw VARCHAR,
            merchant_clean VARCHAR,
            amount DECIMAL(18, 2),
            transaction_type VARCHAR,
            scope VARCHAR,
            currency VARCHAR,
            category VARCHAR,
            subcategory VARCHAR,
            source_file VARCHAR,
            ingested_at TIMESTAMP
        )
        """
    )
    ensure_column(con, "transactions", "transaction_type", "VARCHAR")
    ensure_column(con, "transactions", "scope", "VARCHAR DEFAULT 'personal'")
    ensure_column(con, "transactions", "manual_override", "BOOLEAN DEFAULT FALSE")
    ensure_column(con, "transactions", "category_manual_override", "BOOLEAN DEFAULT FALSE")
    ensure_column(con, "transactions", "type_manual_override", "BOOLEAN DEFAULT FALSE")
    ensure_column(con, "transactions", "merchant_manual_override", "BOOLEAN DEFAULT FALSE")
    con.execute("UPDATE transactions SET scope = 'personal' WHERE scope IS NULL OR scope = ''")
    con.execute("UPDATE transactions SET manual_override = FALSE WHERE manual_override IS NULL")
    con.execute(
        """
        UPDATE transactions
        SET
            category_manual_override = COALESCE(category_manual_override, manual_override, FALSE),
            type_manual_override = COALESCE(type_manual_override, manual_override, FALSE),
            merchant_manual_override = COALESCE(merchant_manual_override, manual_override, FALSE)
        WHERE category_manual_override IS NULL
           OR type_manual_override IS NULL
           OR merchant_manual_override IS NULL
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS import_log (
            source_file VARCHAR,
            status VARCHAR,
            rows_seen INTEGER,
            rows_inserted INTEGER,
            message VARCHAR,
            imported_at TIMESTAMP DEFAULT now()
        )
        """
    )
    run_migrations(con, db_path=db_path, backup_before_migrations=backup_before_migrations)


def ensure_column(con: duckdb.DuckDBPyConnection, table_name: str, column_name: str, data_type: str) -> None:
    columns = con.execute(f"PRAGMA table_info('{table_name}')").df()["name"].tolist()
    if column_name not in columns:
        con.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {data_type}")


def verify_schema(con: duckdb.DuckDBPyConnection) -> list[str]:
    return verify_metadata_tables(con)


def save_app_setting(con: duckdb.DuckDBPyConnection, setting_key: str, setting_value: str) -> None:
    con.execute(
        """
        INSERT INTO app_setting (setting_key, setting_value)
        VALUES (?, ?)
        ON CONFLICT (setting_key) DO UPDATE
        SET
            setting_value = excluded.setting_value,
            updated_at = now()
        """,
        [setting_key, setting_value],
    )


def load_app_settings(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    if "app_setting" not in {row[0] for row in con.execute("SHOW TABLES").fetchall()}:
        return {}
    rows = con.execute("SELECT setting_key, setting_value FROM app_setting").fetchall()
    return {str(key): str(value) for key, value in rows}


def reset_imported_data(con: duckdb.DuckDBPyConnection) -> None:
    for table in [
        "transactions",
        "import_log",
        "import_batch",
        "raw_import_row",
        "transaction_classification_audit",
    ]:
        con.execute(f"DELETE FROM {table}")


def insert_transactions(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    return len(insert_transactions_with_status(con, df))


def insert_transactions_with_status(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []

    audit_payload = df.copy()
    payload = df.reindex(columns=TRANSACTION_COLUMNS).copy()
    con.register("incoming_transactions", payload)
    column_list = ", ".join(TRANSACTION_COLUMNS)
    result = con.execute(
        f"""
        INSERT INTO transactions ({column_list})
        SELECT {column_list}
        FROM incoming_transactions
        ON CONFLICT (transaction_id) DO NOTHING
        RETURNING transaction_id
        """
    ).fetchall()
    con.unregister("incoming_transactions")
    inserted_ids = [row[0] for row in result]
    insert_classification_audit(con, audit_payload, set(inserted_ids))
    return inserted_ids


def insert_classification_audit(
    con: duckdb.DuckDBPyConnection,
    df: pd.DataFrame,
    inserted_ids: set[str],
) -> int:
    required_columns = {"transaction_id", "matched_rule_id", "matched_rule_owner_type", "classification_reason"}
    if df.empty or not inserted_ids or not required_columns.issubset(df.columns):
        return 0

    payload = df[df["transaction_id"].isin(inserted_ids)].copy()
    payload = payload[payload["matched_rule_id"].notna()]
    if payload.empty:
        return 0

    first_audit_id = next_audit_id(con)
    payload["audit_id"] = range(first_audit_id, first_audit_id + len(payload))
    payload["rule_id"] = payload["matched_rule_id"].astype(int)
    payload["rule_owner_type"] = payload["matched_rule_owner_type"].fillna("").astype(str)
    payload["matched_pattern"] = payload["matched_pattern"].fillna("").astype(str) if "matched_pattern" in payload.columns else ""
    payload["old_transaction_type"] = ""
    payload["new_transaction_type"] = payload["transaction_type"].fillna("").astype(str)
    payload["old_category"] = ""
    payload["new_category"] = payload["category"].fillna("").astype(str)
    payload["old_subcategory"] = ""
    payload["new_subcategory"] = payload["subcategory"].fillna("").astype(str)
    payload["reason"] = payload["classification_reason"].fillna("").astype(str)
    audit_columns = [
        "audit_id",
        "transaction_id",
        "rule_id",
        "rule_owner_type",
        "matched_pattern",
        "old_transaction_type",
        "new_transaction_type",
        "old_category",
        "new_category",
        "old_subcategory",
        "new_subcategory",
        "reason",
    ]
    con.register("classification_audit", payload[audit_columns])
    con.execute(
        f"""
        INSERT INTO transaction_classification_audit ({", ".join(audit_columns)})
        SELECT {", ".join(audit_columns)}
        FROM classification_audit
        """
    )
    con.unregister("classification_audit")
    return len(payload)


def next_audit_id(con: duckdb.DuckDBPyConnection) -> int:
    return int(con.execute("SELECT COALESCE(max(audit_id), 0) + 1 FROM transaction_classification_audit").fetchone()[0])


def create_import_batch(
    con: duckdb.DuckDBPyConnection,
    import_batch_id: str,
    source_file: str,
    file_hash: str,
    status: str = "started",
    rows_seen: int = 0,
    source_id: str | None = None,
    message: str = "",
) -> None:
    con.execute(
        """
        INSERT INTO import_batch (
            import_batch_id,
            source_file,
            file_hash,
            source_id,
            status,
            rows_seen,
            message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [import_batch_id, source_file, file_hash, source_id, status, rows_seen, message],
    )


def update_import_batch(
    con: duckdb.DuckDBPyConnection,
    import_batch_id: str,
    status: str,
    rows_seen: int,
    rows_inserted: int,
    rows_duplicate: int,
    rows_failed: int,
    source_id: str | None = None,
    message: str = "",
) -> None:
    con.execute(
        """
        UPDATE import_batch
        SET
            source_id = COALESCE(?, source_id),
            status = ?,
            rows_seen = ?,
            rows_inserted = ?,
            rows_duplicate = ?,
            rows_failed = ?,
            message = ?
        WHERE import_batch_id = ?
        """,
        [source_id, status, rows_seen, rows_inserted, rows_duplicate, rows_failed, message, import_batch_id],
    )


def insert_raw_import_rows(
    con: duckdb.DuckDBPyConnection,
    import_batch_id: str,
    rows: list[dict[str, object]],
) -> None:
    if not rows:
        return
    payload = pd.DataFrame(rows)
    con.register("incoming_raw_import_rows", payload)
    con.execute(
        """
        INSERT INTO raw_import_row (
            import_batch_id,
            row_number,
            source_id,
            raw_data,
            row_hash,
            normalized_transaction_id,
            status,
            error_message
        )
        SELECT
            import_batch_id,
            row_number,
            source_id,
            raw_data,
            row_hash,
            normalized_transaction_id,
            status,
            error_message
        FROM incoming_raw_import_rows
        """
    )
    con.unregister("incoming_raw_import_rows")


def update_raw_import_row_statuses(
    con: duckdb.DuckDBPyConnection,
    rows: list[dict[str, object]],
) -> None:
    if not rows:
        return
    payload = pd.DataFrame(rows)
    con.register("raw_import_row_updates", payload)
    con.execute(
        """
        UPDATE raw_import_row
        SET
            source_id = raw_import_row_updates.source_id,
            normalized_transaction_id = raw_import_row_updates.normalized_transaction_id,
            status = raw_import_row_updates.status,
            error_message = raw_import_row_updates.error_message
        FROM raw_import_row_updates
        WHERE raw_import_row.import_batch_id = raw_import_row_updates.import_batch_id
          AND raw_import_row.row_number = raw_import_row_updates.row_number
        """
    )
    con.unregister("raw_import_row_updates")


def load_import_batches(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT *
        FROM import_batch
        ORDER BY imported_at DESC
        """
    ).df()


def load_raw_import_rows(con: duckdb.DuckDBPyConnection, import_batch_id: str) -> pd.DataFrame:
    return con.execute(
        """
        SELECT *
        FROM raw_import_row
        WHERE import_batch_id = ?
        ORDER BY row_number
        """,
        [import_batch_id],
    ).df()


def log_import(
    con: duckdb.DuckDBPyConnection,
    source_file: str,
    status: str,
    rows_seen: int,
    rows_inserted: int,
    message: str = "",
) -> None:
    con.execute(
        """
        INSERT INTO import_log (source_file, status, rows_seen, rows_inserted, message)
        VALUES (?, ?, ?, ?, ?)
        """,
        [source_file, status, rows_seen, rows_inserted, message],
    )


def load_transactions(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT *
        FROM transactions
        ORDER BY transaction_date DESC, ingested_at DESC
        """
    ).df()


def load_import_log(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT *
        FROM import_log
        ORDER BY imported_at DESC
        """
    ).df()


def update_categorizations(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    payload = df[["transaction_id", "merchant_clean", "transaction_type", "scope", "category", "subcategory"]].copy()
    if "manual_override" in df.columns:
        payload = payload[~df["manual_override"].fillna(False).astype(bool).to_numpy()]
    if payload.empty:
        return 0

    con.register("category_updates", payload)
    con.execute(
        """
        UPDATE transactions
        SET
            merchant_clean = category_updates.merchant_clean,
            transaction_type = category_updates.transaction_type,
            scope = category_updates.scope,
            category = category_updates.category,
            subcategory = category_updates.subcategory
        FROM category_updates
        WHERE transactions.transaction_id = category_updates.transaction_id
          AND COALESCE(transactions.manual_override, FALSE) = FALSE
        """
    )
    con.unregister("category_updates")
    return len(payload)


def update_transaction_fields(
    con: duckdb.DuckDBPyConnection,
    transaction_id: str,
    merchant_clean: str,
    transaction_type: str,
    scope: str,
    category: str,
    subcategory: str,
    manual_override: bool = True,
    category_manual_override: bool | None = None,
    type_manual_override: bool | None = None,
    merchant_manual_override: bool | None = None,
) -> None:
    category_manual_override = manual_override if category_manual_override is None else category_manual_override
    type_manual_override = manual_override if type_manual_override is None else type_manual_override
    merchant_manual_override = manual_override if merchant_manual_override is None else merchant_manual_override
    con.execute(
        """
        UPDATE transactions
        SET
            merchant_clean = ?,
            transaction_type = ?,
            scope = ?,
            category = ?,
            subcategory = ?,
            manual_override = ?,
            category_manual_override = ?,
            type_manual_override = ?,
            merchant_manual_override = ?
        WHERE transaction_id = ?
        """,
        [
            merchant_clean,
            transaction_type,
            scope,
            category,
            subcategory,
            manual_override,
            category_manual_override,
            type_manual_override,
            merchant_manual_override,
            transaction_id,
        ],
    )
