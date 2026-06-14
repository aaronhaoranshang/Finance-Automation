from __future__ import annotations


def insert_transaction(con, transaction_id: str, merchant: str, category: str, subcategory: str) -> None:
    con.execute(
        """
        INSERT INTO transactions (
            transaction_id,
            transaction_date,
            posted_date,
            institution,
            account_name,
            merchant_raw,
            merchant_clean,
            amount,
            transaction_type,
            scope,
            currency,
            category,
            subcategory,
            source_file,
            ingested_at
        )
        VALUES (?, DATE '2026-01-02', DATE '2026-01-02', 'Test Bank', 'Test Card', ?, ?, 5.25,
                'expense', 'personal', 'CAD', ?, ?, 'manual', now())
        """,
        [transaction_id, merchant, merchant, category, subcategory],
    )


def test_reclassification_dry_run_and_apply_writes_audit(app_modules):
    con = app_modules.db.connect()
    try:
        insert_transaction(con, "tx-starbucks", "STARBUCKS 123", "Other", "Uncategorized")

        dry_run = app_modules.reclassify.reclassify_transactions(con, dry_run=True)
        assert len(dry_run) == 1
        change = dry_run.iloc[0]
        assert change["transaction_id"] == "tx-starbucks"
        assert change["new_category"] == "Food"
        assert change["new_subcategory"] == "Coffee"

        saved = con.execute(
            "SELECT category, subcategory FROM transactions WHERE transaction_id = 'tx-starbucks'"
        ).fetchone()
        assert saved == ("Other", "Uncategorized")

        applied = app_modules.reclassify.reclassify_transactions(con, dry_run=False)
        assert len(applied) == 1
        saved = con.execute(
            "SELECT category, subcategory FROM transactions WHERE transaction_id = 'tx-starbucks'"
        ).fetchone()
        assert saved == ("Food", "Coffee")

        audit = con.execute(
            """
            SELECT old_category, new_category, old_subcategory, new_subcategory, reason
            FROM transaction_classification_audit
            WHERE transaction_id = 'tx-starbucks'
            """
        ).fetchone()
        assert audit[:4] == ("Other", "Food", "Uncategorized", "Coffee")
        assert "Matched system rule" in audit[4]
    finally:
        con.close()
