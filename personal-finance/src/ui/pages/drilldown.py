from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.components import display_table, drilldown_metric_types, money, render_transaction_table
from ui.constants import DRILLDOWN_METRICS


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

