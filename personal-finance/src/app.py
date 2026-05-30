from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from categorize import categorize_transactions, load_rules, save_rule, suggest_rule
from db import connect, load_import_log, load_transactions, update_categorizations, update_transaction_fields
from ingest import ingest_file, preview_file, supported_import_files, unique_destination
from normalize import classify_transaction
from paths import ADMIN_CLASSIFICATION_RULES_PATH, ADMIN_SOURCE_RULES_PATH, TO_IMPORT_DIR, ensure_project_dirs


DEFAULT_CATEGORIES = [
    "Food",
    "Groceries",
    "Housing",
    "Utilities",
    "Transportation",
    "Travel",
    "Shopping",
    "Health",
    "Entertainment",
    "Subscriptions",
    "Fees",
    "Income",
    "Interest",
    "Reimbursement",
    "Cash Movement",
    "Manual Review",
    "Transfer",
    "Debt Payment",
    "Other",
]

DEFAULT_SUBCATEGORIES = {
    "Food": ["Dining", "Delivery", "Coffee", "Snacks"],
    "Groceries": ["Supermarket", "Warehouse", "Specialty"],
    "Housing": ["Rent", "Mortgage", "Maintenance"],
    "Utilities": ["Phone", "Internet", "Hydro", "Gas", "Water"],
    "Transportation": ["Fuel", "Transit", "Parking", "Ride Share", "Maintenance"],
    "Travel": ["Flight", "Hotel", "Car Rental", "Activities"],
    "Shopping": ["Clothing", "Electronics", "Home", "Personal"],
    "Health": ["Pharmacy", "Dental", "Medical", "Fitness"],
    "Entertainment": ["Movies", "Events", "Games", "Streaming"],
    "Subscriptions": ["Software", "Media", "Membership"],
    "Fees": ["Bank Fee", "Interest", "Service Charge"],
    "Income": ["Salary", "Rent", "Bonus"],
    "Interest": ["Savings Interest", "GIC Interest"],
    "Reimbursement": ["Friend Payback", "Refund"],
    "Cash Movement": ["PayPower Reload"],
    "Manual Review": [],
    "Transfer": ["Internal Transfer"],
    "Debt Payment": ["Credit Card Payment", "Loan Payment"],
    "Other": [],
}

SPEND_TYPES = ["expense", "refund", "credit"]
IGNORED_MOVEMENT_TYPES = ["payment", "debt_payment", "transfer", "reimbursement", "stored_value_reload"]
REVIEW_TYPES = ["manual_review"]
TRANSACTION_TYPES = [
    "expense",
    "refund",
    "credit",
    "income",
    "payment",
    "debt_payment",
    "transfer",
    "reimbursement",
    "stored_value_reload",
    "manual_review",
    "zero",
]
SCOPES = ["personal", "shared"]

DRILLDOWN_METRICS = {
    "Gross Spend": ["expense"],
    "Refunds/Credits": ["refund", "credit"],
    "Net Spend": ["expense", "refund", "credit"],
    "Income": ["income"],
    "Card Payments": ["payment"],
    "Debt Payments": ["debt_payment"],
    "Transfers": ["transfer"],
    "Reimbursements": ["reimbursement"],
    "Stored Value Reloads": ["stored_value_reload"],
    "Needs Review": ["manual_review"],
    "Ignored Movement": IGNORED_MOVEMENT_TYPES,
}


