from __future__ import annotations

from datetime import datetime

import streamlit as st

from db import connect, save_app_setting
from paths import ensure_project_dirs


def render_empty_state() -> None:
    st.title("Personal Finance")
    st.info("Start from the Imports page by uploading CSV/PDF statements.")

def render_first_time_setup() -> None:
    st.title("Welcome To Personal Finance")
    st.info("Your financial data stays on this device.")
    st.write("Create a local database, then import CSV or PDF statements from your bank. No subscription or cloud account is required.")

    with st.form("first_time_setup"):
        base_currency = st.selectbox("Base Currency", ["CAD", "USD"], index=0)
        region = st.selectbox("Region", ["Canada", "United States"], index=0)
        submitted = st.form_submit_button("Create Local Database")

    if not submitted:
        return

    ensure_project_dirs()
    con = connect()
    try:
        save_app_setting(con, "base_currency", base_currency)
        save_app_setting(con, "region", region)
        save_app_setting(con, "setup_completed_at", datetime.now().isoformat(timespec="seconds"))
    finally:
        con.close()
    st.cache_data.clear()
    st.success("Local database created. You can import statements now.")
    st.session_state["first_page"] = "Imports"
    st.rerun()

