from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd
import yaml
from rapidfuzz import fuzz

from paths import MERCHANT_RULES_PATH
from metadata import transaction_type_requires_category, validate_category_pair


@dataclass(frozen=True)
class MerchantRule:
    rule_id: int | None
    owner_type: str
    pattern: str
    match_type: str
    merchant_clean: str
    transaction_type: str
    scope: str
    category: str
    subcategory: str
    priority: int
    enabled: bool = True
    notes: str = ""


DEFAULT_UNCATEGORIZED_CATEGORY = "Other"
DEFAULT_UNCATEGORIZED_SUBCATEGORY = "Uncategorized"
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
                rule_id=None,
                owner_type="user",
                pattern=str(rule["pattern"]),
                match_type=str(rule.get("match_type", "contains")).lower(),
                merchant_clean=str(rule["merchant_clean"]),
                transaction_type=str(rule.get("transaction_type", "")),
                scope=str(rule.get("scope", "")),
                category=str(rule["category"]),
                subcategory=str(rule.get("subcategory", "")),
                priority=int(rule.get("priority", 100)),
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


def import_yaml_rules_to_db(
    con: duckdb.DuckDBPyConnection,
    path: Path = MERCHANT_RULES_PATH,
    owner_type: str = "user",
) -> int:
    imported = 0
    for rule in load_rules(path):
        if rule.category or rule.subcategory:
            validate_rule_fields(con, rule.transaction_type, rule.category, rule.subcategory)
        exists = con.execute(
            """
            SELECT count(*)
            FROM merchant_rule
            WHERE owner_type = ?
              AND pattern = ?
              AND match_type = ?
            """,
            [owner_type, comparable_text(rule.pattern), rule.match_type],
        ).fetchone()[0]
        if exists:
            continue
        con.execute(
            """
            INSERT INTO merchant_rule (
                rule_id,
                owner_type,
                pattern,
                match_type,
                merchant_clean,
                transaction_type,
                scope,
                category,
                subcategory,
                priority,
                enabled,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE, ?)
            """,
            [
                next_rule_id(con),
                owner_type,
                prepare_rule_pattern(rule.pattern, rule.match_type),
                rule.match_type,
                rule.merchant_clean,
                rule.transaction_type,
                rule.scope,
                rule.category,
                rule.subcategory,
                rule.priority,
                f"Imported from {path.name}",
            ],
        )
        imported += 1
    return imported


def load_merchant_rules_from_db(con: duckdb.DuckDBPyConnection, include_disabled: bool = False) -> list[MerchantRule]:
    enabled_clause = "" if include_disabled else "WHERE enabled"
    rows = con.execute(
        f"""
        SELECT
            rule_id,
            owner_type,
            pattern,
            match_type,
            COALESCE(merchant_clean, '') AS merchant_clean,
            COALESCE(transaction_type, '') AS transaction_type,
            COALESCE(scope, '') AS scope,
            COALESCE(category, '') AS category,
            COALESCE(subcategory, '') AS subcategory,
            COALESCE(priority, 100) AS priority,
            COALESCE(enabled, TRUE) AS enabled,
            COALESCE(notes, '') AS notes
        FROM merchant_rule
        {enabled_clause}
        ORDER BY
            CASE owner_type WHEN 'user' THEN 0 ELSE 1 END,
            priority,
            CASE match_type WHEN 'exact' THEN 0 WHEN 'regex' THEN 1 ELSE 2 END,
            length(pattern) DESC,
            rule_id
        """
    ).fetchall()
    return [
        MerchantRule(
            rule_id=int(row[0]),
            owner_type=str(row[1]),
            pattern=str(row[2]),
            match_type=str(row[3]).lower(),
            merchant_clean=str(row[4]),
            transaction_type=str(row[5]),
            scope=str(row[6]),
            category=str(row[7]),
            subcategory=str(row[8]),
            priority=int(row[9]),
            enabled=bool(row[10]),
            notes=str(row[11]),
        )
        for row in rows
    ]


