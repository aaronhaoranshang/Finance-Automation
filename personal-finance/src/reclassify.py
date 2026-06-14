from __future__ import annotations

from datetime import date
from typing import Iterable

import duckdb
import pandas as pd

from categorize import match_merchant_rule, title_from_raw
from db import next_audit_id
from normalize import apply_transaction_type_defaults


CHANGE_COLUMNS = [
    "transaction_id",
    "transaction_date",
    "merchant_raw",
    "old_merchant_clean",
    "new_merchant_clean",
    "old_transaction_type",
    "new_transaction_type",
    "old_category",
    "new_category",
    "old_subcategory",
    "new_subcategory",
    "matched_rule_id",
    "matched_rule_owner_type",
    "matched_pattern",
    "reason",
]


def reclassify_transactions(
    con: duckdb.DuckDBPyConnection,
    transaction_ids: Iterable[str] | None = None,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    dry_run: bool = True,
    respect_manual_overrides: bool = True,
) -> pd.DataFrame:
    transactions = load_reclassify_candidates(con, transaction_ids, start_date, end_date)
    if transactions.empty:
        return pd.DataFrame(columns=CHANGE_COLUMNS)

    changes = build_reclassification_changes(con, transactions, respect_manual_overrides=respect_manual_overrides)
    if not dry_run and not changes.empty:
        apply_reclassification_changes(con, changes)
    return changes


def load_reclassify_candidates(
    con: duckdb.DuckDBPyConnection,
    transaction_ids: Iterable[str] | None,
    start_date: date | str | None,
    end_date: date | str | None,
) -> pd.DataFrame:
    clauses = []
    params: list[object] = []
    if transaction_ids:
        ids = list(transaction_ids)
        placeholders = ", ".join(["?"] * len(ids))
        clauses.append(f"transaction_id IN ({placeholders})")
        params.extend(ids)
    if start_date is not None:
        clauses.append("transaction_date >= ?")
        params.append(start_date)
    if end_date is not None:
        clauses.append("transaction_date <= ?")
        params.append(end_date)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return con.execute(
        f"""
        SELECT
            transaction_id,
            transaction_date,
            merchant_raw,
            merchant_clean,
            transaction_type,
            scope,
            category,
            subcategory,
            COALESCE(manual_override, FALSE) AS manual_override,
            COALESCE(category_manual_override, COALESCE(manual_override, FALSE)) AS category_manual_override,
            COALESCE(type_manual_override, COALESCE(manual_override, FALSE)) AS type_manual_override,
            COALESCE(merchant_manual_override, COALESCE(manual_override, FALSE)) AS merchant_manual_override
        FROM transactions
        {where}
        ORDER BY transaction_date, transaction_id
        """,
        params,
    ).df()


