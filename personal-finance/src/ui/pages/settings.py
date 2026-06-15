from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from db import connect, load_app_settings, reset_imported_data
from paths import DB_PATH, ensure_project_dirs
from services.backup_service import create_database_backup, restore_database_backup
from services.rule_service import load_sql_merchant_rules


def render_settings(transactions: pd.DataFrame) -> None:
    st.title("Settings")
    ensure_project_dirs()

    con = connect()
    try:
        settings = load_app_settings(con)
        rules = load_sql_merchant_rules(include_disabled=True)
    finally:
        con.close()

    st.subheader("Local Database")
    st.text_input("Database Path", value=str(DB_PATH), disabled=True)
    st.text_input("Base Currency", value=settings.get("base_currency", "CAD"), disabled=True)
    st.text_input("Region", value=settings.get("region", "Canada"), disabled=True)

    col1, col2 = st.columns(2)
    if col1.button("Export Backup", disabled=not DB_PATH.exists()):
        backup_path = create_database_backup()
        st.success(f"Backup created: {backup_path.name}")
    uploaded_backup = col2.file_uploader("Restore Backup", type=["zip", "duckdb", "db"], accept_multiple_files=False)
    if uploaded_backup is not None:
        st.warning("Restoring replaces the current local database. A rollback backup will be created first.")
        confirm_restore = st.checkbox("I understand restore replaces the current database")
        if st.button("Restore Uploaded Backup", disabled=not confirm_restore):
            restore_database_backup(bytes(uploaded_backup.getbuffer()))
            st.cache_data.clear()
            st.success("Backup restored.")
            st.rerun()

    if DB_PATH.exists():
        st.download_button(
            "Download Current Database",
            DB_PATH.read_bytes(),
            file_name=f"finance_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.duckdb",
            mime="application/octet-stream",
        )

    st.subheader("Export")
    if transactions.empty:
        st.info("No transactions to export yet.")
    else:
        st.download_button(
            "Export Transactions CSV",
            transactions.to_csv(index=False).encode("utf-8"),
            "transactions.csv",
            "text/csv",
        )

    if not rules.empty:
        st.download_button(
            "Export My Rules",
            rules[rules["owner_type"] == "user"].to_json(orient="records", indent=2).encode("utf-8"),
            "my_rules.json",
            "application/json",
        )

    st.subheader("Reset")
    st.caption("This removes imported/sample transactions and audit rows. Default categories, source profiles, and default rules remain.")
    confirm_reset = st.checkbox("I understand this removes imported/sample data from this local database")
    if st.button("Reset Imported/Sample Data", disabled=not confirm_reset):
        backup_path = create_database_backup() if DB_PATH.exists() else None
        con = connect()
        try:
            reset_imported_data(con)
        finally:
            con.close()
        st.cache_data.clear()
        message = "Imported/sample data reset."
        if backup_path:
            message += f" Backup created: {backup_path.name}"
        st.success(message)
        st.rerun()
