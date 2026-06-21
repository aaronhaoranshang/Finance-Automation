"""Business-logic and DuckDB tests for Credit Card Due."""

from __future__ import annotations

from datetime import date, datetime

import pytest

import db


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    database_path = tmp_path / "test-cards.duckdb"
    monkeypatch.setenv(db.DB_PATH_ENV, str(database_path))
    db.init_db()
    return database_path


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


def test_mark_paid_waits_until_next_statement(isolated_db):
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

    before_statement = db.get_cards(today=date(2026, 8, 4))[0]
    assert before_statement.status == db.PAID

    new_cycle = db.get_cards(today=date(2026, 8, 5))[0]
    assert new_cycle.status == db.PAYMENT_DUE
    assert new_cycle.current_due_date == date(2026, 8, 25)


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

    assert db.get_cards(
        include_inactive=True,
        today=date(2026, 7, 1),
    ) == []


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
