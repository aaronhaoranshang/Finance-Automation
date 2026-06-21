from __future__ import annotations

import importlib

import pandas as pd
import pytest


STARTER_CATEGORIES = {
    "Food",
    "Grocery",
    "Shopping",
    "Transportation",
    "Bills & Utilities",
    "Entertainment",
    "Travel",
    "Fees",
    "Other",
    "Excluded",
    "Income",
}


def test_starter_category_seed(app_modules):
    con = app_modules.db.connect()
    try:
        categories = {
            row[0]
            for row in con.execute(
                """
                SELECT DISTINCT category
                FROM category_master
                WHERE owner_type = 'system'
                  AND enabled
                """
            ).fetchall()
        }
        assert categories == STARTER_CATEGORIES
        assert "Health" not in categories
        assert "Financial Fees" not in categories
        assert "Subscriptions" not in categories
        assert "Housing" not in categories

        food_subcategories = app_modules.metadata.get_subcategories(con, "Food")
        assert food_subcategories == [
            "Dining",
            "Coffee",
            "Delivery",
        ]
        assert "Grocery" not in food_subcategories
        assert app_modules.metadata.get_subcategories(con, "Grocery") == []
        assert app_modules.metadata.get_subcategories(con, "Shopping") == []
        assert app_modules.metadata.get_subcategories(con, "Travel") == []
        assert app_modules.metadata.get_subcategories(con, "Entertainment") == [
            "Subscriptions",
            "Events",
            "Games & Hobbies",
        ]
        assert app_modules.metadata.get_subcategories(con, "Fees") == []
        assert "Interest" not in app_modules.metadata.get_subcategories(con, "Fees")
        assert app_modules.metadata.get_subcategories(con, "Income") == [
            "Salary",
            "Interest",
            "Tax Refund",
            "Bonus",
            "Other Income",
        ]
    finally:
        con.close()


def test_category_only_pairs_are_valid(app_modules):
    con = app_modules.db.connect()
    try:
        assert app_modules.metadata.validate_category_pair(con, "Shopping", "")
        assert app_modules.metadata.validate_category_pair(con, "Travel", "")
        assert app_modules.metadata.validate_category_pair(con, "Other", "")
        assert app_modules.metadata.validate_category_pair(con, "Fees", "")
        assert app_modules.metadata.validate_category_pair(con, "Excluded", "")
    finally:
        con.close()


def test_user_category_and_subcategory_require_existing_parent(app_modules):
    category_service = importlib.import_module("services.category_service")

    category_service.save_category_metadata("Pets")
    assert category_service.category_pair_valid("Pets", "")

    category_service.save_category_metadata("Shopping", "Clothing")
    assert category_service.category_pair_valid("Shopping", "Clothing")
    assert "Clothing" in category_service.available_subcategories("Shopping")
    assert "Clothing" not in category_service.available_subcategories("Food")

    with pytest.raises(ValueError, match="existing category"):
        category_service.save_category_metadata("Not Yet Created", "Child")

    with pytest.raises(ValueError, match="Select an existing category"):
        category_service.save_category_metadata("", "Orphan")

    con = app_modules.db.connect()
    try:
        app_modules.metadata.disable_user_category(con, "Pets", "")
    finally:
        con.close()

    with pytest.raises(ValueError, match="existing category"):
        category_service.save_category_metadata("Pets", "Food")


def test_category_service_does_not_infer_from_transactions(app_modules):
    category_service = importlib.import_module("services.category_service")
    historical = pd.DataFrame(
        [
            {
                "category": "Historical Only",
                "subcategory": "Legacy Value",
            }
        ]
    )

    assert "Historical Only" not in category_service.available_categories(historical)
    assert category_service.available_subcategories("Historical Only", historical) == []

    con = app_modules.db.connect()
    try:
        con.execute(
            """
            INSERT INTO transactions (
                transaction_id,
                transaction_date,
                merchant_raw,
                merchant_clean,
                amount,
                transaction_type,
                scope,
                category,
                subcategory
            )
            VALUES (
                'historical-invalid',
                DATE '2026-06-01',
                'OLD PAYMENT LABEL',
                'Old Payment Label',
                50.00,
                'expense',
                'personal',
                'Food',
                'Loan Payment'
            )
            """
        )
        assert "Loan Payment" not in app_modules.metadata.get_subcategories(con, "Food")
        assert not app_modules.metadata.validate_category_pair(con, "Food", "Loan Payment")
    finally:
        con.close()


