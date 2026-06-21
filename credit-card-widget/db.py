"""DuckDB storage and payment-cycle logic for Credit Card Due."""

from __future__ import annotations

import argparse
import calendar
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb


DEFAULT_DB_PATH = Path(__file__).resolve().parent / "cards.duckdb"
DB_PATH_ENV = "CREDIT_CARD_WIDGET_DB_PATH"
TABLE_NAME = "credit_cards"

NO_PAYMENT_REQUIRED = "NO_PAYMENT_REQUIRED"
PAYMENT_DUE = "PAYMENT_DUE"
PAID = "PAID"
ALLOWED_STATUSES = {NO_PAYMENT_REQUIRED, PAYMENT_DUE, PAID}


class DatabaseError(RuntimeError):
    """Raised when a database operation cannot be completed."""


@dataclass(frozen=True)
class CreditCard:
    id: int
    card_name: str
    statement_day: int
    due_day: int
    safety_buffer_days: int
    current_statement_date: date | None
    current_due_date: date | None
    status: str
    last_paid_at: datetime | None
    last_paid_due_date: date | None
    created_at: datetime
    updated_at: datetime
    is_active: bool

    @property
    def pay_by_date(self) -> date | None:
        if self.current_due_date is None:
            return None
        return calculate_pay_by_date(
            self.current_due_date,
            self.safety_buffer_days,
        )


CARD_COLUMNS = """
    id,
    card_name,
    statement_day,
    due_day,
    safety_buffer_days,
    current_statement_date,
    current_due_date,
    status,
    last_paid_at,
    last_paid_due_date,
    created_at,
    updated_at,
    is_active
"""


def get_db_path() -> Path:
    """Return the configured database path."""
    configured_path = os.environ.get(DB_PATH_ENV)
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return get_default_db_path()


def get_default_db_path() -> Path:
    """Return a writable default path for source and packaged app launches."""
    if not getattr(sys, "frozen", False):
        return DEFAULT_DB_PATH

    if sys.platform == "darwin":
        data_directory = (
            Path.home() / "Library" / "Application Support" / "Credit Card Due"
        )
    elif sys.platform == "win32":
        windows_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        data_directory = (
            Path(windows_data) if windows_data else Path.home() / "AppData" / "Local"
        ) / "Credit Card Due"
    else:
        linux_data = os.environ.get("XDG_DATA_HOME")
        data_directory = (
            Path(linux_data).expanduser()
            if linux_data
            else Path.home() / ".local" / "share"
        ) / "credit-card-due"

    return data_directory / "cards.duckdb"


def _connect() -> duckdb.DuckDBPyConnection:
    path = get_db_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(path))
    except (OSError, duckdb.Error) as exc:
        raise DatabaseError(str(exc)) from exc


def _table_exists(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = ?
            LIMIT 1
            """,
            [table_name],
        ).fetchone()
        is not None
    )


def _table_columns(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
) -> set[str]:
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'main' AND table_name = ?
        """,
        [table_name],
    ).fetchall()
    return {row[0] for row in rows}


