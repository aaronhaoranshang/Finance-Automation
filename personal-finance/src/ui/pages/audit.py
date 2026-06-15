from __future__ import annotations

import pandas as pd
import streamlit as st

from reclassify import reclassify_transactions
from services.dashboard_service import summary_by_month
from services.import_service import load_import_batch_table, load_raw_import_row_table
from ui.components import display_table


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
    batches = load_import_batch_table()

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
    raw_rows = load_raw_import_row_table(selected_batch)

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
