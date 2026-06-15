from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from ui.components import display_table, spend_types


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