def _create_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INTEGER PRIMARY KEY,
            card_name VARCHAR NOT NULL,
            statement_day INTEGER NOT NULL,
            due_day INTEGER NOT NULL,
            safety_buffer_days INTEGER NOT NULL DEFAULT 7,
            current_statement_date DATE,
            current_due_date DATE,
            status VARCHAR NOT NULL,
            last_paid_at TIMESTAMP,
            last_paid_due_date DATE,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            CHECK (statement_day BETWEEN 1 AND 31),
            CHECK (due_day BETWEEN 1 AND 31),
            CHECK (safety_buffer_days BETWEEN 0 AND 15),
            CHECK (
                status IN (
                    'NO_PAYMENT_REQUIRED',
                    'PAYMENT_DUE',
                    'PAID'
                )
            )
        )
        """
    )


def _legacy_backup_name(connection: duckdb.DuckDBPyConnection) -> str:
    base_name = "credit_card_bills_legacy"
    candidate = base_name
    suffix = 2
    while _table_exists(connection, candidate):
        candidate = f"{base_name}_{suffix}"
        suffix += 1
    return candidate


def _migrate_legacy_cards(connection: duckdb.DuckDBPyConnection) -> None:
    """Import known demo schemas once, retaining the old table as a backup."""
    legacy_table = "credit_card_bills"
    if not _table_exists(connection, legacy_table):
        return
    if connection.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]:
        return

    columns = _table_columns(connection, legacy_table)
    recurring_schema = {
        "card_name",
        "due_day",
        "current_due_date",
        "is_paid",
        "paid_at",
        "created_at",
    }
    one_time_schema = {
        "card_name",
        "due_date",
        "is_paid",
        "paid_at",
        "created_at",
    }
    if not (recurring_schema.issubset(columns) or one_time_schema.issubset(columns)):
        return

    now = datetime.now()
    today = date.today()
    imported: list[tuple[object, ...]] = []

    if recurring_schema.issubset(columns):
        rows = connection.execute(
            f"""
            SELECT card_name, due_day, current_due_date, is_paid, paid_at, created_at
            FROM {legacy_table}
            ORDER BY id
            """
        ).fetchall()
        for card_name, due_day, due_date, is_paid, paid_at, created_at in rows:
            statement_date = due_date - timedelta(days=21)
            statement_day = statement_date.day
            status = (
                PAID
                if paid_at is not None or is_paid
                else (PAYMENT_DUE if today >= statement_date else NO_PAYMENT_REQUIRED)
            )
            imported.append(
                (
                    card_name,
                    statement_day,
                    due_day,
                    7,
                    statement_date,
                    due_date,
                    status,
                    paid_at,
                    None,
                    created_at or now,
                    now,
                    True,
                )
            )
    else:
        rows = connection.execute(
            f"""
            SELECT card_name, due_date, is_paid, paid_at, created_at
            FROM {legacy_table}
            ORDER BY id
            """
        ).fetchall()
        for card_name, due_date, is_paid, paid_at, created_at in rows:
            statement_date = due_date - timedelta(days=21)
            statement_day = statement_date.day
            due_day = due_date.day
            last_paid_due_date = due_date if is_paid else None
            if is_paid:
                statement_date = _shift_cycle_statement(
                    statement_date,
                    statement_day,
                    1,
                )
                due_date = calculate_due_date(
                    statement_date,
                    due_day,
                    statement_day,
                )
                status = PAID
            else:
                status = PAYMENT_DUE if today >= statement_date else NO_PAYMENT_REQUIRED
            imported.append(
                (
                    card_name,
                    statement_day,
                    due_day,
                    7,
                    statement_date,
                    due_date,
                    status,
                    paid_at,
                    last_paid_due_date,
                    created_at or now,
                    now,
                    True,
                )
            )

    backup_name = _legacy_backup_name(connection)
    connection.execute("BEGIN TRANSACTION")
    try:
        for record in imported:
            next_id = _next_id(connection)
            connection.execute(
                f"""
                INSERT INTO {TABLE_NAME} (
                    id,
                    card_name,
                    statement_day,
                    due_day,
                    safety_buffer_days,
                    current_statement_date,
                    current_due_date,
                    status,
                    last_paid_at,
                    last_paid_due_date,
                    created_at,
                    updated_at,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [next_id, *record],
            )
        connection.execute(f"ALTER TABLE {legacy_table} RENAME TO {backup_name}")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        # The new empty table remains usable even if legacy import is unusual.


def init_db() -> None:
    """Create the current schema and safely import supported demo data."""
    connection = _connect()
    try:
        _create_schema(connection)
        _migrate_legacy_cards(connection)
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def initialize_database() -> None:
    """Backward-compatible alias used by older entry points."""
    init_db()


def clamp_day(year: int, month: int, day: int) -> date:
    """Create a date, clamping day 29-31 to a short month's last day."""
    _validate_day(day, "Day")
    final_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, final_day))


def _shift_year_month(year: int, month: int, months: int) -> tuple[int, int]:
    month_index = year * 12 + (month - 1) + months
    return month_index // 12, month_index % 12 + 1