def money_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    framed = df.copy()
    framed["transaction_date"] = pd.to_datetime(framed["transaction_date"], errors="coerce")
    if "transaction_type" not in framed.columns:
        framed["transaction_type"] = framed.apply(classify_transaction, axis=1)
    else:
        missing_type = framed["transaction_type"].isna() | (framed["transaction_type"] == "")
        if missing_type.any():
            framed.loc[missing_type, "transaction_type"] = framed.loc[missing_type].apply(classify_transaction, axis=1)

    framed["amount"] = pd.to_numeric(framed["amount"], errors="coerce").fillna(0)
    if "scope" not in framed.columns:
        framed["scope"] = "personal"
    framed["scope"] = framed["scope"].fillna("personal").replace("", "personal")
    framed["gross_spend"] = framed["amount"].where(framed["transaction_type"] == "expense", 0)
    framed["refund_credit"] = framed["amount"].where(framed["transaction_type"].isin(["refund", "credit"]), 0)
    framed["refund_credit_abs"] = framed["refund_credit"].abs()
    framed["net_spend"] = framed["gross_spend"] + framed["refund_credit"]
    framed["income_amount"] = framed["amount"].where(framed["transaction_type"] == "income", 0).abs()
    framed["payment_amount"] = framed["amount"].where(framed["transaction_type"] == "payment", 0).abs()
    framed["debt_payment_amount"] = framed["amount"].where(framed["transaction_type"] == "debt_payment", 0).abs()
    framed["transfer_amount"] = framed["amount"].where(framed["transaction_type"] == "transfer", 0).abs()
    framed["reimbursement_amount"] = framed["amount"].where(framed["transaction_type"] == "reimbursement", 0).abs()
    framed["stored_value_reload_amount"] = framed["amount"].where(framed["transaction_type"] == "stored_value_reload", 0).abs()
    framed["manual_review_amount"] = framed["amount"].where(framed["transaction_type"] == "manual_review", 0).abs()
    framed["ignored_movement"] = (
        framed["payment_amount"]
        + framed["debt_payment_amount"]
        + framed["transfer_amount"]
        + framed["reimbursement_amount"]
        + framed["stored_value_reload_amount"]
    )
    framed["month"] = framed["transaction_date"].dt.to_period("M").astype(str)
    framed["display_amount"] = framed["amount"].abs()
    framed["category"] = framed["category"].fillna("Uncategorized").replace("", "Uncategorized")
    framed["subcategory"] = framed["subcategory"].fillna("")
    return framed


@st.cache_data(ttl=5)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    con = connect()
    try:
        return load_transactions(con), load_import_log(con)
    finally:
        con.close()


def refresh_categories() -> None:
    con = connect()
    try:
        transactions = load_transactions(con)
        refreshed = categorize_transactions(transactions, load_rules())
        update_categorizations(con, refreshed)
    finally:
        con.close()
    st.cache_data.clear()


def admin_rules_available() -> bool:
    return ADMIN_CLASSIFICATION_RULES_PATH.exists() and ADMIN_SOURCE_RULES_PATH.exists()


def import_mode_control() -> bool:
    if not admin_rules_available():
        st.caption("Import mode: Generic")
        return False
    return st.toggle(
        "Use private local rules",
        value=False,
        help="Keeps shared installs generic by default. Turn this on only for a local customized setup.",
    )


def available_categories(df: pd.DataFrame) -> list[str]:
    from_rules = [rule.category for rule in load_rules()]
    from_db = df["category"].dropna().astype(str).tolist() if not df.empty and "category" in df.columns else []
    return sorted({*DEFAULT_CATEGORIES, *from_rules, *from_db, "Custom"})


def available_subcategories(category: str, df: pd.DataFrame) -> list[str]:
    values = set(DEFAULT_SUBCATEGORIES.get(category, []))
    for rule in load_rules():
        if rule.category == category and rule.subcategory:
            values.add(rule.subcategory)
    if not df.empty and {"category", "subcategory"}.issubset(df.columns):
        values.update(df.loc[df["category"] == category, "subcategory"].dropna().astype(str))
    values.discard("")
    return sorted(values)


def filter_panel(df: pd.DataFrame) -> pd.DataFrame:
    with st.sidebar:
        st.header("Filters")
        months = sorted(df["month"].dropna().unique().tolist(), reverse=True)
        selected_months = st.multiselect("Months", months, default=months[:1] if months else [])

        accounts = sorted(df["account_name"].dropna().unique().tolist())
        selected_accounts = st.multiselect("Accounts", accounts, default=accounts)

        scopes = sorted(df["scope"].dropna().unique().tolist())
        selected_scopes = st.multiselect("Scope", scopes, default=scopes)

        types = sorted(df["transaction_type"].dropna().unique().tolist())
        selected_types = st.multiselect("Transaction Types", types, default=types)

    filtered = df.copy()
    if selected_months:
        filtered = filtered[filtered["month"].isin(selected_months)]
    if selected_accounts:
        filtered = filtered[filtered["account_name"].isin(selected_accounts)]
    if selected_scopes:
        filtered = filtered[filtered["scope"].isin(selected_scopes)]
    if selected_types:
        filtered = filtered[filtered["transaction_type"].isin(selected_types)]
    return filtered


