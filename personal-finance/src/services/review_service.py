from __future__ import annotations

import pandas as pd

from categorize import match_merchant_rule
from db import connect
from services.category_service import category_master_pairs
from services.dashboard_service import category_required_types
from services.rule_service import suggest_sql_rule
from services.transaction_service import category_required_for_type
from ui.constants import REVIEW_TYPES


def is_uncategorized(df: pd.DataFrame) -> pd.Series:
    category = df["category"].fillna("")
    subcategory = df["subcategory"].fillna("")
    return (
        category.eq("Uncategorized")
        | ((category == "Other") & (subcategory == "Uncategorized"))
        | (category.eq("") & df["transaction_type"].isin(category_required_types()))
    )


def review_reason(row: pd.Series, valid_pairs: set[tuple[str, str]]) -> str:
    transaction_type = str(row.get("transaction_type") or "")
    category = str(row.get("category") or "")
    subcategory = str(row.get("subcategory") or "")
    reasons = []
    if transaction_type in REVIEW_TYPES:
        reasons.append("Needs transaction type review")
    if category_required_for_type(transaction_type) and not category:
        reasons.append("Missing category")
    if category and (category, subcategory) not in valid_pairs:
        reasons.append("Category no longer exists")
    if is_uncategorized(pd.DataFrame([row])).iloc[0]:
        reasons.append("Uncategorized")

    con = connect()
    try:
        matched_rule = match_merchant_rule(con, row.get("merchant_raw"))
    finally:
        con.close()
    suggestion = suggest_sql_rule(str(row.get("merchant_raw") or ""), score_cutoff=0)
    score = float(suggestion.get("score", 0)) if suggestion else 0.0
    if matched_rule is None and score < 82:
        reasons.append("No confident merchant rule")
    return "; ".join(dict.fromkeys(reasons))


def build_review_queue(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    valid_pairs = category_master_pairs()
    queue = df.copy()
    queue["review_reason"] = queue.apply(lambda row: review_reason(row, valid_pairs), axis=1)
    queue = queue[queue["review_reason"].astype(str).str.len() > 0]
    return queue.sort_values(["transaction_date", "amount"], ascending=[False, False])