def _shift_cycle_statement(
    statement_date: date,
    statement_day: int,
    months: int,
) -> date:
    year, month = _shift_year_month(
        statement_date.year,
        statement_date.month,
        months,
    )
    return clamp_day(year, month, statement_day)


def calculate_statement_date(
    statement_day: int,
    reference_date: date | None = None,
    *,
    on_or_after: bool = True,
) -> date:
    """Return the nearest anchored statement date around a reference date."""
    _validate_day(statement_day, "Statement day")
    reference = reference_date or date.today()
    candidate = clamp_day(reference.year, reference.month, statement_day)
    if on_or_after and candidate < reference:
        year, month = _shift_year_month(reference.year, reference.month, 1)
        return clamp_day(year, month, statement_day)
    if not on_or_after and candidate > reference:
        year, month = _shift_year_month(reference.year, reference.month, -1)
        return clamp_day(year, month, statement_day)
    return candidate


def calculate_due_date(
    statement_date: date,
    due_day: int,
    statement_day: int | None = None,
) -> date:
    """Calculate the official due date associated with a statement cycle."""
    if not isinstance(statement_date, date):
        raise ValueError("Statement date must be a valid date.")
    _validate_day(due_day, "Due day")
    anchor_statement_day = statement_day or statement_date.day
    _validate_day(anchor_statement_day, "Statement day")
    month_offset = 0 if due_day > anchor_statement_day else 1
    year, month = _shift_year_month(
        statement_date.year,
        statement_date.month,
        month_offset,
    )
    return clamp_day(year, month, due_day)


def _calculate_statement_date_for_due_date(
    due_date: date,
    due_day: int,
    statement_day: int,
) -> date:
    """Recover the anchored statement date associated with a due date."""
    if not isinstance(due_date, date):
        raise ValueError("Due date must be a valid date.")
    _validate_day(due_day, "Due day")
    _validate_day(statement_day, "Statement day")
    month_offset = 0 if due_day > statement_day else -1
    year, month = _shift_year_month(
        due_date.year,
        due_date.month,
        month_offset,
    )
    return clamp_day(year, month, statement_day)


def calculate_pay_by_date(
    due_date: date,
    safety_buffer_days: int,
) -> date:
    """Return the conservative planning date before the official due date."""
    if not isinstance(due_date, date):
        raise ValueError("Due date must be a valid date.")
    _validate_buffer(safety_buffer_days)
    return due_date - timedelta(days=safety_buffer_days)


def days_until(target_date: date, today: date | None = None) -> int:
    """Return signed calendar days from today to a target date."""
    if not isinstance(target_date, date):
        raise ValueError("Target date must be a valid date.")
    return (target_date - (today or date.today())).days