def summary_by_month(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby("month", as_index=False)
        .agg(
            gross_spend=("gross_spend", "sum"),
            refunds_credits=("refund_credit_abs", "sum"),
            net_spend=("net_spend", "sum"),
            income=("income_amount", "sum"),
            card_payments=("payment_amount", "sum"),
            debt_payments=("debt_payment_amount", "sum"),
            transfers=("transfer_amount", "sum"),
            reimbursements=("reimbursement_amount", "sum"),
            stored_value_reloads=("stored_value_reload_amount", "sum"),
            manual_review=("manual_review_amount", "sum"),
            ignored_movement=("ignored_movement", "sum"),
            transactions=("transaction_id", "count"),
        )
        .sort_values("month")
    )


def metric_row(df: pd.DataFrame) -> None:
    gross_spend = float(df["gross_spend"].sum())
    refunds = float(df["refund_credit_abs"].sum())
    net_spend = float(df["net_spend"].sum())
    income = float(df["income_amount"].sum())
    manual_review = float(df["manual_review_amount"].sum())
    ignored = float(df["ignored_movement"].sum())
    uncategorized = int(((df["category"] == "Uncategorized") & df["transaction_type"].isin(SPEND_TYPES)).sum())

    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
    col1.metric("Net Spend", money(net_spend))
    col2.metric("Gross Spend", money(gross_spend))
    col3.metric("Refunds/Credits", money(refunds))
    col4.metric("Income", money(income))
    col5.metric("Needs Review", money(manual_review))
    col6.metric("Ignored Movement", money(ignored))
    col7.metric("Uncategorized", f"{uncategorized:,}")


def money(value: float) -> str:
    return f"${value:,.2f}"


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
    st.plotly_chart(px.bar(chart_data, x="month", y="amount", color="metric", barmode="group"), width="stretch")
    st.dataframe(monthly, width="stretch", hide_index=True)

    account_summary = (
        df.groupby(["account_name", "transaction_type"], as_index=False)
        .agg(amount=("display_amount", "sum"), transactions=("transaction_id", "count"))
        .sort_values(["account_name", "transaction_type"])
    )
    st.subheader("Account Activity")
    st.dataframe(account_summary, width="stretch", hide_index=True)


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
    spend_df = month_df[month_df["transaction_type"].isin(SPEND_TYPES)]

    with tab1:
        category = spend_df.groupby("category", as_index=False)["net_spend"].sum().sort_values("net_spend", ascending=False)
        st.plotly_chart(px.bar(category, x="category", y="net_spend"), width="stretch")
        st.dataframe(category, width="stretch", hide_index=True)

    with tab2:
        subcategory = (
            spend_df.assign(subcategory=spend_df["subcategory"].replace("", "(None)"))
            .groupby(["category", "subcategory"], as_index=False)["net_spend"]
            .sum()
            .sort_values("net_spend", ascending=False)
        )
        st.dataframe(subcategory, width="stretch", hide_index=True)

    with tab3:
        merchants = (
            spend_df.groupby(["merchant_clean", "category", "subcategory"], as_index=False)
            .agg(net_spend=("net_spend", "sum"), transactions=("transaction_id", "count"))
            .sort_values("net_spend", ascending=False)
        )
        st.dataframe(merchants, width="stretch", hide_index=True)

    with tab4:
        accounts = (
            month_df.groupby(["account_name", "transaction_type"], as_index=False)
            .agg(amount=("display_amount", "sum"), transactions=("transaction_id", "count"))
            .sort_values(["account_name", "transaction_type"])
        )
        st.dataframe(accounts, width="stretch", hide_index=True)

    with tab5:
        render_transaction_table(month_df)


