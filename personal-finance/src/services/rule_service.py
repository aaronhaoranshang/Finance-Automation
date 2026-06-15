from __future__ import annotations

import pandas as pd

from categorize import (
    categorize_transactions,
    disable_rule,
    load_merchant_rules_from_db,
    save_user_merchant_rule,
    suggest_pattern_from_raw,
    suggest_rule,
    update_rule,
)
from db import connect, load_transactions, update_categorizations
from normalize import apply_transaction_type_defaults


def refresh_categories() -> None:
    con = connect()
    try:
        transactions = load_transactions(con)
        refreshed = categorize_transactions(transactions, con=con)
        refreshed = apply_transaction_type_defaults(refreshed)
        update_categorizations(con, refreshed)
    finally:
        con.close()


def load_sql_merchant_rules(include_disabled: bool = False) -> pd.DataFrame:
    con = connect()
    try:
        rules = load_merchant_rules_from_db(con, include_disabled=include_disabled)
    finally:
        con.close()
    return pd.DataFrame([rule.__dict__ for rule in rules])


def suggest_sql_rule(merchant_raw: str, score_cutoff: int = 82) -> dict[str, object] | None:
    con = connect()
    try:
        rules = load_merchant_rules_from_db(con)
    finally:
        con.close()
    return suggest_rule(merchant_raw, rules=rules, score_cutoff=score_cutoff)


def save_sql_user_rule(
    pattern: str,
    merchant_clean: str,
    transaction_type: str,
    scope: str,
    category: str,
    subcategory: str,
    match_type: str = "contains",
    priority: int = 50,
    notes: str = "",
) -> int:
    con = connect()
    try:
        return save_user_merchant_rule(
            con,
            pattern=pattern,
            match_type=match_type,
            merchant_clean=merchant_clean,
            transaction_type=transaction_type,
            scope=scope,
            category=category,
            subcategory=subcategory,
            priority=priority,
            notes=notes,
        )
    finally:
        con.close()


def update_user_rule(rule_id: int, fields: dict[str, object]) -> None:
    con = connect()
    try:
        update_rule(con, rule_id, fields)
    finally:
        con.close()


def disable_user_rule(rule_id: int) -> None:
    con = connect()
    try:
        disable_rule(con, rule_id)
    finally:
        con.close()


def suggest_rule_pattern(merchant_raw: object) -> str:
    return suggest_pattern_from_raw(merchant_raw)

