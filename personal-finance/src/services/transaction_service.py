from __future__ import annotations

import pandas as pd

from db import connect, update_transaction_fields
from metadata import get_transaction_types, transaction_type_requires_category
from ui.constants import FALLBACK_TRANSACTION_TYPE_LABELS, FALLBACK_TRANSACTION_TYPES


def load_transaction_type_metadata() -> pd.DataFrame:
    con = connect()
    try:
        return get_transaction_types(con)
    finally:
        con.close()


def transaction_type_metadata() -> pd.DataFrame:
    try:
        metadata = load_transaction_type_metadata()
    except Exception:
        metadata = pd.DataFrame()
    return metadata


def transaction_type_labels() -> dict[str, str]:
    metadata = transaction_type_metadata()
    if metadata.empty:
        return FALLBACK_TRANSACTION_TYPE_LABELS
    labels = dict(zip(metadata["transaction_type"], metadata["display_name"], strict=True))
    return {**FALLBACK_TRANSACTION_TYPE_LABELS, **labels}


def display_transaction_type_label(value: object) -> str:
    value = "" if pd.isna(value) else str(value)
    return transaction_type_labels().get(value, value.replace("_", " ").title())


def transaction_type_options(existing_types: pd.Series | None = None) -> list[str]:
    metadata = transaction_type_metadata()
    metadata_types = metadata["transaction_type"].dropna().astype(str).tolist() if not metadata.empty else []
    existing = existing_types.dropna().astype(str).tolist() if existing_types is not None else []
    return sorted({*FALLBACK_TRANSACTION_TYPES, *metadata_types, *existing}, key=display_transaction_type_label)


def transaction_types_with_flag(flag: str, fallback: list[str]) -> list[str]:
    metadata = transaction_type_metadata()
    if metadata.empty or flag not in metadata.columns:
        return fallback
    values = metadata.loc[metadata[flag].astype(bool), "transaction_type"].dropna().astype(str).tolist()
    return values or fallback


def category_required_for_type(transaction_type: str) -> bool:
    con = connect()
    try:
        return transaction_type_requires_category(con, transaction_type)
    finally:
        con.close()


def update_transaction_classification(
    transaction_id: str,
    merchant_clean: str,
    transaction_type: str,
    scope: str,
    category: str,
    subcategory: str,
    **override_flags: object,
) -> None:
    con = connect()
    try:
        update_transaction_fields(
            con,
            transaction_id,
            merchant_clean,
            transaction_type,
            scope,
            category,
            subcategory,
            **override_flags,
        )
    finally:
        con.close()

