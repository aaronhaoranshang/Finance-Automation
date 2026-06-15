from __future__ import annotations

from pathlib import Path

import pandas as pd
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
    load_import_log,
    load_transactions,
    update_categorizations,
    update_transaction_fields,
)
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
from paths import DB_PATH
from .constants import (
    COLUMN_LABELS,
    DRILLDOWN_METRICS,
    FALLBACK_INCOME_TYPES,
    FALLBACK_SPEND_TYPES,
    FALLBACK_TRANSACTION_TYPE_LABELS,
    FALLBACK_TRANSACTION_TYPES,
    IGNORED_MOVEMENT_TYPES,
    REVIEW_TYPES,
    SCOPES,
    SCOPE_LABELS,
    TRANSACTION_TYPE_HELP,
)


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

def create_database_backup() -> Path:
    return export_backup(DB_PATH)

def restore_database_backup(buffer: bytes) -> None:
    restore_backup(bytes(buffer), DB_PATH)

def database_exists() -> bool:
    return DB_PATH.exists()