def build_reclassification_changes(
    con: duckdb.DuckDBPyConnection,
    transactions: pd.DataFrame,
    respect_manual_overrides: bool,
) -> pd.DataFrame:
    rows = []
    for row in transactions.itertuples(index=False):
        rule = match_merchant_rule(con, row.merchant_raw)
        proposed_merchant_clean = rule.merchant_clean if rule and rule.merchant_clean else title_from_raw(row.merchant_raw)
        proposed_transaction_type = rule.transaction_type if rule and rule.transaction_type else row.transaction_type
        proposed_category = rule.category if rule and rule.category else row.category
        proposed_subcategory = rule.subcategory if rule and rule.category else row.subcategory

        if respect_manual_overrides:
            if bool(row.merchant_manual_override):
                proposed_merchant_clean = row.merchant_clean
            if bool(row.type_manual_override):
                proposed_transaction_type = row.transaction_type
            if bool(row.category_manual_override):
                proposed_category = row.category
                proposed_subcategory = row.subcategory

        normalized = apply_transaction_type_defaults(
            pd.DataFrame(
                [
                    {
                        "transaction_type": proposed_transaction_type,
                        "category": proposed_category,
                        "subcategory": proposed_subcategory,
                    }
                ]
            )
        ).iloc[0]
        proposed_category = normalized["category"]
        proposed_subcategory = normalized["subcategory"]

        changed = any(
            [
                clean(row.merchant_clean) != clean(proposed_merchant_clean),
                clean(row.transaction_type) != clean(proposed_transaction_type),
                clean(row.category) != clean(proposed_category),
                clean(row.subcategory) != clean(proposed_subcategory),
            ]
        )
        if not changed:
            continue

        matched_rule_id = rule.rule_id if rule else None
        matched_rule_owner_type = rule.owner_type if rule else ""
        matched_pattern = rule.pattern if rule else ""
        reason = (
            f"Matched {rule.owner_type} rule {rule.rule_id}: pattern='{rule.pattern}', match_type='{rule.match_type}'"
            if rule
            else "No merchant rule matched; normalized fallback values."
        )
        if respect_manual_overrides and bool(row.manual_override):
            reason += " Existing manual_override was respected conservatively."

        rows.append(
            {
                "transaction_id": row.transaction_id,
                "transaction_date": row.transaction_date,
                "merchant_raw": row.merchant_raw,
                "old_merchant_clean": row.merchant_clean,
                "new_merchant_clean": proposed_merchant_clean,
                "old_transaction_type": row.transaction_type,
                "new_transaction_type": proposed_transaction_type,
                "old_category": row.category,
                "new_category": proposed_category,
                "old_subcategory": row.subcategory,
                "new_subcategory": proposed_subcategory,
                "matched_rule_id": matched_rule_id,
                "matched_rule_owner_type": matched_rule_owner_type,
                "matched_pattern": matched_pattern,
                "reason": reason,
            }
        )

    return pd.DataFrame(rows, columns=CHANGE_COLUMNS)


def apply_reclassification_changes(con: duckdb.DuckDBPyConnection, changes: pd.DataFrame) -> None:
    payload = changes.copy()
    con.register("reclassification_changes", payload)
    con.execute(
        """
        UPDATE transactions
        SET
            merchant_clean = reclassification_changes.new_merchant_clean,
            transaction_type = reclassification_changes.new_transaction_type,
            category = reclassification_changes.new_category,
            subcategory = reclassification_changes.new_subcategory
        FROM reclassification_changes
        WHERE transactions.transaction_id = reclassification_changes.transaction_id
        """
    )
    con.unregister("reclassification_changes")
    insert_reclassification_audit(con, changes)


def insert_reclassification_audit(con: duckdb.DuckDBPyConnection, changes: pd.DataFrame) -> None:
    if changes.empty:
        return
    payload = changes.copy()
    first_audit_id = next_audit_id(con)
    payload["audit_id"] = range(first_audit_id, first_audit_id + len(payload))
    payload["rule_id"] = payload["matched_rule_id"]
    payload["rule_owner_type"] = payload["matched_rule_owner_type"].fillna("").astype(str)
    payload["matched_pattern"] = payload["matched_pattern"].fillna("").astype(str)
    payload["old_transaction_type"] = payload["old_transaction_type"].fillna("").astype(str)
    payload["new_transaction_type"] = payload["new_transaction_type"].fillna("").astype(str)
    payload["old_category"] = payload["old_category"].fillna("").astype(str)
    payload["new_category"] = payload["new_category"].fillna("").astype(str)
    payload["old_subcategory"] = payload["old_subcategory"].fillna("").astype(str)
    payload["new_subcategory"] = payload["new_subcategory"].fillna("").astype(str)
    payload["reason"] = payload["reason"].fillna("").astype(str)
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
    con.register("reclassification_audit", payload[audit_columns])
    con.execute(
        f"""
        INSERT INTO transaction_classification_audit ({", ".join(audit_columns)})
        SELECT {", ".join(audit_columns)}
        FROM reclassification_audit
        """
    )
    con.unregister("reclassification_audit")


def clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value)
