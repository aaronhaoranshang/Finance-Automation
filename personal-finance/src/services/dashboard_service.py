from __future__ import annotations

import pandas as pd

from db import connect, load_import_log, load_transactions
from normalize import classify_transaction
from services.transaction_service import transaction_types_with_flag
from ui.constants import (
    FALLBACK_INCOME_TYPES,
    FALLBACK_SPEND_TYPES,
    IGNORED_MOVEMENT_TYPES,
)


def spend_types() -> list[str]:
    return transaction_types_with_flag("affects_spend", FALLBACK_SPEND_TYPES)


def income_types() -> list[str]:
    return transaction_types_with_flag("affects_income", FALLBACK_INCOME_TYPES)


def category_required_types() -> list[str]:
    return transaction_types_with_flag("requires_category", ["expense", "refund", "credit"])


def drilldown_metric_types(metric: str) -> list[str]:
    if metric == "Gross Spend":
        return ["expense"]
    if metric == "Refunds/Credits":
        return ["refund", "credit"]
    if metric == "Personal Net Spend":
        return spend_types()
    if metric == "Income":
        return income_types()
    if metric == "Card Payments":
        return ["payment"]
    if metric == "Debt Payments":
        return ["debt_payment"]
    if metric == "Internal Transfers":
        return ["transfer"]
    if metric == "Reimbursements":
        return ["reimbursement"]
    if metric == "Prepaid Card Reloads":
        return ["stored_value_reload"]
    if metric == "Needs Review":
        return ["manual_review"]
    return IGNORED_MOVEMENT_TYPES


def money_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    framed = df.copy()
    framed["transaction_date"] = pd.to_datetime(framed["transaction_date"], errors="coerce")
    if "transaction_type" not in framed.columns:
        framed["transaction_type"] = framed.apply(classify_transaction, axis=1)
    else:
        missing_type = framed["transaction_type"].isna() | (framed["transaction_type"] == "")
        if missing_type.any():
            framed.loc[missing_type, "transaction_type"] = framed.loc[missing_type].apply(classify_transaction, axis=1)

    framed["amount"] = pd.to_numeric(framed["amount"], errors="coerce").fillna(0)
    if "scope" not in framed.columns:
        framed["scope"] = "personal"
    framed["scope"] = framed["scope"].fillna("personal").replace("", "personal")
    income_type_values = income_types()
    framed["gross_spend"] = framed["amount"].where(framed["transaction_type"] == "expense", 0)
    framed["refund_credit"] = -framed["amount"].where(framed["transaction_type"].isin(["refund", "credit"]), 0).abs()
    framed["refund_credit_abs"] = framed["refund_credit"].abs()
    framed["reimbursement_amount"] = framed["amount"].where(framed["transaction_type"] == "reimbursement", 0).abs()
    framed["reimbursement_offset"] = -framed["reimbursement_amount"]
    framed["net_spend"] = framed["gross_spend"] + framed["refund_credit"] + framed["reimbursement_offset"]
    framed["income_amount"] = framed["amount"].where(framed["transaction_type"].isin(income_type_values), 0).abs()
    framed["payment_amount"] = framed["amount"].where(framed["transaction_type"] == "payment", 0).abs()
    framed["debt_payment_amount"] = framed["amount"].where(framed["transaction_type"] == "debt_payment", 0).abs()
    framed["transfer_amount"] = framed["amount"].where(framed["transaction_type"] == "transfer", 0).abs()
    framed["stored_value_reload_amount"] = framed["amount"].where(framed["transaction_type"] == "stored_value_reload", 0).abs()
    framed["manual_review_amount"] = framed["amount"].where(framed["transaction_type"] == "manual_review", 0).abs()
    framed["ignored_amount"] = framed["amount"].where(framed["transaction_type"] == "ignored", 0).abs()
    framed["ignored_movement"] = (
        framed["payment_amount"]
        + framed["debt_payment_amount"]
        + framed["transfer_amount"]
        + framed["stored_value_reload_amount"]
        + framed["ignored_amount"]
    )
    framed["month"] = framed["transaction_date"].dt.to_period("M").astype(str)
    framed["display_amount"] = framed["amount"].abs()
    framed["category"] = framed["category"].fillna("")
    framed["subcategory"] = framed["subcategory"].fillna("")
    missing_required_category = framed["transaction_type"].isin(category_required_types()) & framed["category"].eq("")
    framed.loc[missing_required_category, "category"] = "Uncategorized"
    return framed


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    con = connect()
    try:
        return load_transactions(con), load_import_log(con)
    finally:
        con.close()


def summary_by_month(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby("month", as_index=False)
        .agg(
            gross_spend=("gross_spend", "sum"),
            refunds_credits=("refund_credit_abs", "sum"),
            net_spend=("net_spend", "sum"),
            income=("income_amount", "sum"),
            card_payments=("payment_amount", "sum"),
            debt_payments=("debt_payment_amount", "sum"),
            transfers=("transfer_amount", "sum"),
            reimbursements=("reimbursement_amount", "sum"),
            stored_value_reloads=("stored_value_reload_amount", "sum"),
            manual_review=("manual_review_amount", "sum"),
            ignored_movement=("ignored_movement", "sum"),
            transactions=("transaction_id", "count"),
        )
        .sort_values("month")
    )
