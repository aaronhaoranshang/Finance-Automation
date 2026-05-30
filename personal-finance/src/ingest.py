from __future__ import annotations

import calendar
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

import duckdb

from db import connect, insert_transactions, log_import
from normalize import detect_source, load_classification_rules, load_source_rules, normalize_transactions, read_csv_flex
from pdf_extract import read_pdf_statement
from paths import DB_PATH, FAILED_DIR, PROCESSED_DIR, TO_IMPORT_DIR, ensure_project_dirs


@dataclass(frozen=True)
class ImportPreview:
    file: str
    source: str
    account_name: str
    rows_seen: int
    rows_in_file: int
    existing_duplicates: int | None
    new_rows: int | None
    statement_month: str
    processed_name: str
    gross_expenses: float
    refunds_and_credits: float
    payments: float
    debt_payments: float
    income: float
    transfers: float
    reimbursements: float
    stored_value_reloads: float
    manual_review: float
    net_spend: float
    file_net_total: float


def unique_destination(directory: Path, filename: str) -> Path:
    destination = directory / filename
    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    counter = 1
    while True:
        candidate = directory / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def move_file(path: Path, directory: Path, filename: str | None = None) -> Path:
    destination = unique_destination(directory, filename or path.name)
    shutil.move(str(path), str(destination))
    return destination


def processed_filename(original_path: Path, normalized: pd.DataFrame, rule: dict[str, object]) -> str:
    label = processed_file_label(normalized, rule)
    month = statement_month_label(normalized)
    suffix = original_path.suffix or ".csv"
    return safe_filename(f"{label} {month}{suffix}")


def processed_file_label(normalized: pd.DataFrame, rule: dict[str, object]) -> str:
    if rule.get("processed_file_label"):
        return str(rule["processed_file_label"])

    template = rule.get("processed_file_label_template")
    if template:
        account_name = first_value(normalized, "account_name", "Unknown Account")
        return str(template).format(account_alias=account_name, account_name=account_name)

    return first_value(normalized, "account_name", "Unknown Account")


def statement_month_label(normalized: pd.DataFrame) -> str:
    dates = pd.to_datetime(normalized["transaction_date"], errors="coerce").dropna()
    if dates.empty:
        return "Unknown Month"

    month_counts = dates.dt.to_period("M").value_counts()
    max_count = month_counts.max()
    tied_months = set(month_counts[month_counts == max_count].index.astype(str))
    candidates = normalized.copy()
    candidates["_month"] = pd.to_datetime(candidates["transaction_date"], errors="coerce").dt.to_period("M").astype(str)
    candidates = candidates[candidates["_month"].isin(tied_months)]
    totals = candidates.groupby("_month")["amount"].apply(lambda values: values.abs().sum())
    statement_period = totals.sort_values(ascending=False).index[0]
    statement_date = pd.Period(statement_period, freq="M").to_timestamp()
    month = calendar.month_abbr[int(statement_date.month)]
    return f"{month} {int(statement_date.year)}"


def first_value(df: pd.DataFrame, column: str, default: str) -> str:
    if column not in df.columns or df.empty:
        return default
    values = df[column].dropna().astype(str)
    if values.empty:
        return default
    return values.iloc[0]


