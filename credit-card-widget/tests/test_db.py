"""Business-logic and DuckDB tests for Credit Card Due."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import duckdb
import pytest

import db


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    database_path = tmp_path / "test-cards.duckdb"
    monkeypatch.setenv(db.DB_PATH_ENV, str(database_path))
    db.init_db()
    return database_path


def test_packaged_macos_default_db_path(monkeypatch):
    monkeypatch.delenv(db.DB_PATH_ENV, raising=False)
    monkeypatch.setattr(db.sys, "frozen", True, raising=False)
    monkeypatch.setattr(db.sys, "platform", "darwin")

    assert db.get_default_db_path() == (
        db.Path.home()
        / "Library"
        / "Application Support"
        / "Credit Card Due"
        / "cards.duckdb"
    )


def test_init_db_imports_supported_legacy_schema(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy-cards.duckdb"
    monkeypatch.setenv(db.DB_PATH_ENV, str(database_path))
    due_date = date.today() + timedelta(days=20)

    connection = duckdb.connect(str(database_path))
    try:
        connection.execute(
            """
            CREATE TABLE credit_card_bills (
                id INTEGER,
                card_name VARCHAR,
                due_day INTEGER,
                current_due_date DATE,
                is_paid BOOLEAN,
                paid_at TIMESTAMP,
                created_at TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO credit_card_bills
            VALUES (1, ?, ?, ?, FALSE, NULL, CURRENT_TIMESTAMP)
            """,
            ["Legacy Visa", due_date.day, due_date],
        )
    finally:
        connection.close()

    db.init_db()

    cards = db.get_cards()
    assert len(cards) == 1
    assert cards[0].card_name == "Legacy Visa"

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                """
            ).fetchall()
        }
    finally:
        connection.close()

    assert db.TABLE_NAME in tables
    assert "credit_card_bills_legacy" in tables


def test_clamp_day_for_short_months():
    assert db.clamp_day(2026, 2, 31) == date(2026, 2, 28)
    assert db.clamp_day(2028, 2, 31) == date(2028, 2, 29)
    assert db.clamp_day(2026, 4, 31) == date(2026, 4, 30)


def test_statement_day_31_in_february():
    assert db.calculate_statement_date(
        31,
        date(2026, 2, 1),
    ) == date(2026, 2, 28)


def test_due_day_31_in_february():
    statement_date = date(2026, 2, 5)
    assert db.calculate_due_date(
        statement_date,
        31,
        5,
    ) == date(2026, 2, 28)


def test_due_date_same_month_when_due_day_is_after_statement_day():
    assert db.calculate_due_date(
        date(2026, 7, 5),
        25,
        5,
    ) == date(2026, 7, 25)


def test_due_date_next_month_when_due_day_is_not_after_statement_day():
    assert db.calculate_due_date(
        date(2026, 7, 25),
        15,
        25,
    ) == date(2026, 8, 15)


def test_pay_by_date_calculation():
    assert db.calculate_pay_by_date(
        date(2026, 7, 25),
        7,
    ) == date(2026, 7, 18)


def test_day_31_clamps_in_february_and_returns_to_31_later():
    february_statement = db.calculate_statement_date(31, date(2026, 2, 1))
    march_statement = db.calculate_statement_date(31, date(2026, 3, 1))

    assert february_statement == date(2026, 2, 28)
    assert march_statement == date(2026, 3, 31)


def test_add_card_starts_payment_due_on_statement_date(isolated_db):
    db.add_card(
        "Statement Today Visa",
        5,
        25,
        today=date(2026, 7, 5),
    )

    card = db.get_cards(today=date(2026, 7, 5))[0]
    assert card.status == db.PAYMENT_DUE
    assert card.current_statement_date == date(2026, 7, 5)
    assert card.current_due_date == date(2026, 7, 25)


def test_add_card_starts_payment_due_after_statement_date(isolated_db):
    db.add_card(
        "Triangle WEMC",
        13,
        6,
        5,
        today=date(2026, 6, 20),
    )

    card = db.get_cards(today=date(2026, 6, 20))[0]
    assert card.status == db.PAYMENT_DUE
    assert card.current_statement_date == date(2026, 6, 13)
    assert card.current_due_date == date(2026, 7, 6)
    assert card.pay_by_date == date(2026, 7, 1)


