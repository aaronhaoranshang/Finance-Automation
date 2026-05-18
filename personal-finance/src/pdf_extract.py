from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd
import pdfplumber


MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

PERIOD_RE = re.compile(
    r"For the period:\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})\s+to\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})"
)
TRANSACTION_RE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{2})\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{2})\s+"
    r"(.+?)\s+(-?\$?[\d,]+\.\d{2})(?:\s+.*)?$"
)


def read_pdf_statement(path: Path) -> pd.DataFrame:
    if "triangle" in path.name.lower():
        return read_triangle_pdf(path)
    raise ValueError(f"No PDF parser configured for {path.name}")


def read_triangle_pdf(path: Path) -> pd.DataFrame:
    text = extract_text(path)
    period_start, period_end = parse_statement_period(text)
    rows = []

    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line.strip())
        match = TRANSACTION_RE.match(line)
        if not match:
            continue

        transaction_month, transaction_day, posting_month, posting_day, description, amount = match.groups()
        rows.append(
            {
                "Transaction Date": resolve_statement_date(transaction_month, int(transaction_day), period_start, period_end),
                "Posting Date": resolve_statement_date(posting_month, int(posting_day), period_start, period_end),
                "Transaction Description": description.strip(),
                "Amount": parse_pdf_amount(amount),
            }
        )

    if not rows:
        raise ValueError(f"No Triangle transactions found in {path.name}")

    return pd.DataFrame(rows)


def extract_text(path: Path) -> str:
    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def parse_statement_period(text: str) -> tuple[date, date]:
    match = PERIOD_RE.search(text)
    if not match:
        raise ValueError("Could not find statement period in PDF")

    start_month, start_day, start_year, end_month, end_day, end_year = match.groups()
    return (
        date(int(start_year), month_number(start_month), int(start_day)),
        date(int(end_year), month_number(end_month), int(end_day)),
    )


def resolve_statement_date(month: str, day: int, period_start: date, period_end: date) -> date:
    month_no = month_number(month)
    candidates = [
        date(period_start.year, month_no, day),
        date(period_end.year, month_no, day),
    ]
    for candidate in candidates:
        if period_start <= candidate <= period_end:
            return candidate
    return min(candidates, key=lambda candidate: min(abs((candidate - period_start).days), abs((candidate - period_end).days)))


def month_number(month: str) -> int:
    return MONTHS[month[:3]]


def parse_pdf_amount(value: str) -> float:
    cleaned = value.replace("$", "").replace(",", "").strip()
    return float(cleaned)
