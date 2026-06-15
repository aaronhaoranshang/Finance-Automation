from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.components import render_transaction_editor, render_transaction_table


def render_transactions(df: pd.DataFrame) -> None:
    st.title("Transactions")
    render_transaction_editor(df, key_prefix="transactions")
    render_transaction_table(df)