def render_reconciliation(df: pd.DataFrame) -> None:
    st.title("Audit")
    st.caption("Use these tables to check totals by month, account, source file, and transaction type.")

    monthly = summary_by_month(df)
    st.subheader("Monthly Totals")
    st.dataframe(monthly, width="stretch", hide_index=True)

    by_account_month = (
        df.groupby(["month", "account_name"], as_index=False)
        .agg(
            gross_spend=("gross_spend", "sum"),
            refunds_credits=("refund_credit_abs", "sum"),
            net_spend=("net_spend", "sum"),
            income=("income_amount", "sum"),
            payments=("payment_amount", "sum"),
            debt_payments=("debt_payment_amount", "sum"),
            transfers=("transfer_amount", "sum"),
            reimbursements=("reimbursement_amount", "sum"),
            stored_value_reloads=("stored_value_reload_amount", "sum"),
            manual_review=("manual_review_amount", "sum"),
            ignored_movement=("ignored_movement", "sum"),
            file_net=("amount", "sum"),
            transactions=("transaction_id", "count"),
        )
        .sort_values(["month", "account_name"])
    )
    st.subheader("By Account And Month")
    st.dataframe(by_account_month, width="stretch", hide_index=True)

    by_source = (
        df.groupby(["source_file", "account_name"], as_index=False)
        .agg(
            first_date=("transaction_date", "min"),
            last_date=("transaction_date", "max"),
            net_spend=("net_spend", "sum"),
            income=("income_amount", "sum"),
            reimbursements=("reimbursement_amount", "sum"),
            stored_value_reloads=("stored_value_reload_amount", "sum"),
            manual_review=("manual_review_amount", "sum"),
            ignored_movement=("ignored_movement", "sum"),
            file_net=("amount", "sum"),
            transactions=("transaction_id", "count"),
        )
        .sort_values(["last_date", "source_file"])
    )
    st.subheader("By Source File")
    st.dataframe(by_source, width="stretch", hide_index=True)

    csv = by_account_month.to_csv(index=False).encode("utf-8")
    st.download_button("Download Account-Month CSV", csv, "account_month_reconciliation.csv", "text/csv")


def render_drilldown(df: pd.DataFrame) -> None:
    st.title("Drilldown")
    st.caption("Pick a metric and see the transactions that make up the number.")

    col1, col2, col3 = st.columns(3)
    metric = col1.selectbox("Metric", list(DRILLDOWN_METRICS.keys()), index=list(DRILLDOWN_METRICS.keys()).index("Ignored Movement"))
    months = ["All"] + sorted(df["month"].dropna().unique().tolist(), reverse=True)
    month = col2.selectbox("Month", months)
    accounts = ["All"] + sorted(df["account_name"].dropna().unique().tolist())
    account = col3.selectbox("Account", accounts)

    drill_df = df[df["transaction_type"].isin(DRILLDOWN_METRICS[metric])].copy()
    if month != "All":
        drill_df = drill_df[drill_df["month"] == month]
    if account != "All":
        drill_df = drill_df[drill_df["account_name"] == account]

    if metric == "Gross Spend":
        total = drill_df["gross_spend"].sum()
    elif metric == "Refunds/Credits":
        total = drill_df["refund_credit_abs"].sum()
    elif metric == "Net Spend":
        total = drill_df["net_spend"].sum()
    elif metric == "Income":
        total = drill_df["income_amount"].sum()
    elif metric == "Card Payments":
        total = drill_df["payment_amount"].sum()
    elif metric == "Debt Payments":
        total = drill_df["debt_payment_amount"].sum()
    elif metric == "Transfers":
        total = drill_df["transfer_amount"].sum()
    elif metric == "Reimbursements":
        total = drill_df["reimbursement_amount"].sum()
    elif metric == "Stored Value Reloads":
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
    st.dataframe(by_type, width="stretch", hide_index=True)

    by_account = (
        drill_df.groupby(["account_name", "scope"], as_index=False)
        .agg(amount=("display_amount", "sum"), transactions=("transaction_id", "count"))
        .sort_values("amount", ascending=False)
    )
    st.subheader("By Account")
    st.dataframe(by_account, width="stretch", hide_index=True)

    st.subheader("Transactions")
    render_transaction_table(drill_df)

    csv = drill_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download Drilldown CSV", csv, f"{metric.lower().replace(' ', '_')}_drilldown.csv", "text/csv")


