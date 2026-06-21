"""DuckDB storage helpers for recurring credit card due dates."""

from __future__ import annotations

import argparse
import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb


DB_PATH = Path(__file__).resolve().parent / "cards.duckdb"
TABLE_NAME = "credit_card_bills"
SEQUENCE_NAME = "credit_card_bills_recurring_id_seq"
SAFETY_BUFFER_DAYS = 7


class DatabaseError(RuntimeError):
    """Raised when a database operation cannot be completed."""


@dataclass(frozen=True)
class CreditCard:
    id: int
    card_name: str
    due_day: int
    current_due_date: date
    is_paid: bool
    paid_at: datetime | None
    created_at: datetime

    @property
    def pay_by_date(self) -> date:
        """Return the conservative date shown to the user."""
        return conservative_pay_by_date(self.current_due_date)


def _connect() -> duckdb.DuckDBPyConnection:
    try:
        return duckdb.connect(str(DB_PATH))
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc


def _table_columns(connection: duckdb.DuckDBPyConnection) -> set[str]:
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = ?
        """,
        [TABLE_NAME],
    ).fetchall()
    return {row[0] for row in rows}


def _create_recurring_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE_NAME}")
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INTEGER PRIMARY KEY DEFAULT nextval('{SEQUENCE_NAME}'),
            card_name VARCHAR NOT NULL,
            due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
            current_due_date DATE NOT NULL,
            is_paid BOOLEAN NOT NULL DEFAULT FALSE,
            paid_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _migrate_one_time_bills(connection: duckdb.DuckDBPyConnection) -> None:
    """Convert the original due_date schema without losing existing cards."""
    legacy_rows = connection.execute(
        f"""
        SELECT card_name, due_date, is_paid, paid_at, created_at
        FROM {TABLE_NAME}
        ORDER BY id
        """
    ).fetchall()

    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute(
            f"ALTER TABLE {TABLE_NAME} RENAME TO credit_card_bills_legacy"
        )
        _create_recurring_schema(connection)

        for card_name, due_date, is_paid, paid_at, created_at in legacy_rows:
            due_day = due_date.day
            current_due_date = (
                next_month_due_date(due_date, due_day) if is_paid else due_date
            )
            connection.execute(
                f"""
                INSERT INTO {TABLE_NAME} (
                    card_name,
                    due_day,
                    current_due_date,
                    is_paid,
                    paid_at,
                    created_at
                )
                VALUES (?, ?, ?, FALSE, ?, ?)
                """,
                [card_name, due_day, current_due_date, paid_at, created_at],
            )

        connection.execute("DROP TABLE credit_card_bills_legacy")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def initialize_database() -> None:
    """Create the recurring-card schema or migrate the original schema."""
    connection = _connect()
    try:
        columns = _table_columns(connection)
        if not columns:
            _create_recurring_schema(connection)
        elif {"due_day", "current_due_date"}.issubset(columns):
            _create_recurring_schema(connection)
        elif "due_date" in columns:
            _migrate_one_time_bills(connection)
        else:
            raise DatabaseError(
                "The credit_card_bills table has an unsupported schema."
            )
    except DatabaseError:
        raise
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def due_date_for_month(year: int, month: int, due_day: int) -> date:
    """Return a due date, clamping days 29-31 to a shorter month's final day."""
    if not 1 <= due_day <= 31:
        raise ValueError("Monthly due day must be between 1 and 31.")
    final_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(due_day, final_day))


def current_or_next_due_date(due_day: int, today: date | None = None) -> date:
    """Find this month's due date, or next month's if it has already passed."""
    reference_date = today or date.today()
    candidate = due_date_for_month(
        reference_date.year,
        reference_date.month,
        due_day,
    )
    if candidate >= reference_date:
        return candidate
    return next_month_due_date(candidate, due_day)


def next_month_due_date(current_due_date: date, due_day: int) -> date:
    """Advance one calendar month while preserving the configured due day."""
    if current_due_date.month == 12:
        year, month = current_due_date.year + 1, 1
    else:
        year, month = current_due_date.year, current_due_date.month + 1
    return due_date_for_month(year, month, due_day)


def conservative_pay_by_date(projected_due_date: date) -> date:
    """Return a pay-by date no more than one week before the projection."""
    if not isinstance(projected_due_date, date):
        raise ValueError("Projected due date must be a valid date.")
    return projected_due_date - timedelta(days=SAFETY_BUFFER_DAYS)


def add_card(card_name: str, current_due_date: date) -> None:
    """Add a recurring card using one exact statement due date as its anchor."""
    cleaned_name = card_name.strip()
    if not cleaned_name:
        raise ValueError("Card name cannot be empty.")
    if not isinstance(current_due_date, date):
        raise ValueError("Current statement due date must be a valid date.")
    if current_due_date < date.today():
        raise ValueError("Current statement due date cannot be in the past.")

    due_day = current_due_date.day
    connection = _connect()
    try:
        connection.execute(
            f"""
            INSERT INTO {TABLE_NAME} (card_name, due_day, current_due_date)
            VALUES (?, ?, ?)
            """,
            [cleaned_name, due_day, current_due_date],
        )
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def get_cards() -> list[CreditCard]:
    """Return recurring cards sorted by their current due date."""
    connection = _connect()
    try:
        rows = connection.execute(
            f"""
            SELECT
                id,
                card_name,
                due_day,
                current_due_date,
                is_paid,
                paid_at,
                created_at
            FROM {TABLE_NAME}
            ORDER BY current_due_date ASC, id ASC
            """
        ).fetchall()
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()

    return [CreditCard(*row) for row in rows]


def mark_card_paid(card_id: int) -> None:
    """Record a payment and immediately advance the card by one billing cycle."""
    connection = _connect()
    try:
        row = connection.execute(
            f"""
            SELECT current_due_date, due_day
            FROM {TABLE_NAME}
            WHERE id = ?
            """,
            [card_id],
        ).fetchone()
        if row is None:
            raise ValueError("Credit card could not be found.")

        current_due_date, due_day = row
        next_due_date = next_month_due_date(current_due_date, due_day)

        connection.execute("BEGIN TRANSACTION")
        try:
            connection.execute(
                f"""
                UPDATE {TABLE_NAME}
                SET
                    current_due_date = ?,
                    is_paid = FALSE,
                    paid_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                [next_due_date, card_id],
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
    except ValueError:
        raise
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def seed_example_cards() -> None:
    """Add a few sample recurring cards, skipping exact duplicates."""
    initialize_database()
    today = date.today()
    samples = [
        ("Everyday Visa", 5, current_or_next_due_date(5, today)),
        ("Travel Mastercard", 15, current_or_next_due_date(15, today)),
        ("Store Card", 31, current_or_next_due_date(31, today)),
    ]

    connection = _connect()
    try:
        for card_name, due_day, current_due_date in samples:
            exists = connection.execute(
                f"""
                SELECT 1
                FROM {TABLE_NAME}
                WHERE card_name = ? AND due_day = ?
                LIMIT 1
                """,
                [card_name, due_day],
            ).fetchone()
            if not exists:
                connection.execute(
                    f"""
                    INSERT INTO {TABLE_NAME} (
                        card_name,
                        due_day,
                        current_due_date
                    )
                    VALUES (?, ?, ?)
                    """,
                    [
                        card_name,
                        due_day,
                        current_due_date,
                    ],
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
        help="add three example recurring credit cards",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _parse_args()
    if arguments.seed:
        seed_example_cards()
        print(f"Sample cards added to {DB_PATH}")
    else:
        initialize_database()
        print(f"Database ready at {DB_PATH}")
