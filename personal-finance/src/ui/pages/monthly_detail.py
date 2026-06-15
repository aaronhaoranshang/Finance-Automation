from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from ui.components import display_table, metric_row, render_transaction_table, spend_types


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

