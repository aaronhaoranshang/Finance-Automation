from __future__ import annotations

import pandas as pd
import streamlit as st

from categorize import suggest_pattern_from_raw
from db import connect, update_transaction_fields
from reclassify import reclassify_transactions
from ui.components import (
    available_categories,
    available_subcategories,
    build_review_queue,
    category_pair_valid,
    category_required_for_type,
    display_table,
    display_transaction_type,
    money,
    save_category_metadata,
    save_sql_user_rule,
    suggest_sql_rule,
    transaction_type_options,
)


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