def render_category_breakdown(df: pd.DataFrame) -> None:
    st.title("Category Breakdown")
    spend_df = df[df["transaction_type"].isin(SPEND_TYPES)]
    if spend_df.empty:
        st.info("No spending/refund rows match the current filters.")
        return

    category_totals = (
        spend_df.groupby("category", as_index=False)
        .agg(net_spend=("net_spend", "sum"), transactions=("transaction_id", "count"))
        .sort_values("net_spend", ascending=False)
    )
    st.plotly_chart(px.bar(category_totals, x="category", y="net_spend"), width="stretch")
    st.dataframe(category_totals, width="stretch", hide_index=True)


def render_top_merchants(df: pd.DataFrame) -> None:
    st.title("Top Merchants")
    spend_df = df[df["transaction_type"].isin(SPEND_TYPES)]
    merchant_totals = (
        spend_df.groupby(["merchant_clean", "category", "subcategory"], as_index=False)
        .agg(net_spend=("net_spend", "sum"), gross_spend=("gross_spend", "sum"), transactions=("transaction_id", "count"))
        .sort_values("net_spend", ascending=False)
        .head(50)
    )
    st.plotly_chart(px.bar(merchant_totals, x="net_spend", y="merchant_clean", orientation="h"), width="stretch")
    st.dataframe(merchant_totals, width="stretch", hide_index=True)


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
    st.dataframe(recurring, width="stretch", hide_index=True)


def render_uncategorized(df: pd.DataFrame) -> None:
    st.title("Merchant Rules")
    spend_df = df[df["transaction_type"].isin(SPEND_TYPES)]
    queue = (
        spend_df[spend_df["category"] == "Uncategorized"]
        .groupby("merchant_raw", as_index=False)
        .agg(net_spend=("net_spend", "sum"), gross_spend=("gross_spend", "sum"), transactions=("transaction_id", "count"))
        .sort_values(["net_spend", "transactions"], ascending=False)
    )

    tab1, tab2 = st.tabs(["Uncategorized Queue", "Existing Rules"])

    with tab1:
        if queue.empty:
            st.success("No uncategorized spending merchants match the current filters.")
        else:
            selected = st.selectbox("Merchant", queue["merchant_raw"].tolist())
            row = queue[queue["merchant_raw"] == selected].iloc[0]
            suggestion = suggest_rule(selected)

            col1, col2, col3 = st.columns(3)
            col1.metric("Net Spend", money(float(row["net_spend"])))
            col2.metric("Gross Spend", money(float(row["gross_spend"])))
            col3.metric("Transactions", f"{int(row['transactions']):,}")

            matching_rows = spend_df[spend_df["merchant_raw"] == selected].sort_values("transaction_date", ascending=False)
            st.dataframe(
                matching_rows[
                    ["transaction_date", "account_name", "merchant_raw", "amount", "transaction_type", "source_file"]
                ],
                width="stretch",
                hide_index=True,
            )

            with st.form("merchant_rule"):
                pattern = st.text_input("Pattern", value=selected)
                match_type = st.selectbox("Match Type", ["contains", "exact", "regex"])
                merchant_clean = st.text_input(
                    "Clean Merchant",
                    value=suggestion["merchant_clean"] if suggestion else str(selected).title(),
                )

                categories = available_categories(df)
                suggested_category = suggestion["category"] if suggestion else "Other"
                default_index = categories.index(suggested_category) if suggested_category in categories else categories.index("Other")
                selected_category = st.selectbox("Category", categories, index=default_index)
                custom_category = ""
                if selected_category == "Custom":
                    custom_category = st.text_input("Custom Category")

                final_category = custom_category.strip() if selected_category == "Custom" else selected_category
                subcategory_options = [""] + available_subcategories(final_category, df)
                suggested_subcategory = suggestion["subcategory"] if suggestion else ""
                subcategory_index = subcategory_options.index(suggested_subcategory) if suggested_subcategory in subcategory_options else 0
                selected_subcategory = st.selectbox("Subcategory Optional", subcategory_options, index=subcategory_index)
                custom_subcategory = st.text_input("Custom Subcategory Optional", value="")
                final_subcategory = custom_subcategory.strip() or selected_subcategory.strip()

                submitted = st.form_submit_button("Save Rule And Refresh")

            if submitted:
                if not final_category:
                    st.error("Category is required. Subcategory can stay blank.")
                else:
                    save_rule(pattern, merchant_clean, final_category, final_subcategory, match_type=match_type)
                    refresh_categories()
                    st.success(f"Saved rule for {merchant_clean}.")
                    st.rerun()

    with tab2:
        rules = load_rules()
        if not rules:
            st.info("No merchant rules yet.")
        else:
            st.dataframe(pd.DataFrame([rule.__dict__ for rule in rules]), width="stretch", hide_index=True)


