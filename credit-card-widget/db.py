"""DuckDB storage helpers for credit card bills."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb


DB_PATH = Path(__file__).resolve().parent / "cards.duckdb"


class DatabaseError(RuntimeError):
    """Raised when a database operation cannot be completed."""


@dataclass(frozen=True)
class CreditCardBill:
    id: int
    card_name: str
    due_date: date
    is_paid: bool
    created_at: datetime
    paid_at: datetime | None


def _connect() -> duckdb.DuckDBPyConnection:
    try:
        return duckdb.connect(str(DB_PATH))
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc


def initialize_database() -> None:
    """Create the database, sequence, and bills table when missing."""
    connection = _connect()
    try:
        connection.execute("CREATE SEQUENCE IF NOT EXISTS credit_card_bills_id_seq")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_card_bills (
                id INTEGER PRIMARY KEY
                    DEFAULT nextval('credit_card_bills_id_seq'),
                card_name VARCHAR NOT NULL,
                due_date DATE NOT NULL,
                is_paid BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP
            )
            """
        )
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def add_bill(card_name: str, due_date: date) -> None:
    """Add one unpaid credit card bill."""
    cleaned_name = card_name.strip()
    if not cleaned_name:
        raise ValueError("Card name cannot be empty.")
    if not isinstance(due_date, date):
        raise ValueError("Due date must be a valid date.")

    connection = _connect()
    try:
        connection.execute(
            """
            INSERT INTO credit_card_bills (card_name, due_date)
            VALUES (?, ?)
            """,
            [cleaned_name, due_date],
        )
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def get_bills(*, is_paid: bool) -> list[CreditCardBill]:
    """Return paid or unpaid bills in a useful display order."""
    connection = _connect()
    try:
        if is_paid:
            rows = connection.execute(
                """
                SELECT id, card_name, due_date, is_paid, created_at, paid_at
                FROM credit_card_bills
                WHERE is_paid = TRUE
                ORDER BY paid_at DESC NULLS LAST, due_date DESC, id DESC
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, card_name, due_date, is_paid, created_at, paid_at
                FROM credit_card_bills
                WHERE is_paid = FALSE
                ORDER BY due_date ASC, id ASC
                """
            ).fetchall()
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()

    return [CreditCardBill(*row) for row in rows]


def mark_bill_paid(bill_id: int) -> None:
    """Mark a bill as paid and record the current time."""
    connection = _connect()
    try:
        connection.execute(
            """
            UPDATE credit_card_bills
            SET is_paid = TRUE, paid_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            [bill_id],
        )
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def mark_bill_unpaid(bill_id: int) -> None:
    """Move a paid bill back to the unpaid list."""
    connection = _connect()
    try:
        connection.execute(
            """
            UPDATE credit_card_bills
            SET is_paid = FALSE, paid_at = NULL
            WHERE id = ?
            """,
            [bill_id],
        )
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def seed_example_bills() -> None:
    """Add a few sample bills, skipping exact duplicates."""
    initialize_database()
    today = date.today()
    samples = [
        ("Everyday Visa", today + timedelta(days=3)),
        ("Travel Mastercard", today + timedelta(days=10)),
        ("Store Card", today - timedelta(days=2)),
    ]

    connection = _connect()
    try:
        for card_name, due_date in samples:
            exists = connection.execute(
                """
                SELECT 1
                FROM credit_card_bills
                WHERE card_name = ? AND due_date = ?
                LIMIT 1
                """,
                [card_name, due_date],
            ).fetchone()
            if not exists:
                connection.execute(
                    """
                    INSERT INTO credit_card_bills (card_name, due_date)
                    VALUES (?, ?)
                    """,
                    [card_name, due_date],
                )
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Credit Card Due database tools")
    parser.add_argument(
        "--seed",
        action="store_true",
        help="add three example credit card bills",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _parse_args()
    if arguments.seed:
        seed_example_bills()
        print(f"Sample bills added to {DB_PATH}")
    else:
        initialize_database()
        print(f"Database ready at {DB_PATH}")
