from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.components import display_table


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

