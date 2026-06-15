from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from services.dashboard_service import summary_by_month
from ui.components import display_metric, display_table, metric_row


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