def match_merchant_rule(
    con: duckdb.DuckDBPyConnection,
    merchant_raw: object,
    account_context: dict[str, object] | None = None,
) -> MerchantRule | None:
    return match_rule(merchant_raw, load_merchant_rules_from_db(con), account_context=account_context)


def save_user_merchant_rule(
    con: duckdb.DuckDBPyConnection,
    pattern: str,
    match_type: str,
    merchant_clean: str,
    transaction_type: str = "",
    scope: str = "",
    category: str = "",
    subcategory: str = "",
    priority: int = 50,
    notes: str = "",
) -> int:
    match_type = match_type.lower().strip()
    if match_type not in {"contains", "exact", "regex"}:
        raise ValueError("Match type must be contains, exact, or regex.")
    validate_rule_fields(con, transaction_type, category, subcategory)
    rule_id = next_rule_id(con)
    con.execute(
        """
        INSERT INTO merchant_rule (
            rule_id,
            owner_type,
            pattern,
            match_type,
            merchant_clean,
            transaction_type,
            scope,
            category,
            subcategory,
            priority,
            enabled,
            notes
        )
        VALUES (?, 'user', ?, ?, ?, ?, ?, ?, ?, ?, TRUE, ?)
        """,
        [
            rule_id,
            prepare_rule_pattern(pattern, match_type),
            match_type,
            merchant_clean.strip(),
            transaction_type.strip(),
            scope.strip(),
            category.strip(),
            subcategory.strip(),
            int(priority),
            notes.strip(),
        ],
    )
    return rule_id


def disable_rule(con: duckdb.DuckDBPyConnection, rule_id: int) -> None:
    con.execute(
        """
        UPDATE merchant_rule
        SET enabled = FALSE,
            updated_at = now()
        WHERE rule_id = ?
          AND owner_type = 'user'
        """,
        [int(rule_id)],
    )


def update_rule(con: duckdb.DuckDBPyConnection, rule_id: int, fields: dict[str, object]) -> None:
    allowed_fields = {
        "pattern",
        "match_type",
        "merchant_clean",
        "transaction_type",
        "scope",
        "category",
        "subcategory",
        "priority",
        "enabled",
        "notes",
    }
    updates = {key: value for key, value in fields.items() if key in allowed_fields}
    if not updates:
        return
    if "match_type" in updates:
        updates["match_type"] = str(updates["match_type"]).lower().strip()
        if updates["match_type"] not in {"contains", "exact", "regex"}:
            raise ValueError("Match type must be contains, exact, or regex.")

    existing = con.execute(
        """
        SELECT owner_type, match_type, transaction_type, category, subcategory
        FROM merchant_rule
        WHERE rule_id = ?
        """,
        [int(rule_id)],
    ).fetchone()
    if not existing:
        raise ValueError(f"Rule {rule_id} does not exist.")
    if existing[0] != "user":
        raise ValueError("System rules are read-only. Create a user rule override instead.")

    current_match_type = str(updates.get("match_type", existing[1] or "contains"))
    transaction_type = str(updates.get("transaction_type", existing[2] or ""))
    category = str(updates.get("category", existing[3] or ""))
    subcategory = str(updates.get("subcategory", existing[4] or ""))
    validate_rule_fields(con, transaction_type, category, subcategory)

    assignments = []
    values = []
    for field, value in updates.items():
        assignments.append(f"{field} = ?")
        if field == "pattern":
            values.append(prepare_rule_pattern(value, current_match_type))
        else:
            values.append(value)
    assignments.append("updated_at = now()")
    values.append(int(rule_id))
    con.execute(
        f"""
        UPDATE merchant_rule
        SET {", ".join(assignments)}
        WHERE rule_id = ?
          AND owner_type = 'user'
        """,
        values,
    )


