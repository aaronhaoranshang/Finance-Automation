from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.components import (
    available_categories,
    available_subcategories,
    category_pair_valid,
    category_required_for_type,
    display_table,
    is_uncategorized,
    load_sql_merchant_rules,
    money,
    refresh_categories,
    render_category_manager,
    render_user_rule_editor,
    save_category_metadata,
    save_sql_user_rule,
    spend_types,
    suggest_sql_rule,
    transaction_type_options,
)


def render_uncategorized(df: pd.DataFrame) -> None:
    st.title("Merchant Rules")
    spend_df = df[df["transaction_type"].isin(spend_types())]
    queue = (
        spend_df[is_uncategorized(spend_df)]
        .groupby("merchant_raw", as_index=False)
        .agg(net_spend=("net_spend", "sum"), gross_spend=("gross_spend", "sum"), transactions=("transaction_id", "count"))
        .sort_values(["net_spend", "transactions"], ascending=False)
    )

    tab1, tab2, tab3 = st.tabs(["Uncategorized Queue", "Existing Rules", "Categories"])

    with tab1:
        if queue.empty:
            st.success("No uncategorized spending merchants match the current filters.")
        else:
            selected = st.selectbox("Merchant", queue["merchant_raw"].tolist())
            row = queue[queue["merchant_raw"] == selected].iloc[0]
            suggestion = suggest_sql_rule(selected)

            col1, col2, col3 = st.columns(3)
            col1.metric("Personal Net Spend", money(float(row["net_spend"])))
            col2.metric("Gross Spend", money(float(row["gross_spend"])))
            col3.metric("Transactions", f"{int(row['transactions']):,}")

            matching_rows = spend_df[spend_df["merchant_raw"] == selected].sort_values("transaction_date", ascending=False)
            display_table(
                matching_rows,
                ["transaction_date", "account_name", "merchant_raw", "amount", "transaction_type", "source_file"],
            )

            with st.form("merchant_rule"):
                pattern = st.text_input("Pattern", value=selected)
                match_type = st.selectbox("Match Type", ["contains", "exact", "regex"])
                merchant_clean = st.text_input(
                    "Clean Merchant",
                    value=suggestion["merchant_clean"] if suggestion else str(selected).title(),
                )
                type_options = transaction_type_options(df["transaction_type"])
                suggested_type = str(suggestion.get("transaction_type", "expense")) if suggestion else "expense"
                if suggested_type not in type_options:
                    suggested_type = "expense"
                rule_transaction_type = st.selectbox(
                    "Transaction Type",
                    type_options,
                    index=type_options.index(suggested_type),
                    format_func=display_transaction_type,
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
                requires_category = category_required_for_type(rule_transaction_type)
                category_to_save = final_category if requires_category else ""
                subcategory_to_save = final_subcategory if requires_category else ""
                if requires_category and not category_to_save:
                    st.error("Category is required. Subcategory can stay blank.")
                else:
                    if requires_category:
                        save_category_metadata(category_to_save, subcategory_to_save)
                    if requires_category and not category_pair_valid(category_to_save, subcategory_to_save):
                        st.error("Category/subcategory is not valid. Add it in the Categories tab first.")
                        st.stop()
                    save_sql_user_rule(
                        pattern,
                        merchant_clean,
                        rule_transaction_type,
                        "personal",
                        category_to_save,
                        subcategory_to_save,
                        match_type=match_type,
                        notes="Created from Merchant Rules queue.",
                    )
                    refresh_categories()
                    st.success(f"Saved user rule for {merchant_clean}.")
                    st.rerun()

    with tab2:
        show_system_rules = st.checkbox("Show default rules", value=False)
        rules = load_sql_merchant_rules(include_disabled=True)
        if not show_system_rules and not rules.empty:
            rules = rules[rules["owner_type"] == "user"]
        if rules.empty:
            st.info("No user merchant rules yet.")
        else:
            display_table(rules)
            render_user_rule_editor(rules)

    with tab3:
        render_category_manager()