def test_add_card_starts_no_payment_required_before_statement_date(isolated_db):
    db.add_card(
        "Future Statement Visa",
        15,
        5,
        today=date(2026, 7, 1),
    )

    card = db.get_cards(today=date(2026, 7, 1))[0]
    assert card.status == db.NO_PAYMENT_REQUIRED
    assert card.current_statement_date == date(2026, 7, 15)
    assert card.current_due_date == date(2026, 8, 5)


def test_mark_paid_changes_status_and_advances_cycle(isolated_db):
    card_id = db.add_card(
        "Test Visa",
        5,
        25,
        7,
        today=date(2026, 7, 5),
    )
    assert db.get_cards(today=date(2026, 7, 5))[0].status == db.PAYMENT_DUE

    db.mark_card_paid(
        card_id,
        paid_at=datetime(2026, 7, 10, 9, 30),
    )
    paid_card = db.get_cards(today=date(2026, 7, 10))[0]
    assert paid_card.status == db.PAID
    assert paid_card.last_paid_due_date == date(2026, 7, 25)
    assert paid_card.current_statement_date == date(2026, 8, 5)
    assert paid_card.current_due_date == date(2026, 8, 25)


def test_paid_card_stays_paid_before_next_statement(isolated_db):
    card_id = db.add_card(
        "Paid Visa",
        5,
        25,
        today=date(2026, 7, 5),
    )
    db.mark_card_paid(
        card_id,
        paid_at=datetime(2026, 7, 10, 9, 30),
    )
    before_statement = db.get_cards(today=date(2026, 8, 4))[0]
    assert before_statement.status == db.PAID


def test_paid_card_becomes_payment_due_on_next_statement(isolated_db):
    card_id = db.add_card(
        "Next Cycle Visa",
        5,
        25,
        today=date(2026, 7, 5),
    )
    db.mark_card_paid(
        card_id,
        paid_at=datetime(2026, 7, 10, 9, 30),
    )
    new_cycle = db.get_cards(today=date(2026, 8, 5))[0]
    assert new_cycle.status == db.PAYMENT_DUE
    assert new_cycle.current_statement_date == date(2026, 8, 5)
    assert new_cycle.current_due_date == date(2026, 8, 25)


def test_late_mark_paid_does_not_immediately_reopen_payment(isolated_db):
    card_id = db.add_card(
        "Late Payment Visa",
        5,
        25,
        today=date(2026, 7, 5),
    )
    db.mark_card_paid(
        card_id,
        paid_at=datetime(2026, 9, 10, 9, 30),
    )

    paid_card = db.get_cards(today=date(2026, 9, 10))[0]
    assert paid_card.status == db.PAID
    assert paid_card.current_statement_date == date(2026, 10, 5)
    assert paid_card.current_due_date == date(2026, 10, 25)


def test_refresh_transitions_waiting_card_when_statement_arrives(isolated_db):
    db.add_card(
        "Waiting Mastercard",
        15,
        5,
        today=date(2026, 7, 1),
    )
    waiting = db.get_cards(today=date(2026, 7, 14))[0]
    assert waiting.status == db.NO_PAYMENT_REQUIRED

    due = db.get_cards(today=date(2026, 7, 15))[0]
    assert due.status == db.PAYMENT_DUE
    assert due.current_due_date == date(2026, 8, 5)


def test_refresh_repairs_future_cycle_from_previous_add_algorithm(isolated_db):
    card_id = db.add_card(
        "Legacy Future Cycle",
        13,
        6,
        5,
        today=date(2026, 6, 1),
    )
    connection = duckdb.connect(str(isolated_db))
    try:
        connection.execute(
            """
            UPDATE credit_cards
            SET
                current_statement_date = DATE '2026-07-13',
                current_due_date = DATE '2026-08-06',
                status = ?
            WHERE id = ?
            """,
            [db.NO_PAYMENT_REQUIRED, card_id],
        )
    finally:
        connection.close()

    repaired = db.get_cards(today=date(2026, 6, 20))[0]
    assert repaired.status == db.PAYMENT_DUE
    assert repaired.current_statement_date == date(2026, 6, 13)
    assert repaired.current_due_date == date(2026, 7, 6)
    assert repaired.pay_by_date == date(2026, 7, 1)


