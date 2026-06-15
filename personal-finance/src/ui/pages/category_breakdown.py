from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from ui.components import display_table, spend_types


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

