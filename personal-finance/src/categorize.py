from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import yaml
from rapidfuzz import fuzz, process

from paths import MERCHANT_RULES_PATH


@dataclass(frozen=True)
class MerchantRule:
    pattern: str
    match_type: str
    merchant_clean: str
    category: str
    subcategory: str


DEFAULT_UNCATEGORIZED = "Uncategorized"


def normalize_merchant_text(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    text = re.sub(r"\s+", " ", text.strip())
    return text


def comparable_text(value: object) -> str:
    text = normalize_merchant_text(value).upper()
    return re.sub(r"[^A-Z0-9 ]+", "", text)


def title_from_raw(value: object) -> str:
    text = normalize_merchant_text(value)
    if not text:
        return ""
    return text.title()


def load_rules(path: Path = MERCHANT_RULES_PATH) -> list[MerchantRule]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        raw_rules = yaml.safe_load(handle) or []

    rules: list[MerchantRule] = []
    for rule in raw_rules:
        rules.append(
            MerchantRule(
                pattern=str(rule["pattern"]),
                match_type=str(rule.get("match_type", "contains")).lower(),
                merchant_clean=str(rule["merchant_clean"]),
                category=str(rule["category"]),
                subcategory=str(rule.get("subcategory", "")),
            )
        )
    return rules


def save_rule(
    pattern: str,
    merchant_clean: str,
    category: str,
    subcategory: str,
    match_type: str = "contains",
    path: Path = MERCHANT_RULES_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rules = []
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            rules = yaml.safe_load(handle) or []

    new_rule = {
        "pattern": comparable_text(pattern),
        "match_type": match_type,
        "merchant_clean": merchant_clean.strip(),
        "category": category.strip(),
        "subcategory": subcategory.strip(),
    }
    if new_rule not in rules:
        rules.append(new_rule)

    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(rules, handle, sort_keys=False, allow_unicode=False)


def match_rule(merchant_raw: object, rules: Iterable[MerchantRule]) -> MerchantRule | None:
    merchant = comparable_text(merchant_raw)
    for rule in rules:
        pattern = comparable_text(rule.pattern)
        if rule.match_type == "exact" and merchant == pattern:
            return rule
        if rule.match_type == "contains" and pattern in merchant:
            return rule
        if rule.match_type == "regex" and re.search(rule.pattern, normalize_merchant_text(merchant_raw), re.I):
            return rule
    return None


def categorize_transactions(df: pd.DataFrame, rules: list[MerchantRule] | None = None) -> pd.DataFrame:
    if df.empty:
        return df

    rules = load_rules() if rules is None else rules
    categorized = df.copy()
    merchant_clean = []
    category = []
    subcategory = []

    for merchant_raw in categorized["merchant_raw"]:
        rule = match_rule(merchant_raw, rules)
        if rule:
            merchant_clean.append(rule.merchant_clean)
            category.append(rule.category)
            subcategory.append(rule.subcategory)
        else:
            merchant_clean.append(title_from_raw(merchant_raw))
            category.append(DEFAULT_UNCATEGORIZED)
            subcategory.append("")

    categorized["merchant_clean"] = merchant_clean
    categorized["category"] = category
    categorized["subcategory"] = subcategory
    return categorized


def suggest_rule(merchant_raw: str, rules: list[MerchantRule] | None = None, score_cutoff: int = 82) -> dict[str, object] | None:
    rules = load_rules() if rules is None else rules
    if not rules:
        return None

    choices = {rule.merchant_clean: comparable_text(rule.pattern) for rule in rules}
    match = process.extractOne(comparable_text(merchant_raw), choices, scorer=fuzz.WRatio, score_cutoff=score_cutoff)
    if not match:
        return None

    merchant_clean, score, _ = match
    rule = next(rule for rule in rules if rule.merchant_clean == merchant_clean)
    return {
        "merchant_clean": rule.merchant_clean,
        "category": rule.category,
        "subcategory": rule.subcategory,
        "score": round(float(score), 1),
    }


def refresh_existing_transactions() -> int:
    from db import connect, load_transactions, update_categorizations

    con = connect()
    try:
        transactions = load_transactions(con)
        refreshed = categorize_transactions(transactions, load_rules())
        return update_categorizations(con, refreshed)
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Merchant categorization utilities.")
    parser.add_argument("--refresh-db", action="store_true", help="Reapply merchant_rules.yml to existing DuckDB transactions.")
    args = parser.parse_args()

    if args.refresh_db:
        updated = refresh_existing_transactions()
        print(f"Refreshed categories for {updated} transactions.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
