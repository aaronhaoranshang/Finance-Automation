from __future__ import annotations

import importlib

import pandas as pd


def test_service_modules_import(app_modules):
    service_modules = [
        "services.backup_service",
        "services.category_service",
        "services.dashboard_service",
        "services.import_service",
        "services.review_service",
        "services.rule_service",
        "services.transaction_service",
    ]

    for module_name in service_modules:
        assert importlib.import_module(module_name)


def test_dashboard_service_money_frame_and_summary(app_modules):
    dashboard_service = importlib.import_module("services.dashboard_service")

    raw = pd.DataFrame(
        [
            {
                "transaction_id": "expense-1",
                "transaction_date": "2026-04-01",
                "transaction_type": "expense",
                "amount": 100.0,
                "category": "",
                "subcategory": "",
            },
            {
                "transaction_id": "refund-1",
                "transaction_date": "2026-04-02",
                "transaction_type": "refund",
                "amount": -10.0,
                "category": "Shopping",
                "subcategory": "General",
            },
            {
                "transaction_id": "reimbursement-1",
                "transaction_date": "2026-04-03",
                "transaction_type": "reimbursement",
                "amount": 20.0,
                "category": "",
                "subcategory": "",
            },
            {
                "transaction_id": "income-1",
                "transaction_date": "2026-04-04",
                "transaction_type": "income",
                "amount": 500.0,
                "category": "Income",
                "subcategory": "Salary",
            },
            {
                "transaction_id": "payment-1",
                "transaction_date": "2026-04-05",
                "transaction_type": "payment",
                "amount": -50.0,
                "category": "",
                "subcategory": "",
            },
            {
                "transaction_id": "debt-payment-1",
                "transaction_date": "2026-04-06",
                "transaction_type": "debt_payment",
                "amount": -75.0,
                "category": "",
                "subcategory": "",
            },
            {
                "transaction_id": "transfer-1",
                "transaction_date": "2026-04-07",
                "transaction_type": "transfer",
                "amount": -200.0,
                "category": "",
                "subcategory": "",
            },
            {
                "transaction_id": "ignored-1",
                "transaction_date": "2026-04-08",
                "transaction_type": "ignored",
                "amount": 300.0,
                "category": "Excluded",
                "subcategory": "",
            },
            {
                "transaction_id": "excluded-expense-1",
                "transaction_date": "2026-04-09",
                "transaction_type": "expense",
                "amount": 25.0,
                "category": "Excluded",
                "subcategory": "",
            },
        ]
    )

    framed = dashboard_service.money_frame(raw)
    assert framed.loc[framed["transaction_id"] == "expense-1", "category"].iloc[0] == "Uncategorized"
    ignored = framed.loc[framed["transaction_id"] == "ignored-1"].iloc[0]
    assert ignored["gross_spend"] == 0
    assert ignored["net_spend"] == 0
    assert ignored["income_amount"] == 0
    excluded_expense = framed.loc[framed["transaction_id"] == "excluded-expense-1"].iloc[0]
    assert excluded_expense["gross_spend"] == 25.0
    assert excluded_expense["net_spend"] == 25.0

    summary = dashboard_service.summary_by_month(framed)
    row = summary.iloc[0]
    assert row["month"] == "2026-04"
    assert row["gross_spend"] == 125.0
    assert row["refunds_credits"] == 10.0
    assert row["reimbursements"] == 20.0
    assert row["net_spend"] == 95.0
    assert row["income"] == 500.0
    assert row["card_payments"] == 50.0
    assert row["debt_payments"] == 75.0
    assert row["transfers"] == 200.0
    assert row["ignored_movement"] == 625.0
    assert row["transactions"] == 9


def test_category_service_validation_and_user_category(app_modules):
    category_service = importlib.import_module("services.category_service")

    assert category_service.category_pair_valid("Food", "Coffee")
    assert not category_service.category_pair_valid("Food", "Credit Card Payment")

    category_service.save_category_metadata("Food", "Tea")
    assert category_service.category_pair_valid("Food", "Tea")
    assert "Tea" in category_service.available_subcategories("Food")


def test_rule_service_loads_user_rules_before_system_rules(app_modules):
    rule_service = importlib.import_module("services.rule_service")

    rule_id = rule_service.save_sql_user_rule(
        pattern="COSTCO",
        match_type="contains",
        merchant_clean="Costco",
        transaction_type="expense",
        scope="personal",
        category="Food",
        subcategory="Dining",
        priority=1,
        notes="Service wrapper test",
    )

    rules = rule_service.load_sql_merchant_rules()
    costco_rules = rules[rules["pattern"].astype(str).str.contains("COSTCO", case=False, na=False)]
    assert not costco_rules.empty
    assert int(costco_rules.iloc[0]["rule_id"]) == rule_id
    assert costco_rules.iloc[0]["owner_type"] == "user"


def test_backup_service_database_exists(app_modules):
    backup_service = importlib.import_module("services.backup_service")

    assert not backup_service.database_exists()
    con = app_modules.db.connect()
    con.close()
    assert backup_service.database_exists()
