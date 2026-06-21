from __future__ import annotations

import pandas as pd
import streamlit as st

from services.category_service import (
    available_categories,
    available_subcategories,
    category_pair_valid,
    disable_category_metadata,
    load_category_master,
    load_user_category_pairs,
    save_category_metadata,
)
from services.dashboard_service import spend_types
from services.review_service import is_uncategorized
from services.rule_service import (
    disable_user_rule,
    refresh_categories,
    save_sql_user_rule,
    suggest_rule_pattern,
    update_user_rule,
)
from services.transaction_service import (
    category_required_for_type,
    transaction_type_labels,
    transaction_type_options,
    update_transaction_classification,
)
from .constants import (
    COLUMN_LABELS,
    SCOPES,
    SCOPE_LABELS,
    TRANSACTION_TYPE_HELP,
)

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
    category_master = load_category_master(include_disabled=True)
    user_pairs = load_user_category_pairs()

    display_table(category_master)

    with st.form("add_custom_category"):
        category = st.text_input("Custom Category")
        sort_order = st.number_input("Sort Order", min_value=1, max_value=10_000, value=100, step=10)
        add_category_clicked = st.form_submit_button("Add Category")

    if add_category_clicked:
        if not category.strip():
            st.error("Category is required.")
        else:
            try:
                save_category_metadata(category, sort_order=int(sort_order))
                st.cache_data.clear()
                st.success("Category saved.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    enabled_categories = [category for category in available_categories() if category != "Custom"]
    with st.form("add_custom_subcategory"):
        parent_category = st.selectbox(
            "Parent Category",
            ["", *enabled_categories],
            format_func=lambda value: "Select a category" if value == "" else value,
        )
        subcategory = st.text_input("Custom Subcategory")
        subcategory_sort_order = st.number_input(
            "Subcategory Sort Order",
            min_value=1,
            max_value=10_000,
            value=100,
            step=10,
        )
        add_subcategory_clicked = st.form_submit_button("Add Subcategory")

    if add_subcategory_clicked:
        if not parent_category:
            st.error("Select an existing category before adding a subcategory.")
        elif not subcategory.strip():
            st.error("Subcategory is required.")
        else:
            try:
                save_category_metadata(
                    parent_category,
                    subcategory,
                    sort_order=int(subcategory_sort_order),
                )
                st.cache_data.clear()
                st.success("Subcategory saved.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

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
        disable_category_metadata(selected[0], selected[1])
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
            update_user_rule(
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
            st.cache_data.clear()
            st.success("User rule updated.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    if disable_clicked:
        disable_user_rule(int(selected_rule_id))
        st.cache_data.clear()
        st.success("My Rule disabled. Default rules can apply again.")
        st.rerun()

    if refresh_clicked:
        refresh_categories()
        st.cache_data.clear()
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

        original_category = str(row.get("category") or "")
        original_subcategory = str(row.get("subcategory") or "")
        category_locked = transaction_type in {"income", "ignored"}
        if transaction_type == "income":
            categories = ["Income"]
            current_category = "Income"
        elif transaction_type == "ignored":
            categories = ["Excluded"]
            current_category = "Excluded"
        else:
            categories = available_categories(df)
            current_category = original_category or "Other"
        stale_category = False
        if current_category not in categories:
            stale_category = bool(current_category)
            current_category = "Other" if current_category == "Uncategorized" and "Other" in categories else categories[0]
        selected_category = st.selectbox(
            "Category",
            categories,
            index=categories.index(current_category),
            disabled=category_locked,
        )
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
            disabled=transaction_type == "ignored",
        )
        custom_subcategory = st.text_input(
            "New Custom Subcategory Optional",
            value="",
            disabled=transaction_type == "ignored",
            help="When provided, this is saved under the selected existing category.",
        )
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
        default_rule_pattern = suggest_rule_pattern(row.get("merchant_raw"))
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
        if transaction_type == "ignored":
            category_to_save = "Excluded"
            subcategory_to_save = ""

        if requires_category and not category_to_save:
            st.error("Category is required for this transaction type. Subcategory can stay blank.")
            return
        if selected_category == "Custom" and final_subcategory:
            st.error("Save the custom category first, then add a subcategory under it.")
            return
        if save_as_rule and not rule_pattern.strip():
            st.error("Rule Pattern is required when saving a merchant rule.")
            return
        if requires_category:
            try:
                if selected_category == "Custom":
                    save_category_metadata(category_to_save)
                elif custom_subcategory:
                    save_category_metadata(category_to_save, subcategory_to_save)
            except ValueError as exc:
                st.error(str(exc))
                return
        if category_to_save and not category_pair_valid(category_to_save, subcategory_to_save):
            st.error(f"'{category_to_save} / {subcategory_to_save or '(None)'}' is not a valid category pair.")
            return
        update_transaction_classification(
            selected_id,
            merchant_clean.strip(),
            transaction_type,
            scope or "personal",
            category_to_save,
            subcategory_to_save,
            manual_override=not save_as_rule,
        )
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
            st.cache_data.clear()
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