def render_review_queue(df: pd.DataFrame) -> None:
    st.title("Review Queue")
    review_df = df[
        df["transaction_type"].isin(REVIEW_TYPES)
        | df["category"].isin(["Manual Review", "Uncategorized"])
    ].copy()

    if review_df.empty:
        st.success("No manual review transactions match the current filters.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Needs Review", money(float(review_df["display_amount"].sum())))
    col2.metric("Transactions", f"{len(review_df):,}")
    col3.metric("Accounts", f"{review_df['account_name'].nunique():,}")

    type_summary = (
        review_df.groupby(["transaction_type", "category"], as_index=False)
        .agg(amount=("display_amount", "sum"), transactions=("transaction_id", "count"))
        .sort_values("amount", ascending=False)
    )
    st.subheader("Review Summary")
    st.dataframe(type_summary, width="stretch", hide_index=True)

    st.subheader("Fix One Transaction")
    render_transaction_editor(review_df, key_prefix="review")

    st.subheader("Transactions")
    render_transaction_table(review_df)


def render_transactions(df: pd.DataFrame) -> None:
    st.title("Transactions")
    render_transaction_editor(df, key_prefix="transactions")
    render_transaction_table(df)


def render_transaction_editor(df: pd.DataFrame, key_prefix: str) -> None:
    if df.empty:
        st.info("No transactions match the current filters.")
        return

    editable = df.sort_values(["transaction_date", "account_name", "merchant_raw"], ascending=[False, True, True]).copy()
    labels = {
        row.transaction_id: (
            f"{row.transaction_date} | {row.account_name} | {row.transaction_type} | "
            f"{money(float(abs(row.amount)))} | {str(row.merchant_raw)[:80]}"
        )
        for row in editable.itertuples()
    }

    selected_id = st.selectbox(
        "Select Transaction",
        editable["transaction_id"].tolist(),
        format_func=lambda transaction_id: labels.get(transaction_id, transaction_id),
        key=f"{key_prefix}_transaction_select",
    )
    row = editable[editable["transaction_id"] == selected_id].iloc[0]

    with st.form(f"{key_prefix}_transaction_editor"):
        col1, col2, col3 = st.columns(3)
        col1.text_input("Date", value=str(row["transaction_date"]), disabled=True)
        col2.text_input("Account", value=str(row["account_name"]), disabled=True)
        col3.text_input("Amount", value=money(float(row["amount"])), disabled=True)

        merchant_clean = st.text_input("Clean Merchant", value=str(row.get("merchant_clean") or row.get("merchant_raw") or ""))

        type_options = sorted({*TRANSACTION_TYPES, *df["transaction_type"].dropna().astype(str).tolist()})
        current_type = str(row.get("transaction_type") or "expense")
        if current_type not in type_options:
            type_options.append(current_type)
        transaction_type = st.selectbox(
            "Transaction Type",
            type_options,
            index=type_options.index(current_type),
        )

        current_scope = str(row.get("scope") or "personal")
        scope_options = list(dict.fromkeys([current_scope, *SCOPES]))
        scope = st.selectbox("Scope", scope_options, index=0)

        categories = available_categories(df)
        current_category = str(row.get("category") or "Uncategorized")
        if current_category not in categories:
            categories.insert(0, current_category)
        selected_category = st.selectbox("Category", categories, index=categories.index(current_category))
        custom_category = ""
        if selected_category == "Custom":
            custom_category = st.text_input("Custom Category")
        final_category = custom_category.strip() if selected_category == "Custom" else selected_category

        subcategory_options = [""] + available_subcategories(final_category, df)
        current_subcategory = str(row.get("subcategory") or "")
        if current_subcategory and current_subcategory not in subcategory_options:
            subcategory_options.append(current_subcategory)
        selected_subcategory = st.selectbox(
            "Subcategory Optional",
            subcategory_options,
            index=subcategory_options.index(current_subcategory) if current_subcategory in subcategory_options else 0,
        )
        custom_subcategory = st.text_input("Custom Subcategory Optional", value="")
        final_subcategory = custom_subcategory.strip() or selected_subcategory.strip()

        submitted = st.form_submit_button("Save Transaction")

    if submitted:
        if not final_category:
            st.error("Category is required. Subcategory can stay blank.")
            return
        con = connect()
        try:
            update_transaction_fields(
                con,
                selected_id,
                merchant_clean.strip(),
                transaction_type,
                scope or "personal",
                final_category,
                final_subcategory,
            )
        finally:
            con.close()
        st.cache_data.clear()
        st.success("Transaction updated.")
        st.rerun()


