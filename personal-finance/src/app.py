from __future__ import annotations

import streamlit as st

from services.backup_service import database_exists
from services.dashboard_service import load_data, money_frame
from ui.components import filter_panel
from ui.pages.audit import render_reconciliation
from ui.pages.category_breakdown import render_category_breakdown
from ui.pages.drilldown import render_drilldown
from ui.pages.imports import render_imports
from ui.pages.merchant_rules import render_uncategorized
from ui.pages.merchants import render_top_merchants
from ui.pages.monthly_detail import render_monthly_detail
from ui.pages.overview import render_overview
from ui.pages.recurring import render_recurring
from ui.pages.review_queue import render_review_queue
from ui.pages.settings import render_settings
from ui.pages.setup import render_empty_state, render_first_time_setup
from ui.pages.transactions import render_transactions
from ui.theme import apply_theme, configure_page


PAGES = [
    "Imports",
    "Overview",
    "Monthly Detail",
    "Audit",
    "Drilldown",
    "Category Breakdown",
    "Top Merchants",
    "Recurring Payments",
    "Review Queue",
    "Merchant Rules",
    "Transactions",
    "Settings",
]


def main() -> None:
    configure_page()
    apply_theme()
    if not database_exists():
        render_first_time_setup()
        return

    transactions, import_log = load_data()
    df = money_frame(transactions)

    default_page = st.session_state.pop("first_page", "Imports")
    default_index = PAGES.index(default_page) if default_page in PAGES else 0
    page = st.sidebar.radio("View", PAGES, index=default_index)

    if df.empty:
        if page == "Imports":
            render_imports(import_log)
        elif page == "Settings":
            render_settings(transactions)
        else:
            render_empty_state()
        return

    filtered = filter_panel(df)

    if page == "Overview":
        render_overview(filtered)
    elif page == "Monthly Detail":
        render_monthly_detail(filtered)
    elif page == "Audit":
        render_reconciliation(filtered)
    elif page == "Drilldown":
        render_drilldown(filtered)
    elif page == "Category Breakdown":
        render_category_breakdown(filtered)
    elif page == "Top Merchants":
        render_top_merchants(filtered)
    elif page == "Recurring Payments":
        render_recurring(filtered)
    elif page == "Review Queue":
        render_review_queue(filtered)
    elif page == "Merchant Rules":
        render_uncategorized(filtered)
    elif page == "Transactions":
        render_transactions(filtered)
    elif page == "Imports":
        render_imports(import_log)
    elif page == "Settings":
        render_settings(transactions)


if __name__ == "__main__":
    main()
