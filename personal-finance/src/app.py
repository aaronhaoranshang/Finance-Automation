from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from backup import export_backup, restore_backup
from categorize import (
    categorize_transactions,
    disable_rule,
    load_merchant_rules_from_db,
    match_merchant_rule,
    save_user_merchant_rule,
    suggest_pattern_from_raw,
    suggest_rule,
    update_rule,
)
from db import (
    connect,
    load_app_settings,
    load_import_batches,
    load_import_log,
    load_raw_import_rows,
    load_transactions,
    reset_imported_data,
    save_app_setting,
    update_categorizations,
    update_transaction_fields,
)
from ingest import ingest_file, preview_file, supported_import_files, unique_destination
from metadata import (
    add_user_category,
    disable_user_category,
    get_categories,
    get_category_master,
    get_subcategories,
    get_transaction_types,
    get_user_category_pairs,
    transaction_type_requires_category,
    validate_category_pair,
)
from normalize import apply_transaction_type_defaults, classify_transaction
from paths import DB_PATH, TO_IMPORT_DIR, ensure_project_dirs
from reclassify import reclassify_transactions


FALLBACK_SPEND_TYPES = ["expense", "refund", "credit", "reimbursement"]
FALLBACK_INCOME_TYPES = ["income"]
IGNORED_MOVEMENT_TYPES = ["payment", "debt_payment", "transfer", "stored_value_reload"]
REVIEW_TYPES = ["manual_review"]
FALLBACK_TRANSACTION_TYPES = [
    "expense",
    "refund",
    "credit",
    "income",
    "payment",
    "debt_payment",
    "transfer",
    "reimbursement",
    "stored_value_reload",
    "manual_review",
    "zero",
]
SCOPES = ["personal", "shared"]

FALLBACK_TRANSACTION_TYPE_LABELS = {
    "expense": "Expense",
    "refund": "Refund",
    "credit": "Merchant Credit",
    "income": "Income",
    "payment": "Card Payment",
    "debt_payment": "Debt Payment",
    "transfer": "Internal Transfer",
    "reimbursement": "Reimbursement",
    "stored_value_reload": "Prepaid Card Reload",
    "manual_review": "Needs Review",
    "zero": "Zero Amount",
}

TRANSACTION_TYPE_HELP = {
    "Expense": "Real spending that counts toward spend totals.",
    "Refund": "Merchant refund that reduces spending.",
    "Merchant Credit": "Statement credit or adjustment that reduces spending.",
    "Income": "True income, such as payroll, rent collected, interest, or tax refund.",
    "Card Payment": "Payment made to a credit card. Ignored for spending to avoid double counting.",
    "Debt Payment": "Cash leaving an account to pay a card, loan, or line of credit. Ignored for spending.",
    "Internal Transfer": "Money moved between your own accounts. Ignored for spending and income.",
    "Reimbursement": "Money paid back to you, or pass-through spending you do not want counted as your own spend.",
    "Prepaid Card Reload": "Large reload/top-up transaction, such as loading PayPower or another stored-value card. Ignored for spending.",
    "Needs Review": "Ambiguous transaction that needs a manual decision.",
    "Zero Amount": "Zero-dollar row.",
}

SCOPE_LABELS = {
    "personal": "Personal",
    "shared": "Shared",
}

COLUMN_LABELS = {
    "transaction_date": "Date",
    "posted_date": "Posted Date",
    "account_name": "Account",
    "institution": "Institution",
    "transaction_type": "Type",
    "scope": "Scope",
    "merchant_raw": "Raw Merchant",
    "merchant_clean": "Merchant",
    "category": "Category",
    "subcategory": "Subcategory",
    "amount": "Amount",
    "display_amount": "Amount",
    "source_file": "Source File",
    "source_id": "Source",
    "import_batch_id": "Import Batch",
    "file_hash": "File Hash",
    "row_number": "Row",
    "raw_data": "Raw Data",
    "row_hash": "Row Hash",
    "normalized_transaction_id": "Transaction ID",
    "old_category": "Old Category",
    "new_category": "New Category",
    "old_subcategory": "Old Subcategory",
    "new_subcategory": "New Subcategory",
    "old_transaction_type": "Old Type",
    "new_transaction_type": "New Type",
    "old_merchant_clean": "Old Merchant",
    "new_merchant_clean": "New Merchant",
    "matched_rule_id": "Matched Rule",
    "month": "Month",
    "gross_spend": "Gross Spend",
    "refunds_credits": "Refunds/Credits",
    "refund_credit_abs": "Refunds/Credits",
    "net_spend": "Personal Net Spend",
    "income": "Income",
    "income_amount": "Income",
    "card_payments": "Card Payments",
    "payment_amount": "Card Payments",
    "debt_payments": "Debt Payments",
    "debt_payment_amount": "Debt Payments",
    "transfers": "Internal Transfers",
    "transfer_amount": "Internal Transfers",
    "reimbursements": "Reimbursements",
    "reimbursement_amount": "Reimbursements",
    "stored_value_reloads": "Prepaid Card Reloads",
    "stored_value_reload_amount": "Prepaid Card Reloads",
    "manual_review": "Needs Review",
    "manual_review_amount": "Needs Review",
    "ignored_movement": "Excluded From Spend",
    "transactions": "Transactions",
    "file_net": "File Net",
    "first_date": "First Date",
    "last_date": "Last Date",
    "rows_seen": "Rows Seen",
    "rows_duplicate": "Duplicate Rows",
    "rows_failed": "Failed Rows",
    "rows_in_file": "Rows In File",
    "existing_duplicates": "Existing Duplicates",
    "new_rows": "New Rows",
    "statement_month": "Statement Month",
    "processed_name": "Processed Name",
    "gross_expenses": "Gross Expenses",
    "refunds_and_credits": "Refunds/Credits",
    "payments": "Card Payments",
    "debt_payments": "Debt Payments",
    "file_net_total": "File Net Total",
    "size_kb": "Size KB",
    "type": "File Type",
    "file": "File",
    "status": "Status",
    "rows_inserted": "Rows Inserted",
    "destination": "Destination",
    "error": "Error",
    "imported_at": "Imported At",
    "message": "Message",
}

DRILLDOWN_METRICS = [
    "Gross Spend",
    "Refunds/Credits",
    "Personal Net Spend",
    "Income",
    "Card Payments",
    "Debt Payments",
    "Internal Transfers",
    "Reimbursements",
    "Prepaid Card Reloads",
    "Needs Review",
    "Excluded From Spend",
]


@st.cache_data(ttl=30)
def load_transaction_type_metadata() -> pd.DataFrame:
    con = connect()
    try:
        return get_transaction_types(con)
    finally:
        con.close()


def transaction_type_metadata() -> pd.DataFrame:
    try:
        metadata = load_transaction_type_metadata()
    except Exception:
        metadata = pd.DataFrame()
    return metadata


def transaction_type_options(existing_types: pd.Series | None = None) -> list[str]:
    metadata = transaction_type_metadata()
    metadata_types = metadata["transaction_type"].dropna().astype(str).tolist() if not metadata.empty else []
    existing = existing_types.dropna().astype(str).tolist() if existing_types is not None else []
    return sorted({*FALLBACK_TRANSACTION_TYPES, *metadata_types, *existing}, key=display_transaction_type)


def transaction_type_labels() -> dict[str, str]:
    metadata = transaction_type_metadata()
    if metadata.empty:
        return FALLBACK_TRANSACTION_TYPE_LABELS
    labels = dict(zip(metadata["transaction_type"], metadata["display_name"], strict=True))
    return {**FALLBACK_TRANSACTION_TYPE_LABELS, **labels}


