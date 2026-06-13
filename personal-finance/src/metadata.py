from __future__ import annotations

import duckdb
import pandas as pd


def get_categories(con: duckdb.DuckDBPyConnection, include_disabled: bool = False) -> list[str]:
    where_clause = "" if include_disabled else "WHERE enabled"
    return [
        row[0]
        for row in con.execute(
            f"""
            SELECT category
            FROM category_master
            {where_clause}
            GROUP BY category
            ORDER BY min(sort_order), category
            """
        ).fetchall()
    ]


def get_subcategories(
    con: duckdb.DuckDBPyConnection,
    category: str,
    include_disabled: bool = False,
) -> list[str]:
    enabled_clause = "" if include_disabled else "AND enabled"
    return [
        row[0]
        for row in con.execute(
            f"""
            SELECT subcategory
            FROM category_master
            WHERE category = ?
              AND subcategory <> ''
              {enabled_clause}
            GROUP BY subcategory
            ORDER BY min(sort_order), subcategory
            """,
            [category],
        ).fetchall()
    ]


def add_user_category(
    con: duckdb.DuckDBPyConnection,
    category: str,
    subcategory: str,
    sort_order: int = 100,
) -> None:
    category = category.strip()
    subcategory = subcategory.strip()
    if not category:
        return

    insert_category_pair(con, category, "", "user", sort_order)
    if subcategory:
        insert_category_pair(con, category, subcategory, "user", sort_order)


def disable_user_category(con: duckdb.DuckDBPyConnection, category: str, subcategory: str) -> None:
    category = category.strip()
    subcategory = subcategory.strip()
    if not category:
        return

    if subcategory:
        con.execute(
            """
            UPDATE category_master
            SET
                enabled = FALSE,
                updated_at = now()
            WHERE owner_type = 'user'
              AND category = ?
              AND subcategory = ?
            """,
            [category, subcategory],
        )
        return

    con.execute(
        """
        UPDATE category_master
        SET
            enabled = FALSE,
            updated_at = now()
        WHERE owner_type = 'user'
          AND category = ?
        """,
        [category],
    )


def validate_category_pair(
    con: duckdb.DuckDBPyConnection,
    category: str,
    subcategory: str,
) -> bool:
    category = category.strip()
    subcategory = subcategory.strip()
    if not category and not subcategory:
        return True
    if not category:
        return False
    if not subcategory:
        return (
            con.execute(
                """
                SELECT count(*)
                FROM category_master
                WHERE category = ?
                  AND enabled
                """,
                [category],
            ).fetchone()[0]
            > 0
        )
    return (
        con.execute(
            """
            SELECT count(*)
            FROM category_master
            WHERE category = ?
              AND subcategory = ?
              AND enabled
            """,
            [category, subcategory],
        ).fetchone()[0]
        > 0
    )


def transaction_type_requires_category(
    con: duckdb.DuckDBPyConnection,
    transaction_type: str,
) -> bool:
    row = con.execute(
        """
        SELECT requires_category
        FROM transaction_type_master
        WHERE transaction_type = ?
          AND enabled
        """,
        [transaction_type],
    ).fetchone()
    return bool(row[0]) if row else False


def get_category_master(con: duckdb.DuckDBPyConnection, include_disabled: bool = False) -> pd.DataFrame:
    where_clause = "" if include_disabled else "WHERE enabled"
    return con.execute(
        f"""
        SELECT
            category,
            subcategory,
            owner_type,
            enabled,
            sort_order
        FROM category_master
        {where_clause}
        ORDER BY category, subcategory, owner_type
        """
    ).df()


def get_user_category_pairs(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT category, subcategory
        FROM category_master
        WHERE owner_type = 'user'
          AND enabled
        ORDER BY category, subcategory
        """
    ).df()


def insert_category_pair(
    con: duckdb.DuckDBPyConnection,
    category: str,
    subcategory: str,
    owner_type: str,
    sort_order: int,
) -> None:
    con.execute(
        """
        INSERT INTO category_master (
            category_id,
            category,
            subcategory,
            owner_type,
            sort_order
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (category, subcategory, owner_type) DO UPDATE
        SET
            enabled = TRUE,
            sort_order = excluded.sort_order,
            updated_at = now()
        """,
        [next_category_id(con), category, subcategory, owner_type, sort_order],
    )


def next_category_id(con: duckdb.DuckDBPyConnection) -> int:
    value = con.execute("SELECT COALESCE(max(category_id), 0) + 1 FROM category_master").fetchone()[0]
    return int(value)