def test_user_categories_survive_starter_seed_migration(app_modules):
    con = app_modules.db.connect()
    try:
        app_modules.metadata.add_user_category(con, "Pets")
        migration_path = app_modules.paths.BUNDLED_MIGRATIONS_DIR / "013_simplify_starter_categories.sql"
        con.execute(migration_path.read_text(encoding="utf-8"))

        row = con.execute(
            """
            SELECT enabled
            FROM category_master
            WHERE owner_type = 'user'
              AND category = 'Pets'
              AND subcategory = ''
            """
        ).fetchone()
        assert row == (True,)
    finally:
        con.close()


def test_income_defaults_and_category_validation(app_modules):
    assert "income" not in app_modules.normalize.CATEGORYLESS_TRANSACTION_TYPES

    normalized = app_modules.normalize.apply_transaction_type_defaults(
        pd.DataFrame(
            [
                {
                    "transaction_type": "income",
                    "category": "",
                    "subcategory": "",
                },
                {
                    "transaction_type": "income",
                    "category": "Income",
                    "subcategory": "Salary",
                },
                {
                    "transaction_type": "income",
                    "category": "Legacy Income",
                    "subcategory": "Bonus",
                },
            ]
        )
    )
    assert normalized.loc[0, ["category", "subcategory"]].tolist() == [
        "Income",
        "Other Income",
    ]
    assert normalized.loc[1, ["category", "subcategory"]].tolist() == [
        "Income",
        "Salary",
    ]
    assert normalized.loc[2, ["category", "subcategory"]].tolist() == [
        "Income",
        "Bonus",
    ]

    con = app_modules.db.connect()
    try:
        assert app_modules.metadata.transaction_type_requires_category(con, "income")
        assert app_modules.metadata.validate_category_pair(con, "Income", "Salary")
    finally:
        con.close()


def test_income_and_ignored_transaction_type_metadata(app_modules):
    dashboard_service = importlib.import_module("services.dashboard_service")

    con = app_modules.db.connect()
    try:
        ignored = con.execute(
            """
            SELECT display_name, affects_spend, affects_income, affects_cash_flow, requires_category
            FROM transaction_type_master
            WHERE transaction_type = 'ignored'
            """
        ).fetchone()
        assert ignored == ("Excluded", False, False, False, False)

        income = con.execute(
            """
            SELECT affects_spend, affects_income, requires_category
            FROM transaction_type_master
            WHERE transaction_type = 'income'
            """
        ).fetchone()
        assert income == (False, True, True)
    finally:
        con.close()

    normalized = app_modules.normalize.apply_transaction_type_defaults(
        pd.DataFrame(
            [
                {
                    "transaction_id": "income",
                    "transaction_date": "2026-06-01",
                    "transaction_type": "income",
                    "amount": -1000.0,
                    "category": "",
                    "subcategory": "",
                },
                {
                    "transaction_id": "ignored",
                    "transaction_date": "2026-06-02",
                    "transaction_type": "ignored",
                    "amount": 42.0,
                    "category": "",
                    "subcategory": "",
                },
            ]
        )
    )
    assert normalized.loc[0, ["category", "subcategory"]].tolist() == [
        "Income",
        "Other Income",
    ]
    assert normalized.loc[1, ["category", "subcategory"]].tolist() == [
        "Excluded",
        "",
    ]

    framed = dashboard_service.money_frame(normalized)
    ignored_row = framed[framed["transaction_id"] == "ignored"].iloc[0]
    income_row = framed[framed["transaction_id"] == "income"].iloc[0]
    assert ignored_row["net_spend"] == 0
    assert ignored_row["income_amount"] == 0
    assert ignored_row["ignored_amount"] == 42.0
    assert income_row["gross_spend"] == 0
    assert income_row["net_spend"] == 0
    assert income_row["income_amount"] == 1000.0