def _validate_day(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 31:
        raise ValueError(f"{label} must be a whole number from 1 to 31.")


def _validate_buffer(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 15:
        raise ValueError("Safety buffer must be a whole number from 0 to 15.")


def _normalize_name(card_name: str) -> str:
    if not isinstance(card_name, str):
        raise ValueError("Card name cannot be empty.")
    cleaned_name = " ".join(card_name.split())
    if not cleaned_name:
        raise ValueError("Card name cannot be empty.")
    return cleaned_name


def _validate_card_input(
    card_name: str,
    statement_day: int,
    due_day: int,
    safety_buffer_days: int,
) -> str:
    cleaned_name = _normalize_name(card_name)
    _validate_day(statement_day, "Statement day")
    _validate_day(due_day, "Due day")
    _validate_buffer(safety_buffer_days)
    return cleaned_name


def _next_id(connection: duckdb.DuckDBPyConnection) -> int:
    return connection.execute(
        f"SELECT COALESCE(MAX(id), 0) + 1 FROM {TABLE_NAME}"
    ).fetchone()[0]


def _ensure_unique_name(
    connection: duckdb.DuckDBPyConnection,
    card_name: str,
    *,
    exclude_card_id: int | None = None,
) -> None:
    query = f"""
        SELECT 1
        FROM {TABLE_NAME}
        WHERE is_active = TRUE
          AND LOWER(TRIM(card_name)) = LOWER(TRIM(?))
    """
    parameters: list[object] = [card_name]
    if exclude_card_id is not None:
        query += " AND id <> ?"
        parameters.append(exclude_card_id)
    query += " LIMIT 1"
    if connection.execute(query, parameters).fetchone():
        raise ValueError("This card already exists. Edit the existing card instead.")


def _row_to_card(row: tuple[object, ...]) -> CreditCard:
    return CreditCard(*row)


def _get_card(
    connection: duckdb.DuckDBPyConnection,
    card_id: int,
    *,
    active_only: bool = True,
) -> CreditCard:
    query = f"SELECT {CARD_COLUMNS} FROM {TABLE_NAME} WHERE id = ?"
    if active_only:
        query += " AND is_active = TRUE"
    row = connection.execute(query, [card_id]).fetchone()
    if row is None:
        raise ValueError("Credit card could not be found.")
    return _row_to_card(row)


def add_card(
    card_name: str,
    statement_day: int,
    due_day: int,
    safety_buffer_days: int = 7,
    *,
    today: date | None = None,
) -> int:
    """Add a card and return its Python-generated ID."""
    cleaned_name = _validate_card_input(
        card_name,
        statement_day,
        due_day,
        safety_buffer_days,
    )
    reference = today or date.today()
    statement_date = clamp_day(
        reference.year,
        reference.month,
        statement_day,
    )
    due_date = calculate_due_date(
        statement_date,
        due_day,
        statement_day,
    )
    status = PAYMENT_DUE if reference >= statement_date else NO_PAYMENT_REQUIRED
    now = datetime.now()

    connection = _connect()
    try:
        connection.execute("BEGIN TRANSACTION")
        try:
            _ensure_unique_name(connection, cleaned_name)
            card_id = _next_id(connection)
            connection.execute(
                f"""
                INSERT INTO {TABLE_NAME} (
                    id,
                    card_name,
                    statement_day,
                    due_day,
                    safety_buffer_days,
                    current_statement_date,
                    current_due_date,
                    status,
                    last_paid_at,
                    last_paid_due_date,
                    created_at,
                    updated_at,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, TRUE)
                """,
                [
                    card_id,
                    cleaned_name,
                    statement_day,
                    due_day,
                    safety_buffer_days,
                    statement_date,
                    due_date,
                    status,
                    now,
                    now,
                ],
            )
            connection.execute("COMMIT")
            return card_id
        except Exception:
            connection.execute("ROLLBACK")
            raise
    except ValueError:
        raise
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def refresh_card_cycles(today: date | None = None) -> None:
    """Normalize cycle dates and activate cards when their statement arrives."""
    reference = today or date.today()
    connection = _connect()
    try:
        rows = connection.execute(
            f"""
            SELECT {CARD_COLUMNS}
            FROM {TABLE_NAME}
            WHERE is_active = TRUE
            """
        ).fetchall()
        updates: list[tuple[date, date, str, datetime, int]] = []
        now = datetime.now()

        for row in rows:
            card = _row_to_card(row)
            statement_date = card.current_statement_date

            if statement_date is None:
                statement_date = calculate_statement_date(
                    card.statement_day,
                    reference,
                    on_or_after=card.status == PAID,
                )

            if card.status == PAYMENT_DUE and statement_date > reference:
                statement_date = calculate_statement_date(
                    card.statement_day,
                    reference,
                    on_or_after=False,
                )
            elif card.status == NO_PAYMENT_REQUIRED:
                current_month_statement = clamp_day(
                    reference.year,
                    reference.month,
                    card.statement_day,
                )
                if current_month_statement <= reference and (
                    statement_date is None or statement_date > reference
                ):
                    statement_date = current_month_statement

            due_date = calculate_due_date(
                statement_date,
                card.due_day,
                card.statement_day,
            )
            status = card.status
            if status in {NO_PAYMENT_REQUIRED, PAID} and reference >= statement_date:
                status = PAYMENT_DUE

            if (
                statement_date != card.current_statement_date
                or due_date != card.current_due_date
                or status != card.status
            ):
                updates.append(
                    (
                        statement_date,
                        due_date,
                        status,
                        now,
                        card.id,
                    )
                )

        if not updates:
            return

        connection.executemany(
            f"""
            UPDATE {TABLE_NAME}
            SET
                current_statement_date = ?,
                current_due_date = ?,
                status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            updates,
        )
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def get_cards(
    include_inactive: bool = False,
    *,
    today: date | None = None,
) -> list[CreditCard]:
    """Return cards after applying automatic lifecycle transitions."""
    refresh_card_cycles(today=today)
    connection = _connect()
    try:
        query = f"SELECT {CARD_COLUMNS} FROM {TABLE_NAME}"
        if not include_inactive:
            query += " WHERE is_active = TRUE"
        query += f"""
            ORDER BY
                CASE WHEN status = '{PAYMENT_DUE}' THEN 0 ELSE 1 END,
                CASE
                    WHEN status = '{PAYMENT_DUE}'
                    THEN current_due_date - safety_buffer_days
                    ELSE current_statement_date
                END ASC,
                LOWER(card_name) ASC
        """
        rows = connection.execute(query).fetchall()
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()
    return [_row_to_card(row) for row in rows]


def update_card(
    card_id: int,
    card_name: str,
    statement_day: int,
    due_day: int,
    safety_buffer_days: int,
    *,
    today: date | None = None,
) -> None:
    """Update card configuration while preserving its lifecycle state."""
    cleaned_name = _validate_card_input(
        card_name,
        statement_day,
        due_day,
        safety_buffer_days,
    )
    reference = today or date.today()
    connection = _connect()
    try:
        card = _get_card(connection, card_id)
        _ensure_unique_name(
            connection,
            cleaned_name,
            exclude_card_id=card_id,
        )

        if card.status == PAYMENT_DUE:
            existing_statement = card.current_statement_date
            if existing_statement is None:
                existing_statement = calculate_statement_date(
                    card.statement_day,
                    reference,
                    on_or_after=False,
                )
            statement_date = clamp_day(
                existing_statement.year,
                existing_statement.month,
                statement_day,
            )
            status = PAYMENT_DUE
        elif card.status == PAID:
            existing_statement = card.current_statement_date
            if existing_statement is None:
                existing_statement = calculate_statement_date(
                    statement_day,
                    reference,
                    on_or_after=True,
                )
            statement_date = clamp_day(
                existing_statement.year,
                existing_statement.month,
                statement_day,
            )
            while statement_date <= reference:
                statement_date = _shift_cycle_statement(
                    statement_date,
                    statement_day,
                    1,
                )
            status = PAID
        else:
            statement_date = clamp_day(
                reference.year,
                reference.month,
                statement_day,
            )
            status = PAYMENT_DUE if reference >= statement_date else NO_PAYMENT_REQUIRED

        due_date = calculate_due_date(
            statement_date,
            due_day,
            statement_day,
        )
        connection.execute(
            f"""
            UPDATE {TABLE_NAME}
            SET
                card_name = ?,
                statement_day = ?,
                due_day = ?,
                safety_buffer_days = ?,
                current_statement_date = ?,
                current_due_date = ?,
                status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            [
                cleaned_name,
                statement_day,
                due_day,
                safety_buffer_days,
                statement_date,
                due_date,
                status,
                datetime.now(),
                card_id,
            ],
        )
    except ValueError:
        raise
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def delete_card(card_id: int) -> None:
    """Soft-delete a card."""
    connection = _connect()
    try:
        _get_card(connection, card_id)
        connection.execute(
            f"""
            UPDATE {TABLE_NAME}
            SET is_active = FALSE, updated_at = ?
            WHERE id = ?
            """,
            [datetime.now(), card_id],
        )
    except ValueError:
        raise
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def reset_all_data() -> None:
    """Remove all current cards while leaving legacy backup tables untouched."""
    connection = _connect()
    try:
        connection.execute(f"DELETE FROM {TABLE_NAME}")
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def mark_card_paid(
    card_id: int,
    *,
    paid_at: datetime | None = None,
) -> None:
    """Mark the active cycle paid and prepare the next statement cycle."""
    connection = _connect()
    try:
        card = _get_card(connection, card_id)
        if card.status != PAYMENT_DUE:
            raise ValueError("This card does not currently require payment.")
        if card.current_due_date is None:
            raise ValueError("This card does not have a current due date.")

        statement_date = card.current_statement_date or calculate_statement_date(
            card.statement_day,
            date.today(),
            on_or_after=False,
        )
        effective_paid_at = paid_at or datetime.now()
        next_statement_date = _shift_cycle_statement(
            statement_date,
            card.statement_day,
            1,
        )
        while next_statement_date <= effective_paid_at.date():
            next_statement_date = _shift_cycle_statement(
                next_statement_date,
                card.statement_day,
                1,
            )
        next_due_date = calculate_due_date(
            next_statement_date,
            card.due_day,
            card.statement_day,
        )
        connection.execute(
            f"""
            UPDATE {TABLE_NAME}
            SET
                current_statement_date = ?,
                current_due_date = ?,
                status = ?,
                last_paid_at = ?,
                last_paid_due_date = ?,
                updated_at = ?
            WHERE id = ?
            """,
            [
                next_statement_date,
                next_due_date,
                PAID,
                effective_paid_at,
                card.current_due_date,
                datetime.now(),
                card_id,
            ],
        )
    except ValueError:
        raise
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def undo_last_paid(card_id: int) -> None:
    """Restore the most recently paid cycle when it is still reversible."""
    connection = _connect()
    try:
        card = _get_card(connection, card_id)
        if card.status != PAID or card.last_paid_due_date is None:
            raise ValueError("There is no recent payment to undo.")
        if card.current_statement_date is None:
            raise ValueError("The previous statement cycle cannot be restored.")

        previous_statement_date = _calculate_statement_date_for_due_date(
            card.last_paid_due_date,
            card.due_day,
            card.statement_day,
        )
        connection.execute(
            f"""
            UPDATE {TABLE_NAME}
            SET
                current_statement_date = ?,
                current_due_date = ?,
                status = ?,
                last_paid_at = NULL,
                last_paid_due_date = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            [
                previous_statement_date,
                card.last_paid_due_date,
                PAYMENT_DUE,
                datetime.now(),
                card_id,
            ],
        )
    except ValueError:
        raise
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def set_card_status(card_id: int, status: str) -> None:
    """Set a lifecycle status explicitly for maintenance or manual overrides."""
    if status not in ALLOWED_STATUSES:
        raise ValueError("Invalid credit card status.")
    connection = _connect()
    try:
        _get_card(connection, card_id)
        connection.execute(
            f"""
            UPDATE {TABLE_NAME}
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            [status, datetime.now(), card_id],
        )
    except ValueError:
        raise
    except duckdb.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        connection.close()


def seed_example_cards() -> None:
    """Add optional sample cards for development."""
    init_db()
    samples = [
        ("Sample Visa", 5, 25, 7),
        ("Sample Mastercard", 15, 5, 7),
        ("Sample Store Card", 28, 20, 5),
    ]
    for card_name, statement_day, due_day, buffer_days in samples:
        try:
            add_card(
                card_name,
                statement_day,
                due_day,
                buffer_days,
            )
        except ValueError as exc:
            if "already exists" not in str(exc):
                raise


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Credit Card Due database tools")
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--seed",
        action="store_true",
        help="add three optional sample credit cards",
    )
    action.add_argument(
        "--reset",
        action="store_true",
        help="remove all cards from the current database",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _parse_args()
    init_db()
    if arguments.seed:
        seed_example_cards()
        print(f"Sample cards added to {get_db_path()}")
    elif arguments.reset:
        reset_all_data()
        print(f"All cards removed from {get_db_path()}")
    else:
        print(f"Database ready at {get_db_path()}")