def render_transaction_table(df: pd.DataFrame) -> None:
    columns = [
        "transaction_date",
        "account_name",
        "transaction_type",
        "scope",
        "merchant_raw",
        "merchant_clean",
        "category",
        "subcategory",
        "amount",
        "source_file",
    ]
    existing_columns = [column for column in columns if column in df.columns]
    st.dataframe(df.sort_values("transaction_date", ascending=False)[existing_columns], width="stretch", hide_index=True)


def render_imports(import_log: pd.DataFrame) -> None:
    st.title("Imports")
    st.caption("Add CSV/PDF statements, preview totals, then import into the local DuckDB file.")
    ensure_project_dirs()

    use_admin = import_mode_control()

    uploaded_files = st.file_uploader(
        "Statement Files",
        type=["csv", "pdf"],
        accept_multiple_files=True,
        help="Files are saved locally to imports/to_import before import.",
    )
    if st.button("Add Files", disabled=not uploaded_files):
        saved_names = []
        for uploaded_file in uploaded_files:
            destination = unique_destination(TO_IMPORT_DIR, uploaded_file.name)
            destination.write_bytes(uploaded_file.getbuffer())
            saved_names.append(destination.name)
        st.success(f"Added {len(saved_names)} file(s) to imports/to_import.")
        st.rerun()

    pending_files = supported_import_files(TO_IMPORT_DIR)
    st.subheader("Pending Files")
    if pending_files:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "file": path.name,
                        "type": path.suffix.lower().lstrip("."),
                        "size_kb": round(path.stat().st_size / 1024, 1),
                    }
                    for path in pending_files
                ]
            ),
            width="stretch",
            hide_index=True,
        )

        col1, col2 = st.columns(2)
        if col1.button("Preview Pending Files"):
            previews = []
            errors = []
            for path in pending_files:
                try:
                    previews.append(preview_file(path, admin=use_admin).__dict__)
                except Exception as exc:
                    errors.append({"file": path.name, "error": str(exc)})
            if previews:
                st.dataframe(pd.DataFrame(previews), width="stretch", hide_index=True)
            if errors:
                st.error("Some files could not be previewed.")
                st.dataframe(pd.DataFrame(errors), width="stretch", hide_index=True)

        if col2.button("Import Pending Files"):
            results = [ingest_file(path, admin=use_admin) for path in pending_files]
            st.dataframe(pd.DataFrame(results), width="stretch", hide_index=True)
            st.cache_data.clear()
            st.success("Import finished.")
    else:
        st.info("No pending files. Upload statements above or place them in imports/to_import.")

    st.subheader("Import History")
    if import_log.empty:
        st.info("No imports yet on this local install.")
    else:
        st.dataframe(import_log, width="stretch", hide_index=True)


def render_empty_state() -> None:
    st.title("Personal Finance")
    st.info("Start from the Imports page by uploading CSV/PDF statements. New installs use generic rules by default.")


def main() -> None:
    st.set_page_config(page_title="Personal Finance", layout="wide")
    transactions, import_log = load_data()
    df = money_frame(transactions)

    page = st.sidebar.radio(
        "View",
        [
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
        ],
    )

    if df.empty:
        if page == "Imports":
            render_imports(import_log)
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


if __name__ == "__main__":
    main()
