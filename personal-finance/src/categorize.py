from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import yaml
from rapidfuzz import fuzz

from paths import MERCHANT_RULES_PATH


@dataclass(frozen=True)
class MerchantRule:
    pattern: str
    match_type: str
    merchant_clean: str
    category: str
    subcategory: str


DEFAULT_UNCATEGORIZED = "Uncategorized"
MIN_CONTAINS_KEY_LENGTH = 3


def normalize_merchant_text(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    text = re.sub(r"\s+", " ", text.strip())
    return text


def comparable_text(value: object) -> str:
    text = normalize_merchant_text(value).upper()
    return re.sub(r"[^A-Z0-9 ]+", "", text)


def compact_text(value: object) -> str:
    text = normalize_merchant_text(value).upper()
    return re.sub(r"[^A-Z0-9]+", "", text)


def compact_without_long_numbers(value: object) -> str:
    return re.sub(r"\d{4,}", "", compact_text(value))


def strip_statement_noise(value: object) -> str:
    text = normalize_merchant_text(value)
    text = re.sub(r"\s*\([^)]*$", "", text).strip()
    statement_prefixes = [
        r"CONTACTLESS\s+INTERAC\s+PURCHASE",
        r"INTERAC\s+PURCHASE",
        r"POINT\s+OF\s+SALE",
        r"POS\s+PURCHASE",
        r"DEBIT\s+PURCHASE",
        r"PURCHASE",
    ]
    for prefix in statement_prefixes:
        text = re.sub(rf"(?i)^{prefix}\s*[-:]*\s*\d*\s*", "", text).strip()
    return text or normalize_merchant_text(value)


def remove_numeric_noise(value: object) -> str:
    tokens = comparable_text(value).split()
    return " ".join(token for token in tokens if not (token.isdigit() and len(token) >= 4))


def merchant_match_keys(value: object) -> list[str]:
    stripped = strip_statement_noise(value)
    candidates = [
        comparable_text(value),
        comparable_text(stripped),
        remove_numeric_noise(stripped),
        compact_text(value),
        compact_text(stripped),
        compact_without_long_numbers(value),
        compact_without_long_numbers(stripped),
    ]
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def suggest_pattern_from_raw(value: object) -> str:
    text = strip_statement_noise(value)
    text = remove_numeric_noise(text)
    return text or normalize_merchant_text(value)


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
    merchant_keys = merchant_match_keys(merchant_raw)
    for rule in rules:
        pattern_keys = merchant_match_keys(rule.pattern)
        if rule.match_type == "exact" and any(merchant_key == pattern_key for merchant_key in merchant_keys for pattern_key in pattern_keys):
            return rule
        if rule.match_type == "contains" and any(
            len(pattern_key) >= MIN_CONTAINS_KEY_LENGTH and pattern_key in merchant_key
            for merchant_key in merchant_keys
            for pattern_key in pattern_keys
        ):
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

    query_keys = merchant_match_keys(merchant_raw)
    best_rule = None
    best_score = 0.0

    for rule in rules:
        rule_keys = merchant_match_keys(rule.pattern) + merchant_match_keys(rule.merchant_clean)
        scores = [fuzz.WRatio(query_key, rule_key) for query_key in query_keys for rule_key in rule_keys]
        score = max(scores)
        if score > best_score:
            best_rule = rule
            best_score = float(score)

    if best_rule is None or best_score < score_cutoff:
        return None

    return {
        "merchant_clean": best_rule.merchant_clean,
        "category": best_rule.category,
        "subcategory": best_rule.subcategory,
        "score": round(best_score, 1),
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