def validate_rule_fields(
    con: duckdb.DuckDBPyConnection,
    transaction_type: str,
    category: str,
    subcategory: str,
) -> None:
    transaction_type = transaction_type.strip()
    category = category.strip()
    subcategory = subcategory.strip()
    if category == "Custom":
        raise ValueError("Choose a real category name, not Custom.")
    if transaction_type:
        exists = con.execute(
            """
            SELECT count(*)
            FROM transaction_type_master
            WHERE transaction_type = ?
              AND enabled
            """,
            [transaction_type],
        ).fetchone()[0]
        if not exists:
            raise ValueError(f"Invalid transaction type: {transaction_type}")

    if transaction_type and transaction_type_requires_category(con, transaction_type) and not category:
        raise ValueError(f"{transaction_type} rules require a category.")
    if category or subcategory:
        if not validate_category_pair(con, category, subcategory):
            raise ValueError(f"Invalid category/subcategory: {category} / {subcategory or '(None)'}")


def prepare_rule_pattern(pattern: object, match_type: str) -> str:
    text = normalize_merchant_text(pattern)
    if match_type == "regex":
        return text
    return comparable_text(text)


def next_rule_id(con: duckdb.DuckDBPyConnection) -> int:
    return int(con.execute("SELECT COALESCE(max(rule_id), 0) + 1 FROM merchant_rule").fetchone()[0])


def match_rule(
    merchant_raw: object,
    rules: Iterable[MerchantRule],
    account_context: dict[str, object] | None = None,
) -> MerchantRule | None:
    _ = account_context
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
        if rule.match_type == "regex":
            try:
                if re.search(rule.pattern, normalize_merchant_text(merchant_raw), re.I):
                    return rule
            except re.error:
                continue
    return None


def categorize_transactions(
    df: pd.DataFrame,
    rules: list[MerchantRule] | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df

    if rules is None:
        rules = load_merchant_rules_from_db(con) if con is not None else load_rules()
    categorized = df.copy()
    merchant_clean = []
    transaction_type = []
    scope = []
    category = []
    subcategory = []
    matched_rule_id = []
    matched_rule_owner_type = []
    matched_pattern = []
    classification_reason = []

    for row in categorized.itertuples():
        merchant_raw = getattr(row, "merchant_raw")
        rule = match_rule(merchant_raw, rules)
        if rule:
            merchant_clean.append(rule.merchant_clean)
            transaction_type.append(rule.transaction_type or getattr(row, "transaction_type", ""))
            scope.append(rule.scope or getattr(row, "scope", ""))
            category.append(rule.category or getattr(row, "category", ""))
            subcategory.append(rule.subcategory or getattr(row, "subcategory", ""))
            matched_rule_id.append(rule.rule_id)
            matched_rule_owner_type.append(rule.owner_type)
            matched_pattern.append(rule.pattern)
            classification_reason.append(
                f"Matched {rule.owner_type} rule {rule.rule_id}: pattern='{rule.pattern}', match_type='{rule.match_type}'"
            )
        else:
            merchant_clean.append(title_from_raw(merchant_raw))
            transaction_type.append(getattr(row, "transaction_type", ""))
            scope.append(getattr(row, "scope", ""))
            category.append(DEFAULT_UNCATEGORIZED_CATEGORY)
            subcategory.append(DEFAULT_UNCATEGORIZED_SUBCATEGORY)
            matched_rule_id.append(None)
            matched_rule_owner_type.append("")
            matched_pattern.append("")
            classification_reason.append("")

    categorized["merchant_clean"] = merchant_clean
    categorized["transaction_type"] = transaction_type
    categorized["scope"] = scope
    categorized["category"] = category
    categorized["subcategory"] = subcategory
    categorized["matched_rule_id"] = matched_rule_id
    categorized["matched_rule_owner_type"] = matched_rule_owner_type
    categorized["matched_pattern"] = matched_pattern
    categorized["classification_reason"] = classification_reason
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
        "transaction_type": best_rule.transaction_type,
        "scope": best_rule.scope,
        "category": best_rule.category,
        "subcategory": best_rule.subcategory,
        "score": round(best_score, 1),
    }


def refresh_existing_transactions() -> int:
    from db import connect, load_transactions, update_categorizations

    con = connect()
    try:
        transactions = load_transactions(con)
        refreshed = categorize_transactions(transactions, con=con)
        return update_categorizations(con, refreshed)
    finally:
        con.close()