def transaction_types_with_flag(flag: str, fallback: list[str]) -> list[str]:
    metadata = transaction_type_metadata()
    if metadata.empty or flag not in metadata.columns:
        return fallback
    values = metadata.loc[metadata[flag].astype(bool), "transaction_type"].dropna().astype(str).tolist()
    return values or fallback


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
    framed["ignored_movement"] = (
        framed["payment_amount"]
        + framed["debt_payment_amount"]
        + framed["transfer_amount"]
        + framed["stored_value_reload_amount"]
    )
    framed["month"] = framed["transaction_date"].dt.to_period("M").astype(str)
    framed["display_amount"] = framed["amount"].abs()
    framed["category"] = framed["category"].fillna("")
    framed["subcategory"] = framed["subcategory"].fillna("")
    missing_required_category = (
        framed["transaction_type"].isin(category_required_types())
        & framed["category"].eq("")
    )
    framed.loc[missing_required_category, "category"] = "Uncategorized"
    return framed


@st.cache_data(ttl=5)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    con = connect()
    try:
        return load_transactions(con), load_import_log(con)
    finally:
        con.close()


def refresh_categories() -> None:
    con = connect()
    try:
        transactions = load_transactions(con)
        refreshed = categorize_transactions(transactions, con=con)
        refreshed = apply_transaction_type_defaults(refreshed)
        update_categorizations(con, refreshed)
    finally:
        con.close()
    st.cache_data.clear()


def load_sql_merchant_rules(include_disabled: bool = False) -> pd.DataFrame:
    con = connect()
    try:
        rules = load_merchant_rules_from_db(con, include_disabled=include_disabled)
    finally:
        con.close()
    return pd.DataFrame([rule.__dict__ for rule in rules])


def suggest_sql_rule(merchant_raw: str, score_cutoff: int = 82) -> dict[str, object] | None:
    con = connect()
    try:
        rules = load_merchant_rules_from_db(con)
    finally:
        con.close()
    return suggest_rule(merchant_raw, rules=rules, score_cutoff=score_cutoff)


def save_sql_user_rule(
    pattern: str,
    merchant_clean: str,
    transaction_type: str,
    scope: str,
    category: str,
    subcategory: str,
    match_type: str = "contains",
    priority: int = 50,
    notes: str = "",
) -> int:
    con = connect()
    try:
        rule_id = save_user_merchant_rule(
            con,
            pattern=pattern,
            match_type=match_type,
            merchant_clean=merchant_clean,
            transaction_type=transaction_type,
            scope=scope,
            category=category,
            subcategory=subcategory,
            priority=priority,
            notes=notes,
        )
    finally:
        con.close()
    st.cache_data.clear()
    return rule_id


def available_categories(df: pd.DataFrame) -> list[str]:
    con = connect()
    try:
        categories = get_categories(con)
    finally:
        con.close()
    return [*categories, "Custom"]


def available_subcategories(category: str, df: pd.DataFrame) -> list[str]:
    con = connect()
    try:
        subcategories = get_subcategories(con, category)
    finally:
        con.close()
    return subcategories


def save_category_metadata(category: str, subcategory: str = "", sort_order: int = 100) -> None:
    category = category.strip()
    subcategory = subcategory.strip()
    if not category or category == "Custom":
        return

    con = connect()
    try:
        add_user_category(con, category, subcategory, sort_order=sort_order)
    finally:
        con.close()


def category_pair_valid(category: str, subcategory: str) -> bool:
    con = connect()
    try:
        return validate_category_pair(con, category, subcategory)
    finally:
        con.close()


def category_required_for_type(transaction_type: str) -> bool:
    con = connect()
    try:
        return transaction_type_requires_category(con, transaction_type)
    finally:
        con.close()


def category_master_pairs() -> set[tuple[str, str]]:
    con = connect()
    try:
        category_master = get_category_master(con)
    finally:
        con.close()
    if category_master.empty:
        return set()
    return {
        (str(row.category), str(row.subcategory or ""))
        for row in category_master.itertuples()
    }


