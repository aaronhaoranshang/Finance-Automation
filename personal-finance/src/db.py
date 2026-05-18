from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

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
    "currency",
    "category",
    "subcategory",
    "source_file",
    "ingested_at",
]


def connect(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    ensure_project_dirs()
    con = duckdb.connect(str(db_path))
    init_db(con)
    return con


def init_db(con: duckdb.DuckDBPyConnection) -> None:
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
            currency VARCHAR,
            category VARCHAR,
            subcategory VARCHAR,
            source_file VARCHAR,
            ingested_at TIMESTAMP
        )
        """
    )
    ensure_column(con, "transactions", "transaction_type", "VARCHAR")
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


def ensure_column(con: duckdb.DuckDBPyConnection, table_name: str, column_name: str, data_type: str) -> None:
    columns = con.execute(f"PRAGMA table_info('{table_name}')").df()["name"].tolist()
    if column_name not in columns:
        con.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {data_type}")


def insert_transactions(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0

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
    return len(result)


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

    payload = df[["transaction_id", "merchant_clean", "category", "subcategory"]].copy()
    con.register("category_updates", payload)
    con.execute(
        """
        UPDATE transactions
        SET
            merchant_clean = category_updates.merchant_clean,
            category = category_updates.category,
            subcategory = category_updates.subcategory
        FROM category_updates
        WHERE transactions.transaction_id = category_updates.transaction_id
        """
    )
    con.unregister("category_updates")
    return len(payload)
