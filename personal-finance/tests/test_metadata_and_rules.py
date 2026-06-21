from __future__ import annotations

import pandas as pd


def test_db_migrations_seed_metadata(app_modules):
    con = app_modules.db.connect()
    try:
        assert app_modules.db.verify_schema(con) == []
        assert con.execute("SELECT count(*) FROM transaction_type_master").fetchone()[0] >= 11
        assert con.execute("SELECT count(*) FROM category_master").fetchone()[0] >= 60
        assert con.execute("SELECT count(*) FROM source_profile").fetchone()[0] >= 1
        assert con.execute("SELECT count(*) FROM merchant_rule").fetchone()[0] >= 1
        assert list(app_modules.paths.BACKUPS_DIR.glob("finance_pre_migration_*.duckdb")) == []
    finally:
        con.close()


def test_category_subcategory_validation_uses_master_data(app_modules):
    con = app_modules.db.connect()
    try:
        assert app_modules.metadata.validate_category_pair(con, "Food", "Coffee")
        assert not app_modules.metadata.validate_category_pair(con, "Food", "Credit Card Payment")

        app_modules.metadata.add_user_category(con, "Food", "Tea")
        assert app_modules.metadata.validate_category_pair(con, "Food", "Tea")

        app_modules.metadata.disable_user_category(con, "Food", "Tea")
        assert not app_modules.metadata.validate_category_pair(con, "Food", "Tea")
    finally:
        con.close()


def test_transaction_type_defaults_do_not_pollute_categories(app_modules):
    rows = pd.DataFrame(
        [
            {"transaction_type": "payment", "category": "Debt Payment", "subcategory": "Credit Card Payment"},
            {"transaction_type": "transfer", "category": "Transfer", "subcategory": "Internal Transfer"},
            {"transaction_type": "income", "category": "Income", "subcategory": "Salary"},
            {"transaction_type": "reimbursement", "category": "Other", "subcategory": "Uncategorized"},
            {"transaction_type": "expense", "category": "Food", "subcategory": "Coffee"},
        ]
    )

    normalized = app_modules.normalize.apply_transaction_type_defaults(rows)

    assert normalized.loc[0, "category"] == ""
    assert normalized.loc[0, "subcategory"] == ""
    assert normalized.loc[1, "category"] == ""
    assert normalized.loc[1, "subcategory"] == ""
    assert normalized.loc[2, "category"] == "Income"
    assert normalized.loc[2, "subcategory"] == "Salary"
    assert normalized.loc[3, "category"] == ""
    assert normalized.loc[3, "subcategory"] == ""
    assert normalized.loc[4, "category"] == "Food"
    assert normalized.loc[4, "subcategory"] == "Coffee"


def test_user_rule_overrides_default_rule_and_can_fall_back(app_modules):
    con = app_modules.db.connect()
    try:
        default_rule = app_modules.categorize.match_merchant_rule(con, "COSTCO WHOLESALE")
        assert default_rule is not None
        assert default_rule.owner_type == "system"
        assert (default_rule.category, default_rule.subcategory) == ("Grocery", "")

        user_rule_id = app_modules.categorize.save_user_merchant_rule(
            con,
            pattern="COSTCO",
            match_type="contains",
            merchant_clean="Costco",
            transaction_type="expense",
            scope="personal",
            category="Food",
            subcategory="Dining",
            priority=1,
            notes="Test override",
        )
        user_rule = app_modules.categorize.match_merchant_rule(con, "COSTCO WHOLESALE")
        assert user_rule is not None
        assert user_rule.rule_id == user_rule_id
        assert user_rule.owner_type == "user"
        assert (user_rule.category, user_rule.subcategory) == ("Food", "Dining")

        app_modules.categorize.disable_rule(con, user_rule_id)
        fallback_rule = app_modules.categorize.match_merchant_rule(con, "COSTCO WHOLESALE")
        assert fallback_rule is not None
        assert fallback_rule.owner_type == "system"
        assert (fallback_rule.category, fallback_rule.subcategory) == ("Grocery", "")
    finally:
        con.close()