def test_refresh_normalizes_due_date_to_statement_cycle(isolated_db):
    card_id = db.add_card(
        "Mismatched Cycle Visa",
        5,
        25,
        today=date(2026, 7, 5),
    )
    connection = duckdb.connect(str(isolated_db))
    try:
        connection.execute(
            """
            UPDATE credit_cards
            SET current_due_date = DATE '2026-08-25'
            WHERE id = ?
            """,
            [card_id],
        )
    finally:
        connection.close()

    normalized = db.get_cards(today=date(2026, 7, 5))[0]
    assert normalized.current_statement_date == date(2026, 7, 5)
    assert normalized.current_due_date == date(2026, 7, 25)


def test_refresh_does_not_skip_an_unhandled_statement_cycle(isolated_db):
    card_id = db.add_card(
        "Long Closed App Visa",
        5,
        25,
        today=date(2026, 7, 5),
    )
    db.mark_card_paid(card_id)

    reopened_months_later = db.get_cards(today=date(2026, 10, 1))[0]

    assert reopened_months_later.status == db.PAYMENT_DUE
    assert reopened_months_later.current_statement_date == date(2026, 8, 5)
    assert reopened_months_later.current_due_date == date(2026, 8, 25)


def test_duplicate_active_card_is_prevented(isolated_db):
    db.add_card("My Visa", 5, 25, today=date(2026, 7, 1))

    with pytest.raises(ValueError, match="already exists"):
        db.add_card("  my   visa ", 10, 28, today=date(2026, 7, 1))


def test_edit_waiting_card_uses_current_month_statement_cycle(isolated_db):
    card_id = db.add_card(
        "Editable Triangle",
        13,
        6,
        5,
        today=date(2026, 6, 1),
    )

    db.update_card(
        card_id,
        "Editable Triangle",
        13,
        6,
        5,
        today=date(2026, 6, 20),
    )

    card = db.get_cards(today=date(2026, 6, 20))[0]
    assert card.status == db.PAYMENT_DUE
    assert card.current_statement_date == date(2026, 6, 13)
    assert card.current_due_date == date(2026, 7, 6)


def test_delete_soft_deactivates_card(isolated_db):
    card_id = db.add_card(
        "Delete Me",
        5,
        25,
        today=date(2026, 7, 1),
    )
    db.delete_card(card_id)

    assert db.get_cards(today=date(2026, 7, 1)) == []
    inactive_cards = db.get_cards(
        include_inactive=True,
        today=date(2026, 7, 1),
    )
    assert len(inactive_cards) == 1
    assert inactive_cards[0].is_active is False


def test_reset_all_data_clears_cards(isolated_db):
    db.add_card("Card One", 5, 25, today=date(2026, 7, 1))
    db.add_card("Card Two", 10, 28, today=date(2026, 7, 1))

    db.reset_all_data()

    assert (
        db.get_cards(
            include_inactive=True,
            today=date(2026, 7, 1),
        )
        == []
    )


def test_undo_last_paid_restores_payment_due(isolated_db):
    card_id = db.add_card(
        "Undo Visa",
        5,
        25,
        today=date(2026, 7, 5),
    )
    db.mark_card_paid(card_id)
    db.undo_last_paid(card_id)

    restored = db.get_cards(today=date(2026, 7, 10))[0]
    assert restored.status == db.PAYMENT_DUE
    assert restored.current_statement_date == date(2026, 7, 5)
    assert restored.current_due_date == date(2026, 7, 25)
    assert restored.last_paid_at is None
    assert restored.last_paid_due_date is None


def test_undo_late_payment_restores_exact_paid_cycle(isolated_db):
    card_id = db.add_card(
        "Late Undo Visa",
        5,
        25,
        today=date(2026, 7, 5),
    )
    db.mark_card_paid(
        card_id,
        paid_at=datetime(2026, 9, 10, 9, 30),
    )
    db.undo_last_paid(card_id)

    restored = db.get_cards(today=date(2026, 9, 10))[0]
    assert restored.status == db.PAYMENT_DUE
    assert restored.current_statement_date == date(2026, 7, 5)
    assert restored.current_due_date == date(2026, 7, 25)