def safe_filename(filename: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', " ", filename)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def preview_file(file_path: Path, admin: bool = False) -> ImportPreview:
    raw = read_source_file(file_path)
    source_rules = load_source_rules(admin=admin)
    source_name, rule = detect_source(raw, file_path, source_rules)
    classification_rules = load_classification_rules(admin=admin)
    normalized = normalize_transactions(raw, source_name, rule, file_path.name, classification_rules)
    existing_duplicates = count_existing_duplicates(normalized)
    return build_preview(file_path, source_name, rule, raw, normalized, existing_duplicates)


def build_preview(
    file_path: Path,
    source_name: str,
    rule: dict[str, object],
    raw: pd.DataFrame,
    normalized: pd.DataFrame,
    existing_duplicates: int | None,
) -> ImportPreview:
    payments = abs(float(normalized.loc[normalized["transaction_type"] == "payment", "amount"].sum()))
    debt_payments = abs(float(normalized.loc[normalized["transaction_type"] == "debt_payment", "amount"].sum()))
    income = abs(float(normalized.loc[normalized["transaction_type"] == "income", "amount"].sum()))
    transfers = abs(float(normalized.loc[normalized["transaction_type"] == "transfer", "amount"].sum()))
    reimbursements = abs(float(normalized.loc[normalized["transaction_type"] == "reimbursement", "amount"].sum()))
    stored_value_reloads = abs(float(normalized.loc[normalized["transaction_type"] == "stored_value_reload", "amount"].sum()))
    manual_review = abs(float(normalized.loc[normalized["transaction_type"] == "manual_review", "amount"].sum()))
    refunds_and_credits = abs(float(normalized.loc[normalized["transaction_type"].isin(["refund", "credit"]), "amount"].sum()))
    gross_expenses = float(normalized.loc[normalized["transaction_type"] == "expense", "amount"].sum())
    net_spend = gross_expenses - refunds_and_credits
    file_net_total = float(normalized["amount"].sum())

    return ImportPreview(
        file=file_path.name,
        source=source_name,
        account_name=first_value(normalized, "account_name", "Unknown Account"),
        rows_seen=len(raw),
        rows_in_file=len(normalized),
        existing_duplicates=existing_duplicates,
        new_rows=max(len(normalized) - existing_duplicates, 0) if existing_duplicates is not None else None,
        statement_month=statement_month_label(normalized),
        processed_name=processed_filename(file_path, normalized, rule),
        gross_expenses=gross_expenses,
        refunds_and_credits=refunds_and_credits,
        payments=payments,
        debt_payments=debt_payments,
        income=income,
        transfers=transfers,
        reimbursements=reimbursements,
        stored_value_reloads=stored_value_reloads,
        manual_review=manual_review,
        net_spend=net_spend,
        file_net_total=file_net_total,
    )


def count_existing_duplicates(normalized: pd.DataFrame) -> int | None:
    if normalized.empty or not DB_PATH.exists():
        return 0

    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        payload = normalized[["transaction_id"]].copy()
        con.register("incoming_ids", payload)
        count = con.execute(
            """
            SELECT count(*)
            FROM incoming_ids
            INNER JOIN transactions USING (transaction_id)
            """
        ).fetchone()[0]
        con.unregister("incoming_ids")
        return int(count)
    except Exception:
        return None
    finally:
        if "con" in locals():
            con.close()


def print_preview(preview: ImportPreview) -> None:
    if preview.existing_duplicates is None:
        row_summary = f"{preview.rows_in_file} (duplicate check unavailable; close DBeaver/Streamlit if DuckDB is locked)"
    else:
        row_summary = f"{preview.rows_in_file} ({preview.new_rows} new, {preview.existing_duplicates} duplicates)"

    print(f"Preview {preview.file}")
    print(f"  Source: {preview.source}")
    print(f"  Account: {preview.account_name}")
    print(f"  Statement month: {preview.statement_month}")
    print(f"  Processed name: {preview.processed_name}")
    print(f"  Rows: {row_summary}")
    print(f"  Gross expenses: ${preview.gross_expenses:,.2f}")
    print(f"  Refunds/credits: ${preview.refunds_and_credits:,.2f}")
    print(f"  Payments ignored for spend: ${preview.payments:,.2f}")
    print(f"  Debt payments excluded from spend: ${preview.debt_payments:,.2f}")
    print(f"  Income: ${preview.income:,.2f}")
    print(f"  Internal transfers excluded from spend: ${preview.transfers:,.2f}")
    print(f"  Reimbursements excluded from spend: ${preview.reimbursements:,.2f}")
    print(f"  Prepaid card reloads excluded from spend: ${preview.stored_value_reloads:,.2f}")
    print(f"  Needs manual review: ${preview.manual_review:,.2f}")
    print(f"  Net spend: ${preview.net_spend:,.2f}")
    print(f"  File net total: ${preview.file_net_total:,.2f}")


def ingest_file(file_path: Path, admin: bool = False) -> dict[str, object]:
    ensure_project_dirs()
    con = connect()
    rows_seen = 0
    try:
        classification_rules = load_classification_rules(admin=admin)
        source_rules = load_source_rules(admin=admin)
        raw = read_source_file(file_path)
        rows_seen = len(raw)
        source_name, rule = detect_source(raw, file_path, source_rules)
        normalized = normalize_transactions(raw, source_name, rule, file_path.name, classification_rules)
        rows_inserted = insert_transactions(con, normalized)
        destination_name = processed_filename(file_path, normalized, rule)
        destination = move_file(file_path, PROCESSED_DIR, destination_name)
        duplicates = len(normalized) - rows_inserted
        summary = build_preview(file_path, source_name, rule, raw, normalized, duplicates)
        log_import(con, file_path.name, "processed", rows_seen, rows_inserted, import_message(summary, destination.name))
        return {
            "file": file_path.name,
            "status": "processed",
            "rows_seen": rows_seen,
            "rows_inserted": rows_inserted,
            "duplicates": duplicates,
            "destination": str(destination),
        }
    except Exception as exc:
        log_import(con, file_path.name, "failed", rows_seen, 0, str(exc))
        destination = move_file(file_path, FAILED_DIR)
        return {
            "file": file_path.name,
            "status": "failed",
            "rows_seen": rows_seen,
            "rows_inserted": 0,
            "destination": str(destination),
            "error": str(exc),
        }
    finally:
        con.close()


def ingest_directory(directory: Path = TO_IMPORT_DIR, admin: bool = False) -> list[dict[str, object]]:
    ensure_project_dirs()
    results = []
    for file_path in supported_import_files(directory):
        if file_path.is_file():
            results.append(ingest_file(file_path, admin=admin))
    return results


def supported_import_files(directory: Path) -> list[Path]:
    files = [*directory.glob("*.csv"), *directory.glob("*.pdf")]
    return sorted(files)


def read_source_file(file_path: Path) -> pd.DataFrame:
    if file_path.suffix.lower() == ".pdf":
        return read_pdf_statement(file_path)
    return read_csv_flex(file_path)


def import_message(preview: ImportPreview, destination_name: str) -> str:
    return (
        f"Moved to {destination_name}; "
        f"gross_expenses={preview.gross_expenses:.2f}; "
        f"refunds_credits={preview.refunds_and_credits:.2f}; "
        f"payments={preview.payments:.2f}; "
        f"debt_payments={preview.debt_payments:.2f}; "
        f"income={preview.income:.2f}; "
        f"transfers={preview.transfers:.2f}; "
        f"reimbursements={preview.reimbursements:.2f}; "
        f"stored_value_reloads={preview.stored_value_reloads:.2f}; "
        f"manual_review={preview.manual_review:.2f}; "
        f"net_spend={preview.net_spend:.2f}; "
        f"file_net_total={preview.file_net_total:.2f}"
    )


def preview_paths(paths: list[Path], admin: bool = False) -> None:
    targets = paths or supported_import_files(TO_IMPORT_DIR)
    if not targets:
        print("No CSV files found to preview.")
        return
    for path in targets:
        try:
            print_preview(preview_file(path, admin=admin))
        except Exception as exc:
            print(f"Failed preview {path.name}: {exc}")