def is_uncategorized(df: pd.DataFrame) -> pd.Series:
    category = df["category"].fillna("")
    subcategory = df["subcategory"].fillna("")
    return category.eq("Uncategorized") | (
        (category == "Other") & (subcategory == "Uncategorized")
    ) | (
        category.eq("") & df["transaction_type"].isin(category_required_types())
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


def filter_panel(df: pd.DataFrame) -> pd.DataFrame:
    with st.sidebar:
        st.header("Filters")
        months = sorted(df["month"].dropna().unique().tolist(), reverse=True)
        selected_months = st.multiselect("Months", months, default=months[:1] if months else [])

        accounts = sorted(df["account_name"].dropna().unique().tolist())
        selected_accounts = st.multiselect("Accounts", accounts, default=accounts)

        scopes = sorted(df["scope"].dropna().unique().tolist(), key=display_scope)
        selected_scopes = st.multiselect("Scope", scopes, default=scopes, format_func=display_scope)

        types = sorted(df["transaction_type"].dropna().unique().tolist(), key=display_transaction_type)
        selected_types = st.multiselect("Transaction Types", types, default=types, format_func=display_transaction_type)

    filtered = df.copy()
    if selected_months:
        filtered = filtered[filtered["month"].isin(selected_months)]
    if selected_accounts:
        filtered = filtered[filtered["account_name"].isin(selected_accounts)]
    if selected_scopes:
        filtered = filtered[filtered["scope"].isin(selected_scopes)]
    if selected_types:
        filtered = filtered[filtered["transaction_type"].isin(selected_types)]
    return filtered


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


def metric_row(df: pd.DataFrame) -> None:
    gross_spend = float(df["gross_spend"].sum())
    refunds = float(df["refund_credit_abs"].sum())
    net_spend = float(df["net_spend"].sum())
    income = float(df["income_amount"].sum())
    manual_review = float(df["manual_review_amount"].sum())
    ignored = float(df["ignored_movement"].sum())
    uncategorized = int((is_uncategorized(df) & df["transaction_type"].isin(spend_types())).sum())

    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
    col1.metric("Personal Net Spend", money(net_spend))
    col2.metric("Gross Spend", money(gross_spend))
    col3.metric("Refunds/Credits", money(refunds))
    col4.metric("Income", money(income))
    col5.metric("Needs Review", money(manual_review))
    col6.metric("Excluded From Spend", money(ignored))
    col7.metric("Uncategorized", f"{uncategorized:,}")


def money(value: float) -> str:
    return f"${value:,.2f}"


def display_transaction_type(value: object) -> str:
    value = "" if pd.isna(value) else str(value)
    return transaction_type_labels().get(value, value.replace("_", " ").title())


def display_scope(value: object) -> str:
    value = "" if pd.isna(value) else str(value)
    return SCOPE_LABELS.get(value, value.replace("_", " ").title())


def display_metric(value: object) -> str:
    value = "" if pd.isna(value) else str(value)
    return COLUMN_LABELS.get(value, value.replace("_", " ").title())


def display_log_message(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value)
    replacements = {
        "gross_expenses": "Gross Expenses",
        "refunds_credits": "Refunds/Credits",
        "debt_payments": "Debt Payments",
        "stored_value_reloads": "Prepaid Card Reloads",
        "manual_review": "Needs Review",
        "net_spend": "Personal Net Spend",
        "file_net_total": "File Net Total",
        "payments": "Card Payments",
        "transfers": "Internal Transfers",
        "reimbursements": "Reimbursements",
        "income": "Income",
    }
    for raw, label in replacements.items():
        text = text.replace(f"{raw}=", f"{label}=")
    return text


def display_table(df: pd.DataFrame, columns: list[str] | None = None) -> None:
    if df.empty:
        st.dataframe(df, width="stretch", hide_index=True)
        return

    display_df = df.copy()
    if columns is not None:
        display_df = display_df[[column for column in columns if column in display_df.columns]]
    if "transaction_type" in display_df.columns:
        display_df["transaction_type"] = display_df["transaction_type"].map(display_transaction_type)
    if "scope" in display_df.columns:
        display_df["scope"] = display_df["scope"].map(display_scope)
    if "message" in display_df.columns:
        display_df["message"] = display_df["message"].map(display_log_message)
    display_df = display_df.rename(columns=lambda column: COLUMN_LABELS.get(column, str(column).replace("_", " ").title()))
    st.dataframe(display_df, width="stretch", hide_index=True)


def display_import_preview(preview: dict[str, object]) -> dict[str, object]:
    return {COLUMN_LABELS.get(key, key.replace("_", " ").title()): value for key, value in preview.items()}


def render_overview(df: pd.DataFrame) -> None:
    st.title("Finance Overview")
    metric_row(df)

    monthly = summary_by_month(df)
    if monthly.empty:
        st.info("No transactions match the current filters.")
        return

    chart_data = monthly.melt(
        id_vars="month",
        value_vars=[
            "gross_spend",
            "refunds_credits",
            "net_spend",
            "income",
            "manual_review",
            "ignored_movement",
        ],
        var_name="metric",
        value_name="amount",
    )
    chart_data["metric"] = chart_data["metric"].map(display_metric)
    st.plotly_chart(px.bar(chart_data, x="month", y="amount", color="metric", barmode="group"), width="stretch")
    display_table(monthly)

    account_summary = (
        df.groupby(["account_name", "transaction_type"], as_index=False)
        .agg(amount=("display_amount", "sum"), transactions=("transaction_id", "count"))
        .sort_values(["account_name", "transaction_type"])
    )
    st.subheader("Account Activity")
    display_table(account_summary)


def render_monthly_detail(df: pd.DataFrame) -> None:
    st.title("Monthly Detail")
    months = sorted(df["month"].dropna().unique().tolist(), reverse=True)
    if not months:
        st.info("No transactions match the current filters.")
        return
    selected_month = st.selectbox("Month", months)
    month_df = df[df["month"] == selected_month]
    metric_row(month_df)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Category", "Subcategory", "Merchant", "Account", "Transactions"])
    spend_df = month_df[month_df["transaction_type"].isin(spend_types())]

    with tab1:
        category = spend_df.groupby("category", as_index=False)["net_spend"].sum().sort_values("net_spend", ascending=False)
        st.plotly_chart(px.bar(category, x="category", y="net_spend"), width="stretch")
        display_table(category)

    with tab2:
        subcategory = (
            spend_df.assign(subcategory=spend_df["subcategory"].replace("", "(None)"))
            .groupby(["category", "subcategory"], as_index=False)["net_spend"]
            .sum()
            .sort_values("net_spend", ascending=False)
        )
        display_table(subcategory)

    with tab3:
        merchants = (
            spend_df.groupby(["merchant_clean", "category", "subcategory"], as_index=False)
            .agg(net_spend=("net_spend", "sum"), transactions=("transaction_id", "count"))
            .sort_values("net_spend", ascending=False)
        )
        display_table(merchants)

    with tab4:
        accounts = (
            month_df.groupby(["account_name", "transaction_type"], as_index=False)
            .agg(amount=("display_amount", "sum"), transactions=("transaction_id", "count"))
            .sort_values(["account_name", "transaction_type"])
        )
        display_table(accounts)

    with tab5:
        render_transaction_table(month_df)


def render_reconciliation(df: pd.DataFrame) -> None:
    st.title("Audit")
    st.caption("Use these tables to check totals by Month, Account, Source File, and Type.")

    monthly = summary_by_month(df)
    st.subheader("Monthly Totals")
    display_table(monthly)

    by_account_month = (
        df.groupby(["month", "account_name"], as_index=False)
        .agg(
            gross_spend=("gross_spend", "sum"),
            refunds_credits=("refund_credit_abs", "sum"),
            net_spend=("net_spend", "sum"),
            income=("income_amount", "sum"),
            payments=("payment_amount", "sum"),
            debt_payments=("debt_payment_amount", "sum"),
            transfers=("transfer_amount", "sum"),
            reimbursements=("reimbursement_amount", "sum"),
            stored_value_reloads=("stored_value_reload_amount", "sum"),
            manual_review=("manual_review_amount", "sum"),
            ignored_movement=("ignored_movement", "sum"),
            file_net=("amount", "sum"),
            transactions=("transaction_id", "count"),
        )
        .sort_values(["month", "account_name"])
    )
    st.subheader("By Account And Month")
    display_table(by_account_month)

    by_source = (
        df.groupby(["source_file", "account_name"], as_index=False)
        .agg(
            first_date=("transaction_date", "min"),
            last_date=("transaction_date", "max"),
            net_spend=("net_spend", "sum"),
            income=("income_amount", "sum"),
            reimbursements=("reimbursement_amount", "sum"),
            stored_value_reloads=("stored_value_reload_amount", "sum"),
            manual_review=("manual_review_amount", "sum"),
            ignored_movement=("ignored_movement", "sum"),
            file_net=("amount", "sum"),
            transactions=("transaction_id", "count"),
        )
        .sort_values(["last_date", "source_file"])
    )
    st.subheader("By Source File")
    display_table(by_source)

    render_import_batch_audit()
    render_reclassification_panel(df)

    csv = by_account_month.to_csv(index=False).encode("utf-8")
    st.download_button("Download Account-Month CSV", csv, "account_month_reconciliation.csv", "text/csv")


def render_import_batch_audit() -> None:
    con = connect()
    try:
        batches = load_import_batches(con)
    finally:
        con.close()

    st.subheader("Import Batches")
    if batches.empty:
        st.info("No import batches recorded yet.")
        return

    display_table(batches)
    selected_batch = st.selectbox(
        "Inspect Import Batch",
        batches["import_batch_id"].tolist(),
        format_func=lambda batch_id: format_import_batch(batches, batch_id),
    )
    con = connect()
    try:
        raw_rows = load_raw_import_rows(con, selected_batch)
    finally:
        con.close()

    if raw_rows.empty:
        st.info("No raw rows stored for this batch.")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Raw Rows", f"{len(raw_rows):,}")
    col2.metric("Inserted", f"{int((raw_rows['status'] == 'inserted').sum()):,}")
    col3.metric("Duplicates", f"{int((raw_rows['status'] == 'duplicate').sum()):,}")
    col4.metric("Failed", f"{int((raw_rows['status'] == 'failed').sum()):,}")

    statuses = ["All", *sorted(raw_rows["status"].fillna("").replace("", "pending").unique().tolist())]
    selected_status = st.selectbox("Raw Row Status", statuses)
    filtered_rows = raw_rows.copy()
    if selected_status != "All":
        filtered_rows = filtered_rows[filtered_rows["status"].fillna("").replace("", "pending") == selected_status]

    display_table(
        filtered_rows,
        [
            "row_number",
            "status",
            "source_id",
            "normalized_transaction_id",
            "error_message",
            "raw_data",
            "row_hash",
        ],
    )


def render_reclassification_panel(df: pd.DataFrame) -> None:
    st.subheader("Reclassification")
    st.caption("Preview how current SQL merchant rules would update existing transactions before applying changes.")
    if df.empty:
        st.info("No transactions match the current filters.")
        return

    months = ["All", *sorted(df["month"].dropna().unique().tolist(), reverse=True)]
    col1, col2 = st.columns(2)
    month = col1.selectbox("Reclassification Month", months)
    respect_manual = col2.checkbox(
        "Respect manual overrides",
        value=True,
        help="Keeps manually edited merchants, types, and categories unchanged. Turn off only when you intentionally want rules to overwrite manual edits.",
    )

    candidate_df = df if month == "All" else df[df["month"] == month]
    transaction_ids = candidate_df["transaction_id"].dropna().astype(str).tolist()
    preview_key = f"reclass_preview_{month}_{respect_manual}_{len(transaction_ids)}"

    if st.button("Preview Reclassification", disabled=not transaction_ids):
        con = connect()
        try:
            st.session_state[preview_key] = reclassify_transactions(
                con,
                transaction_ids=transaction_ids,
                dry_run=True,
                respect_manual_overrides=respect_manual,
            )
        finally:
            con.close()

    preview = st.session_state.get(preview_key)
    if preview is None:
        return
    if preview.empty:
        st.success("No changes would be made.")
        return

    st.warning(f"{len(preview):,} transaction(s) would change.")
    display_table(
        preview,
        [
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
            "reason",
        ],
    )
    confirm = st.checkbox("I reviewed the preview and want to apply these changes")
    if st.button("Apply Reclassification", disabled=not confirm):
        con = connect()
        try:
            applied = reclassify_transactions(
                con,
                transaction_ids=transaction_ids,
                dry_run=False,
                respect_manual_overrides=respect_manual,
            )
        finally:
            con.close()
        st.cache_data.clear()
        st.session_state.pop(preview_key, None)
        st.success(f"Applied {len(applied):,} reclassification change(s).")
        st.rerun()


def format_import_batch(batches: pd.DataFrame, batch_id: str) -> str:
    row = batches[batches["import_batch_id"] == batch_id].iloc[0]
    return f"{row['imported_at']} | {row['source_file']} | {row['status']}"


def render_drilldown(df: pd.DataFrame) -> None:
    st.title("Drilldown")
    st.caption("Pick a metric and see the transactions that make up the number.")

    col1, col2, col3 = st.columns(3)
    metric = col1.selectbox("Metric", DRILLDOWN_METRICS, index=DRILLDOWN_METRICS.index("Excluded From Spend"))
    months = ["All"] + sorted(df["month"].dropna().unique().tolist(), reverse=True)
    month = col2.selectbox("Month", months)
    accounts = ["All"] + sorted(df["account_name"].dropna().unique().tolist())
    account = col3.selectbox("Account", accounts)

    drill_df = df[df["transaction_type"].isin(drilldown_metric_types(metric))].copy()
    if month != "All":
        drill_df = drill_df[drill_df["month"] == month]
    if account != "All":
        drill_df = drill_df[drill_df["account_name"] == account]

    if metric == "Gross Spend":
        total = drill_df["gross_spend"].sum()
    elif metric == "Refunds/Credits":
        total = drill_df["refund_credit_abs"].sum()
    elif metric == "Personal Net Spend":
        total = drill_df["net_spend"].sum()
    elif metric == "Income":
        total = drill_df["income_amount"].sum()
    elif metric == "Card Payments":
        total = drill_df["payment_amount"].sum()
    elif metric == "Debt Payments":
        total = drill_df["debt_payment_amount"].sum()
    elif metric == "Internal Transfers":
        total = drill_df["transfer_amount"].sum()
    elif metric == "Reimbursements":
        total = drill_df["reimbursement_amount"].sum()
    elif metric == "Prepaid Card Reloads":
        total = drill_df["stored_value_reload_amount"].sum()
    elif metric == "Needs Review":
        total = drill_df["manual_review_amount"].sum()
    else:
        total = drill_df["ignored_movement"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric(metric, money(float(total)))
    col2.metric("Transactions", f"{len(drill_df):,}")
    col3.metric("Accounts", f"{drill_df['account_name'].nunique():,}" if not drill_df.empty else "0")

    if drill_df.empty:
        st.info("No transactions match this drilldown.")
        return

    by_type = (
        drill_df.groupby("transaction_type", as_index=False)
        .agg(amount=("display_amount", "sum"), transactions=("transaction_id", "count"))
        .sort_values("amount", ascending=False)
    )
    st.subheader("By Type")
    display_table(by_type)

    by_account = (
        drill_df.groupby(["account_name", "scope"], as_index=False)
        .agg(amount=("display_amount", "sum"), transactions=("transaction_id", "count"))
        .sort_values("amount", ascending=False)
    )
    st.subheader("By Account")
    display_table(by_account)

    st.subheader("Transactions")
    render_transaction_table(drill_df)

    csv = drill_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download Drilldown CSV", csv, f"{metric.lower().replace(' ', '_')}_drilldown.csv", "text/csv")


def render_category_breakdown(df: pd.DataFrame) -> None:
    st.title("Category Breakdown")
    spend_df = df[df["transaction_type"].isin(spend_types())]
    if spend_df.empty:
        st.info("No spending/refund rows match the current filters.")
        return

    category_totals = (
        spend_df.groupby("category", as_index=False)
        .agg(net_spend=("net_spend", "sum"), transactions=("transaction_id", "count"))
        .sort_values("net_spend", ascending=False)
    )
    st.plotly_chart(px.bar(category_totals, x="category", y="net_spend"), width="stretch")
    display_table(category_totals)


def render_top_merchants(df: pd.DataFrame) -> None:
    st.title("Top Merchants")
    spend_df = df[df["transaction_type"].isin(spend_types())]
    merchant_totals = (
        spend_df.groupby(["merchant_clean", "category", "subcategory"], as_index=False)
        .agg(net_spend=("net_spend", "sum"), gross_spend=("gross_spend", "sum"), transactions=("transaction_id", "count"))
        .sort_values("net_spend", ascending=False)
        .head(50)
    )
    st.plotly_chart(px.bar(merchant_totals, x="net_spend", y="merchant_clean", orientation="h"), width="stretch")
    display_table(merchant_totals)


def render_recurring(df: pd.DataFrame) -> None:
    st.title("Recurring Payments")
    payments = df[df["transaction_type"] == "expense"].copy()
    recurring = (
        payments.groupby("merchant_clean")
        .agg(
            transactions=("transaction_id", "count"),
            months=("month", "nunique"),
            median_amount=("gross_spend", "median"),
            total_spend=("gross_spend", "sum"),
            first_seen=("transaction_date", "min"),
            last_seen=("transaction_date", "max"),
        )
        .reset_index()
    )
    recurring = recurring[(recurring["transactions"] >= 3) & (recurring["months"] >= 2)].sort_values(
        ["months", "total_spend"], ascending=False
    )
    display_table(recurring)


def render_uncategorized(df: pd.DataFrame) -> None:
    st.title("Merchant Rules")
    spend_df = df[df["transaction_type"].isin(spend_types())]
    queue = (
        spend_df[is_uncategorized(spend_df)]
        .groupby("merchant_raw", as_index=False)
        .agg(net_spend=("net_spend", "sum"), gross_spend=("gross_spend", "sum"), transactions=("transaction_id", "count"))
        .sort_values(["net_spend", "transactions"], ascending=False)
    )

    tab1, tab2, tab3 = st.tabs(["Uncategorized Queue", "Existing Rules", "Categories"])

    with tab1:
        if queue.empty:
            st.success("No uncategorized spending merchants match the current filters.")
        else:
            selected = st.selectbox("Merchant", queue["merchant_raw"].tolist())
            row = queue[queue["merchant_raw"] == selected].iloc[0]
            suggestion = suggest_sql_rule(selected)

            col1, col2, col3 = st.columns(3)
            col1.metric("Personal Net Spend", money(float(row["net_spend"])))
            col2.metric("Gross Spend", money(float(row["gross_spend"])))
            col3.metric("Transactions", f"{int(row['transactions']):,}")

            matching_rows = spend_df[spend_df["merchant_raw"] == selected].sort_values("transaction_date", ascending=False)
            display_table(
                matching_rows,
                ["transaction_date", "account_name", "merchant_raw", "amount", "transaction_type", "source_file"],
            )

            with st.form("merchant_rule"):
                pattern = st.text_input("Pattern", value=selected)
                match_type = st.selectbox("Match Type", ["contains", "exact", "regex"])
                merchant_clean = st.text_input(
                    "Clean Merchant",
                    value=suggestion["merchant_clean"] if suggestion else str(selected).title(),
                )
                type_options = transaction_type_options(df["transaction_type"])
                suggested_type = str(suggestion.get("transaction_type", "expense")) if suggestion else "expense"
                if suggested_type not in type_options:
                    suggested_type = "expense"
                rule_transaction_type = st.selectbox(
                    "Transaction Type",
                    type_options,
                    index=type_options.index(suggested_type),
                    format_func=display_transaction_type,
                )

                categories = available_categories(df)
                suggested_category = suggestion["category"] if suggestion else "Other"
                default_index = categories.index(suggested_category) if suggested_category in categories else categories.index("Other")
                selected_category = st.selectbox("Category", categories, index=default_index)
                custom_category = ""
                if selected_category == "Custom":
                    custom_category = st.text_input("Custom Category")

                final_category = custom_category.strip() if selected_category == "Custom" else selected_category
                subcategory_options = [""] + available_subcategories(final_category, df)
                suggested_subcategory = suggestion["subcategory"] if suggestion else ""
                subcategory_index = subcategory_options.index(suggested_subcategory) if suggested_subcategory in subcategory_options else 0
                selected_subcategory = st.selectbox("Subcategory Optional", subcategory_options, index=subcategory_index)
                custom_subcategory = st.text_input("Custom Subcategory Optional", value="")
                final_subcategory = custom_subcategory.strip() or selected_subcategory.strip()

                submitted = st.form_submit_button("Save Rule And Refresh")

            if submitted:
                requires_category = category_required_for_type(rule_transaction_type)
                category_to_save = final_category if requires_category else ""
                subcategory_to_save = final_subcategory if requires_category else ""
                if requires_category and not category_to_save:
                    st.error("Category is required. Subcategory can stay blank.")
                else:
                    if requires_category:
                        save_category_metadata(category_to_save, subcategory_to_save)
                    if requires_category and not category_pair_valid(category_to_save, subcategory_to_save):
                        st.error("Category/subcategory is not valid. Add it in the Categories tab first.")
                        st.stop()
                    save_sql_user_rule(
                        pattern,
                        merchant_clean,
                        rule_transaction_type,
                        "personal",
                        category_to_save,
                        subcategory_to_save,
                        match_type=match_type,
                        notes="Created from Merchant Rules queue.",
                    )
                    refresh_categories()
                    st.success(f"Saved user rule for {merchant_clean}.")
                    st.rerun()

    with tab2:
        show_system_rules = st.checkbox("Show default rules", value=False)
        rules = load_sql_merchant_rules(include_disabled=True)
        if not show_system_rules and not rules.empty:
            rules = rules[rules["owner_type"] == "user"]
        if rules.empty:
            st.info("No user merchant rules yet.")
        else:
            display_table(rules)
            render_user_rule_editor(rules)

    with tab3:
        render_category_manager()


def render_category_manager() -> None:
    st.subheader("Category Master")
    con = connect()
    try:
        category_master = get_category_master(con, include_disabled=True)
        user_pairs = get_user_category_pairs(con)
    finally:
        con.close()

    display_table(category_master)

    with st.form("add_category"):
        category = st.text_input("Custom Category")
        subcategory = st.text_input("Custom Subcategory Optional")
        sort_order = st.number_input("Sort Order", min_value=1, max_value=10_000, value=100, step=10)
        submitted = st.form_submit_button("Add Category")

    if submitted:
        if not category.strip():
            st.error("Category is required.")
        else:
            save_category_metadata(category, subcategory, sort_order=int(sort_order))
            st.cache_data.clear()
            st.success("Category saved.")
            st.rerun()

    st.subheader("Disable User Category")
    if user_pairs.empty:
        st.info("No user categories to disable.")
        return

    options = [
        (row.category, row.subcategory)
        for row in user_pairs.itertuples()
    ]
    selected = st.selectbox(
        "User Category",
        options,
        format_func=lambda pair: f"{pair[0]} / {pair[1]}" if pair[1] else pair[0],
    )
    confirm_disable_category = st.checkbox("I understand this disables the selected user category")
    if st.button("Disable Selected User Category", disabled=not confirm_disable_category):
        con = connect()
        try:
            disable_user_category(con, selected[0], selected[1])
        finally:
            con.close()
        st.cache_data.clear()
        st.success("User category disabled.")
        st.rerun()


def render_user_rule_editor(rules: pd.DataFrame) -> None:
    st.subheader("Edit User Rule")
    user_rules = rules[(rules["owner_type"] == "user") & (rules["enabled"].astype(bool))].copy()
    if user_rules.empty:
        st.info("Default rules are read-only. Create one of My Rules to override them.")
        return

    selected_rule_id = st.selectbox(
        "User Rule",
        user_rules["rule_id"].tolist(),
        format_func=lambda rule_id: format_rule_option(user_rules, rule_id),
    )
    row = user_rules[user_rules["rule_id"] == selected_rule_id].iloc[0]

    with st.form("edit_user_rule"):
        pattern = st.text_input("Pattern", value=str(row["pattern"]))
        match_type = st.selectbox(
            "Match Type",
            ["contains", "exact", "regex"],
            index=["contains", "exact", "regex"].index(str(row["match_type"])) if str(row["match_type"]) in ["contains", "exact", "regex"] else 0,
        )
        merchant_clean = st.text_input("Clean Merchant", value=str(row["merchant_clean"] or ""))
        type_options = transaction_type_options()
        current_type = str(row["transaction_type"] or "")
        if current_type and current_type not in type_options:
            type_options.append(current_type)
        type_choices = [""] + type_options
        transaction_type = st.selectbox(
            "Transaction Type Optional",
            type_choices,
            index=type_choices.index(current_type) if current_type in type_choices else 0,
            format_func=lambda value: "(No change)" if value == "" else display_transaction_type(value),
        )
        scope_options = ["", *SCOPES]
        current_scope = str(row["scope"] or "")
        scope = st.selectbox(
            "Scope Optional",
            scope_options,
            index=scope_options.index(current_scope) if current_scope in scope_options else 0,
            format_func=lambda value: "(No change)" if value == "" else display_scope(value),
        )
        categories = [category for category in available_categories(pd.DataFrame()) if category != "Custom"]
        current_category = str(row["category"] or "")
        if current_category and current_category not in categories:
            categories = [current_category, *categories]
        category_choices = ["", *categories]
        selected_category = st.selectbox(
            "Category Optional",
            category_choices,
            index=category_choices.index(current_category) if current_category in category_choices else 0,
            format_func=lambda value: "(Blank)" if value == "" else value,
        )
        subcategories = [""] + available_subcategories(selected_category, pd.DataFrame()) if selected_category else [""]
        current_subcategory = str(row["subcategory"] or "")
        if current_subcategory and current_subcategory not in subcategories:
            subcategories.append(current_subcategory)
        selected_subcategory = st.selectbox(
            "Subcategory Optional",
            subcategories,
            index=subcategories.index(current_subcategory) if current_subcategory in subcategories else 0,
        )
        priority = st.number_input("Priority", min_value=1, max_value=10_000, value=int(row["priority"]), step=10)
        notes = st.text_input("Notes", value=str(row["notes"] or ""))
        save_clicked = st.form_submit_button("Save User Rule")

    col1, col2 = st.columns(2)
    confirm_disable_rule = st.checkbox("I understand this disables the selected user rule")
    disable_clicked = col1.button("Disable User Rule", disabled=not confirm_disable_rule)
    refresh_clicked = col2.button("Refresh Transactions From Rules")

    if save_clicked:
        try:
            con = connect()
            try:
                update_rule(
                    con,
                    int(selected_rule_id),
                    {
                        "pattern": pattern,
                        "match_type": match_type,
                        "merchant_clean": merchant_clean,
                        "transaction_type": transaction_type,
                        "scope": scope,
                        "category": selected_category,
                        "subcategory": selected_subcategory,
                        "priority": int(priority),
                        "notes": notes,
                    },
                )
            finally:
                con.close()
            st.cache_data.clear()
            st.success("User rule updated.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    if disable_clicked:
        con = connect()
        try:
            disable_rule(con, int(selected_rule_id))
        finally:
            con.close()
        st.cache_data.clear()
        st.success("My Rule disabled. Default rules can apply again.")
        st.rerun()

    if refresh_clicked:
        refresh_categories()
        st.success("Transactions refreshed from SQL merchant rules.")
        st.rerun()


def format_rule_option(rules: pd.DataFrame, rule_id: int) -> str:
    row = rules[rules["rule_id"] == rule_id].iloc[0]
    return f"{row['rule_id']} | {row['pattern']} -> {row['merchant_clean']}"


def render_review_queue(df: pd.DataFrame) -> None:
    st.title("Review Queue")
    review_df = build_review_queue(df)

    if review_df.empty:
        st.success("No manual review transactions match the current filters.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Needs Review", money(float(review_df["display_amount"].sum())))
    col2.metric("Transactions", f"{len(review_df):,}")
    col3.metric("Accounts", f"{review_df['account_name'].nunique():,}")

    type_summary = (
        review_df.groupby(["transaction_type", "category"], as_index=False)
        .agg(amount=("display_amount", "sum"), transactions=("transaction_id", "count"))
        .sort_values("amount", ascending=False)
    )
    st.subheader("Review Summary")
    display_table(type_summary)

    st.subheader("Review Transaction")
    render_classification_workflow(review_df)

    st.subheader("Transactions")
    display_table(
        review_df,
        [
            "transaction_date",
            "amount",
            "account_name",
            "merchant_raw",
            "merchant_clean",
            "transaction_type",
            "category",
            "subcategory",
            "review_reason",
        ],
    )


def render_classification_workflow(review_df: pd.DataFrame) -> None:
    labels = {
        row.transaction_id: (
            f"{row.transaction_date} | {money(float(abs(row.amount)))} | "
            f"{display_transaction_type(row.transaction_type)} | {str(row.merchant_raw)[:90]}"
        )
        for row in review_df.itertuples()
    }
    selected_id = st.selectbox(
        "Transaction",
        review_df["transaction_id"].tolist(),
        format_func=lambda transaction_id: labels.get(transaction_id, transaction_id),
    )
    row = review_df[review_df["transaction_id"] == selected_id].iloc[0]
    suggestion = suggest_sql_rule(str(row.get("merchant_raw") or ""), score_cutoff=0)

    detail = pd.DataFrame(
        [
            {
                "transaction_date": row.get("transaction_date"),
                "amount": row.get("amount"),
                "account_name": row.get("account_name"),
                "merchant_raw": row.get("merchant_raw"),
                "merchant_clean": row.get("merchant_clean"),
                "transaction_type": row.get("transaction_type"),
                "category": row.get("category"),
                "subcategory": row.get("subcategory"),
                "review_reason": row.get("review_reason"),
            }
        ]
    )
    display_table(detail)

    if suggestion:
        st.info(
            "Suggestion: "
            f"{suggestion.get('merchant_clean') or row.get('merchant_clean')} | "
            f"{display_transaction_type(suggestion.get('transaction_type') or row.get('transaction_type'))} | "
            f"{suggestion.get('category') or '(no category)'}"
            f"{' / ' + suggestion.get('subcategory') if suggestion.get('subcategory') else ''} "
            f"(confidence {suggestion.get('score', 0)}%)"
        )
    else:
        st.info("No confident suggestion yet. Choose the right classification below.")

    with st.form("classification_review_form"):
        merchant_clean = st.text_input(
            "Clean Merchant",
            value=str((suggestion or {}).get("merchant_clean") or row.get("merchant_clean") or row.get("merchant_raw") or ""),
        )
        type_options = transaction_type_options(review_df["transaction_type"])
        suggested_type = str((suggestion or {}).get("transaction_type") or row.get("transaction_type") or "expense")
        if suggested_type not in type_options:
            type_options.append(suggested_type)
        transaction_type = st.selectbox(
            "Transaction Type",
            type_options,
            index=type_options.index(suggested_type),
            format_func=display_transaction_type,
        )

        requires_category = category_required_for_type(transaction_type)
        categories = available_categories(review_df)
        suggested_category = str((suggestion or {}).get("category") or row.get("category") or "Other")
        if suggested_category not in categories:
            suggested_category = "Other" if "Other" in categories else categories[0]
        selected_category = st.selectbox("Category", categories, index=categories.index(suggested_category), disabled=not requires_category)
        custom_category = ""
        if selected_category == "Custom" and requires_category:
            custom_category = st.text_input("Custom Category")
        final_category = (custom_category.strip() if selected_category == "Custom" else selected_category) if requires_category else ""

        subcategory_options = [""] + available_subcategories(final_category, review_df) if final_category else [""]
        suggested_subcategory = str((suggestion or {}).get("subcategory") or row.get("subcategory") or "")
        if suggested_subcategory not in subcategory_options:
            suggested_subcategory = ""
        selected_subcategory = st.selectbox(
            "Subcategory Optional",
            subcategory_options,
            index=subcategory_options.index(suggested_subcategory),
            disabled=not requires_category,
        )
        custom_subcategory = st.text_input("Custom Subcategory Optional", value="", disabled=not requires_category)
        final_subcategory = (custom_subcategory.strip() or selected_subcategory.strip()) if requires_category else ""

        match_type = st.selectbox(
            "Future Match Type",
            ["contains", "exact"],
            help="Contains works well for merchants with dates, store numbers, or extra statement text. Exact is stricter.",
        )
        default_pattern = suggest_pattern_from_raw(merchant_clean or row.get("merchant_raw"))
        rule_pattern = st.text_input("Future Match Text", value=default_pattern)

        save_once = st.form_submit_button("Save For This Transaction Only")
        apply_future = st.form_submit_button("Apply This Category To Future Similar Transactions")

    if not save_once and not apply_future:
        return

    if requires_category and not final_category:
        st.error("Category is required for this transaction type.")
        return
    if requires_category:
        save_category_metadata(final_category, final_subcategory)
        if not category_pair_valid(final_category, final_subcategory):
            st.error(f"'{final_category} / {final_subcategory or '(None)'}' is not a valid category pair.")
            return
    if apply_future and not rule_pattern.strip():
        st.error("Future Match Text is required when applying to future similar transactions.")
        return

    rule_id = None
    if apply_future:
        try:
            rule_id = save_sql_user_rule(
                rule_pattern,
                merchant_clean,
                transaction_type,
                str(row.get("scope") or "personal"),
                final_category,
                final_subcategory,
                match_type=match_type,
                priority=25,
                notes="Created from review queue.",
            )
        except ValueError as exc:
            st.error(str(exc))
            return

    con = connect()
    try:
        update_transaction_fields(
            con,
            selected_id,
            merchant_clean.strip(),
            transaction_type,
            str(row.get("scope") or "personal"),
            final_category,
            final_subcategory,
            manual_override=not apply_future,
            category_manual_override=not apply_future,
            type_manual_override=not apply_future,
            merchant_manual_override=not apply_future,
        )
        if rule_id is not None:
            preview = reclassify_transactions(con, dry_run=True, respect_manual_overrides=True)
            st.session_state["last_review_reclass_preview"] = preview[preview["matched_rule_id"] == rule_id]
    finally:
        con.close()

    st.cache_data.clear()
    if apply_future:
        preview = st.session_state.get("last_review_reclass_preview", pd.DataFrame())
        st.success(f"Saved. Future similar transactions will use this classification. {len(preview):,} historical transaction(s) may also match.")
        if preview is not None and not preview.empty:
            display_table(
                preview,
                ["transaction_date", "merchant_raw", "old_category", "new_category", "old_subcategory", "new_subcategory", "reason"],
            )
    else:
        st.success("Saved for this transaction only.")
        st.rerun()


def render_transactions(df: pd.DataFrame) -> None:
    st.title("Transactions")
    render_transaction_editor(df, key_prefix="transactions")
    render_transaction_table(df)


def render_transaction_editor(df: pd.DataFrame, key_prefix: str) -> None:
    if df.empty:
        st.info("No transactions match the current filters.")
        return

    editable = df.sort_values(["transaction_date", "account_name", "merchant_raw"], ascending=[False, True, True]).copy()
    labels = {
        row.transaction_id: (
            f"{row.transaction_date} | {row.account_name} | {display_transaction_type(row.transaction_type)} | "
            f"{money(float(abs(row.amount)))} | {str(row.merchant_raw)[:80]}"
        )
        for row in editable.itertuples()
    }

    selected_id = st.selectbox(
        "Select Transaction",
        editable["transaction_id"].tolist(),
        format_func=lambda transaction_id: labels.get(transaction_id, transaction_id),
        key=f"{key_prefix}_transaction_select",
    )
    row = editable[editable["transaction_id"] == selected_id].iloc[0]

    with st.form(f"{key_prefix}_transaction_editor"):
        col1, col2, col3 = st.columns(3)
        col1.text_input("Date", value=str(row["transaction_date"]), disabled=True)
        col2.text_input("Account", value=str(row["account_name"]), disabled=True)
        col3.text_input("Amount", value=money(float(row["amount"])), disabled=True)

        merchant_clean = st.text_input("Clean Merchant", value=str(row.get("merchant_clean") or row.get("merchant_raw") or ""))

        type_options = transaction_type_options(df["transaction_type"])
        current_type = str(row.get("transaction_type") or "expense")
        if current_type not in type_options:
            type_options.append(current_type)
        transaction_type = st.selectbox(
            "Transaction Type",
            type_options,
            index=type_options.index(current_type),
            format_func=display_transaction_type,
            help="Choose how this transaction should affect spending, income, and excluded-from-spend totals.",
        )
        st.caption(TRANSACTION_TYPE_HELP.get(display_transaction_type(transaction_type), ""))

        current_scope = str(row.get("scope") or "personal")
        scope_options = list(dict.fromkeys([current_scope, *SCOPES]))
        scope = st.selectbox("Scope", scope_options, index=0, format_func=display_scope)

        categories = available_categories(df)
        original_category = str(row.get("category") or "")
        original_subcategory = str(row.get("subcategory") or "")
        current_category = original_category or "Other"
        stale_category = False
        if current_category not in categories:
            stale_category = bool(current_category)
            current_category = "Other" if current_category == "Uncategorized" and "Other" in categories else categories[0]
        selected_category = st.selectbox("Category", categories, index=categories.index(current_category))
        custom_category = ""
        if selected_category == "Custom":
            custom_category = st.text_input("Custom Category")
        final_category = custom_category.strip() if selected_category == "Custom" else selected_category

        subcategory_options = [""] + available_subcategories(final_category, df)
        current_subcategory = original_subcategory
        stale_subcategory = False
        if original_category == "Uncategorized" and final_category == "Other":
            current_subcategory = "Uncategorized"
        if current_subcategory and current_subcategory not in subcategory_options:
            stale_subcategory = True
            current_subcategory = ""
        selected_subcategory = st.selectbox(
            "Subcategory Optional",
            subcategory_options,
            index=subcategory_options.index(current_subcategory) if current_subcategory in subcategory_options else 0,
        )
        custom_subcategory = st.text_input("Custom Subcategory Optional", value="")
        final_subcategory = custom_subcategory.strip() or selected_subcategory.strip()
        if stale_category:
            st.warning(f"Existing category '{original_category}' is not in Category Master and was not added to the dropdown.")
        if stale_subcategory:
            st.warning(
                f"Existing subcategory '{original_subcategory}' is not valid for '{final_category}' and was not added to the dropdown."
            )

        should_offer_rule = bool(str(row.get("merchant_raw") or "").strip())
        save_as_rule = st.checkbox(
            "Always apply this rule in the future",
            value=key_prefix == "review",
            disabled=not should_offer_rule,
            help="Creates one of My Rules on this device. My Rules override default rules.",
        )
        default_rule_pattern = suggest_pattern_from_raw(row.get("merchant_raw"))
        rule_pattern = st.text_input(
            "Rule Pattern",
            value=default_rule_pattern,
            help="Used only when saving a merchant rule. Use the stable merchant name only; the matcher also checks compact variants like PHOANHVU.",
        )

        submitted = st.form_submit_button("Save Transaction")

    if submitted:
        requires_category = category_required_for_type(transaction_type)
        category_to_save = final_category if requires_category else ""
        subcategory_to_save = final_subcategory if requires_category else ""

        if requires_category and not category_to_save:
            st.error("Category is required for this transaction type. Subcategory can stay blank.")
            return
        if requires_category and selected_category != "Custom" and not category_pair_valid(category_to_save, subcategory_to_save):
            st.error(f"'{category_to_save} / {subcategory_to_save or '(None)'}' is not a valid category pair.")
            return
        if save_as_rule and not rule_pattern.strip():
            st.error("Rule Pattern is required when saving a merchant rule.")
            return
        if requires_category and selected_category == "Custom":
            save_category_metadata(category_to_save, subcategory_to_save)
        if requires_category and not category_pair_valid(category_to_save, subcategory_to_save):
            st.error(f"'{category_to_save} / {subcategory_to_save or '(None)'}' is not a valid category pair.")
            return
        con = connect()
        try:
            update_transaction_fields(
                con,
                selected_id,
                merchant_clean.strip(),
                transaction_type,
                scope or "personal",
                category_to_save,
                subcategory_to_save,
                manual_override=not save_as_rule,
            )
        finally:
            con.close()
        if save_as_rule:
            try:
                save_sql_user_rule(
                    rule_pattern,
                    merchant_clean,
                    transaction_type,
                    scope or "personal",
                    category_to_save,
                    subcategory_to_save,
                    match_type="contains",
                    notes="Created from transaction editor.",
                )
            except ValueError as exc:
                st.error(str(exc))
                return
            refresh_categories()
            st.success("Transaction updated and similar merchants refreshed.")
        else:
            st.cache_data.clear()
            st.success("Transaction updated.")
        st.rerun()


def render_transaction_table(df: pd.DataFrame) -> None:
    columns = [
        "transaction_date",
        "account_name",
        "transaction_type",
        "scope",
        "merchant_raw",
        "merchant_clean",
        "category",
        "subcategory",
        "amount",
        "source_file",
    ]
    display_table(df.sort_values("transaction_date", ascending=False), columns)


def render_imports(import_log: pd.DataFrame) -> None:
    st.title("Imports")
    st.caption("Add CSV/PDF statements, preview totals, then import into the local DuckDB file.")
    ensure_project_dirs()

    uploaded_files = st.file_uploader(
        "Statement Files",
        type=["csv", "pdf"],
        accept_multiple_files=True,
        help="Files are saved locally to imports/to_import before import.",
    )
    if st.button("Add Files", disabled=not uploaded_files):
        saved_names = []
        for uploaded_file in uploaded_files:
            destination = unique_destination(TO_IMPORT_DIR, uploaded_file.name)
            destination.write_bytes(uploaded_file.getbuffer())
            saved_names.append(destination.name)
        st.success(f"Added {len(saved_names)} file(s) to imports/to_import.")
        st.rerun()

    pending_files = supported_import_files(TO_IMPORT_DIR)
    st.subheader("Pending Files")
    if pending_files:
        display_table(
            pd.DataFrame(
                [
                    {
                        "file": path.name,
                        "type": path.suffix.lower().lstrip("."),
                        "size_kb": round(path.stat().st_size / 1024, 1),
                    }
                    for path in pending_files
                ]
            )
        )

        col1, col2 = st.columns(2)
        if col1.button("Preview Pending Files"):
            previews = []
            errors = []
            for path in pending_files:
                try:
                    previews.append(preview_file(path).__dict__)
                except Exception as exc:
                    errors.append({"file": path.name, "error": str(exc)})
            if previews:
                display_table(pd.DataFrame([display_import_preview(preview) for preview in previews]))
            if errors:
                st.error("Some files could not be previewed.")
                display_table(pd.DataFrame(errors))

        if col2.button("Import Pending Files"):
            results = [ingest_file(path) for path in pending_files]
            display_table(pd.DataFrame(results))
            st.cache_data.clear()
            st.success("Import finished.")
    else:
        st.info("No pending files. Upload statements above or place them in imports/to_import.")

    st.subheader("Import History")
    if import_log.empty:
        st.info("No imports yet on this local install.")
    else:
        display_table(import_log)


def render_empty_state() -> None:
    st.title("Personal Finance")
    st.info("Start from the Imports page by uploading CSV/PDF statements.")


def database_exists() -> bool:
    return DB_PATH.exists()


def render_first_time_setup() -> None:
    st.title("Welcome To Personal Finance")
    st.info("Your financial data stays on this device.")
    st.write("Create a local database, then import CSV or PDF statements from your bank. No subscription or cloud account is required.")

    with st.form("first_time_setup"):
        base_currency = st.selectbox("Base Currency", ["CAD", "USD"], index=0)
        region = st.selectbox("Region", ["Canada", "United States"], index=0)
        submitted = st.form_submit_button("Create Local Database")

    if not submitted:
        return

    ensure_project_dirs()
    con = connect()
    try:
        save_app_setting(con, "base_currency", base_currency)
        save_app_setting(con, "region", region)
        save_app_setting(con, "setup_completed_at", datetime.now().isoformat(timespec="seconds"))
    finally:
        con.close()
    st.cache_data.clear()
    st.success("Local database created. You can import statements now.")
    st.session_state["first_page"] = "Imports"
    st.rerun()


def render_settings(transactions: pd.DataFrame) -> None:
    st.title("Settings")
    ensure_project_dirs()

    con = connect()
    try:
        settings = load_app_settings(con)
        rules = load_sql_merchant_rules(include_disabled=True)
    finally:
        con.close()

    st.subheader("Local Database")
    st.text_input("Database Path", value=str(DB_PATH), disabled=True)
    st.text_input("Base Currency", value=settings.get("base_currency", "CAD"), disabled=True)
    st.text_input("Region", value=settings.get("region", "Canada"), disabled=True)

    col1, col2 = st.columns(2)
    if col1.button("Export Backup", disabled=not DB_PATH.exists()):
        backup_path = create_database_backup()
        st.success(f"Backup created: {backup_path.name}")
    uploaded_backup = col2.file_uploader("Restore Backup", type=["zip", "duckdb", "db"], accept_multiple_files=False)
    if uploaded_backup is not None:
        st.warning("Restoring replaces the current local database. A rollback backup will be created first.")
        confirm_restore = st.checkbox("I understand restore replaces the current database")
        if st.button("Restore Uploaded Backup", disabled=not confirm_restore):
            restore_backup(bytes(uploaded_backup.getbuffer()))
            st.cache_data.clear()
            st.success("Backup restored.")
            st.rerun()

    if DB_PATH.exists():
        st.download_button(
            "Download Current Database",
            DB_PATH.read_bytes(),
            file_name=f"finance_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.duckdb",
            mime="application/octet-stream",
        )

    st.subheader("Export")
    if transactions.empty:
        st.info("No transactions to export yet.")
    else:
        st.download_button(
            "Export Transactions CSV",
            transactions.to_csv(index=False).encode("utf-8"),
            "transactions.csv",
            "text/csv",
        )

    if not rules.empty:
        st.download_button(
            "Export My Rules",
            rules[rules["owner_type"] == "user"].to_json(orient="records", indent=2).encode("utf-8"),
            "my_rules.json",
            "application/json",
        )

    st.subheader("Reset")
    st.caption("This removes imported/sample transactions and audit rows. Default categories, source profiles, and default rules remain.")
    confirm_reset = st.checkbox("I understand this removes imported/sample data from this local database")
    if st.button("Reset Imported/Sample Data", disabled=not confirm_reset):
        backup_path = create_database_backup() if DB_PATH.exists() else None
        con = connect()
        try:
            reset_imported_data(con)
        finally:
            con.close()
        st.cache_data.clear()
        message = "Imported/sample data reset."
        if backup_path:
            message += f" Backup created: {backup_path.name}"
        st.success(message)
        st.rerun()


def create_database_backup() -> Path:
    return export_backup(DB_PATH)


def restore_database_backup(buffer: bytes) -> None:
    restore_backup(bytes(buffer), DB_PATH)


def main() -> None:
    st.set_page_config(page_title="Personal Finance", layout="wide")
    if not database_exists():
        render_first_time_setup()
        return

    transactions, import_log = load_data()
    df = money_frame(transactions)

    pages = [
        "Imports",
        "Overview",
        "Monthly Detail",
        "Audit",
        "Drilldown",
        "Category Breakdown",
        "Top Merchants",
        "Recurring Payments",
        "Review Queue",
        "Merchant Rules",
        "Transactions",
        "Settings",
    ]
    default_page = st.session_state.pop("first_page", "Imports")
    default_index = pages.index(default_page) if default_page in pages else 0
    page = st.sidebar.radio(
        "View",
        pages,
        index=default_index,
    )

    if df.empty:
        if page == "Imports":
            render_imports(import_log)
        elif page == "Settings":
            render_settings(transactions)
        else:
            render_empty_state()
        return

    filtered = filter_panel(df)

    if page == "Overview":
        render_overview(filtered)
    elif page == "Monthly Detail":
        render_monthly_detail(filtered)
    elif page == "Audit":
        render_reconciliation(filtered)
    elif page == "Drilldown":
        render_drilldown(filtered)
    elif page == "Category Breakdown":
        render_category_breakdown(filtered)
    elif page == "Top Merchants":
        render_top_merchants(filtered)
    elif page == "Recurring Payments":
        render_recurring(filtered)
    elif page == "Review Queue":
        render_review_queue(filtered)
    elif page == "Merchant Rules":
        render_uncategorized(filtered)
    elif page == "Transactions":
        render_transactions(filtered)
    elif page == "Imports":
        render_imports(import_log)
    elif page == "Settings":
        render_settings(transactions)


if __name__ == "__main__":
    main()
