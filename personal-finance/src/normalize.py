from __future__ import annotations

import hashlib
from copy import deepcopy
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from categorize import categorize_transactions, normalize_merchant_text
from paths import ADMIN_CLASSIFICATION_RULES_PATH, ADMIN_SOURCE_RULES_PATH, SOURCE_RULES_PATH


def load_source_rules(path: Path = SOURCE_RULES_PATH, admin: bool = False, admin_path: Path = ADMIN_SOURCE_RULES_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        rules = yaml.safe_load(handle) or {"sources": {}}
    if admin:
        if not admin_path.exists():
            raise FileNotFoundError(
                f"Admin source rules not found at {admin_path}. "
                "Create the file or run without --admin for generic source labels."
            )
        with admin_path.open("r", encoding="utf-8") as handle:
            rules = merge_nested_dict(rules, yaml.safe_load(handle) or {})
    return rules


def merge_nested_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_nested_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


BASE_CLASSIFICATION_RULES: dict[str, Any] = {
    "payment_patterns": [
        "PAYMENT",
        "PAYMENTS",
        "PMT",
        "PAIEMENT",
        "BANQUE",
        "THANK YOU",
        "TELEPAYMENTS",
        "AUTOPAY",
        "AUTO PAY",
        "ONLINE PAYMENT",
        "MOBILE PAYMENT",
        "PAYMENT FROM",
    ],
    "debt_payment_patterns": [
        "ONLINE BANKING TRANSFER",
        "BILL PAYMENT",
        "CREDIT CARD/LOC PAY",
        "CREDIT CARD",
        "MASTERCARD",
        "VISA",
        "AMEX",
        "AMERICAN EXPRESS",
    ],
    "payment_source_patterns": [
        "RBC",
        "ROYAL BANK",
        "SCOTIABANK",
        "BMO",
        "CIBC",
        "TD",
        "TANGERINE",
        "PC FINANCIAL",
    ],
    "refund_patterns": [
        "REFUND",
        "RETURN",
        "RETURNED",
        "REBATE",
        "REVERSAL",
        "CREDIT VOUCHER",
        "CREDIT ADJUSTMENT",
        "ADJUSTMENT",
    ],
    "income_patterns": [
        "PAYROLL",
        "SALARY",
        "DIRECT DEPOSIT",
        "EI CANADA",
        "GST",
        "HST",
        "CRA",
        "CANADA",
        "CHEXY",
        "RENT",
    ],
    "self_transfer_patterns": [
        "CUSTOMER TRANSFER",
        "INTERNAL TRANSFER",
        "ACCOUNT TRANSFER",
        "INVESTMENT",
        "INTER-FI FUND",
    ],
    "reimbursement_patterns": [],
    "refund_reimbursement_patterns": [],
    "stored_value_reload": {
        "minimum_amount": None,
        "merchants": [],
    },
    "manual_review_patterns": [
        "MISCELLANEOUS PAYMENT",
        "ABM DEPOSIT",
        "ROYAL FOREIGN EXCHANGE DEPOSIT",
    ],
}


def load_classification_rules(admin: bool = False, path: Path | None = None) -> dict[str, Any]:
    rules = deepcopy(BASE_CLASSIFICATION_RULES)
    overlay_path = path or ADMIN_CLASSIFICATION_RULES_PATH
    if admin:
        if not overlay_path.exists():
            raise FileNotFoundError(
                f"Admin classification rules not found at {overlay_path}. "
                "Create the file or run without --admin for generic rules."
            )
        with overlay_path.open("r", encoding="utf-8") as handle:
            rules = merge_classification_rules(rules, yaml.safe_load(handle) or {})
    return normalize_classification_rules(rules)


def merge_classification_rules(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if key == "stored_value_reload" and isinstance(value, dict):
            stored_value_rules = merged.setdefault("stored_value_reload", {})
            stored_value_rules.update({k: v for k, v in value.items() if k != "merchants"})
            stored_value_rules["merchants"] = [
                *stored_value_rules.get("merchants", []),
                *value.get("merchants", []),
            ]
        elif isinstance(value, list):
            merged[key] = [*merged.get(key, []), *value]
        else:
            merged[key] = value
    return merged


def normalize_classification_rules(rules: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(rules)
    for key, value in list(normalized.items()):
        if isinstance(value, list):
            normalized[key] = [str(item).upper() for item in value]

    stored_value_rules = normalized.setdefault("stored_value_reload", {})
    stored_value_rules["merchants"] = [str(item).upper() for item in stored_value_rules.get("merchants", [])]
    return normalized


def read_csv_flex(path: Path) -> pd.DataFrame:
    if path.name.lower().startswith("accountactivity"):
        return read_accountactivity_csv(path)

    attempts = [
        {"encoding": "utf-8-sig"},
        {"encoding": "utf-8"},
        {"encoding": "latin1"},
    ]
    last_error: Exception | None = None
    for kwargs in attempts:
        try:
            return pd.read_csv(path, **kwargs)
        except Exception as exc:
            last_error = exc
    raise ValueError(f"Could not read CSV {path.name}: {last_error}") from last_error


def read_accountactivity_csv(path: Path) -> pd.DataFrame:
    attempts = [
        {"encoding": "utf-8-sig"},
        {"encoding": "utf-8"},
        {"encoding": "latin1"},
    ]
    last_error: Exception | None = None
    for kwargs in attempts:
        try:
            return pd.read_csv(
                path,
                header=None,
                names=["Transaction Date", "Description", "Debit", "Credit", "Balance"],
                **kwargs,
            )
        except Exception as exc:
            last_error = exc
    raise ValueError(f"Could not read account activity CSV {path.name}: {last_error}") from last_error


def detect_source(df: pd.DataFrame, file_path: Path, source_rules: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    source_rules = load_source_rules() if source_rules is None else source_rules
    columns = {str(column).strip() for column in df.columns}
    filename = file_path.name.lower()

    for source_name, rule in source_rules.get("sources", {}).items():
        detection = rule.get("detection", {})
        required = set(detection.get("required_columns", []))
        any_columns = set(detection.get("any_columns", []))
        filename_terms = [str(term).lower() for term in detection.get("filename_contains", [])]
        column_values = detection.get("column_values", {})

        required_ok = not required or required.issubset(columns)
        any_ok = not any_columns or bool(any_columns.intersection(columns))
        filename_ok = not filename_terms or any(term in filename for term in filename_terms)
        column_values_ok = all(
            column in df.columns and df[column].dropna().astype(str).str.strip().isin([str(value) for value in values]).any()
            for column, values in column_values.items()
        )

        if required_ok and any_ok and filename_ok and column_values_ok:
            return source_name, rule

    raise ValueError(f"Could not detect source for {file_path.name}. Columns: {sorted(columns)}")


def normalize_transactions(
    df: pd.DataFrame,
    source_name: str,
    rule: dict[str, Any],
    source_file: str,
    classification_rules: dict[str, Any] | None = None,
) -> pd.DataFrame:
    normalized = pd.DataFrame()
    normalized["transaction_date"] = parse_date(get_required_column(df, rule["date_column"]))
    normalized["posted_date"] = parse_date(get_first_available_column(df, optional_column_names(rule, "posted_date")))
    normalized["institution"] = rule.get("institution", source_name)
    normalized["account_name"] = get_account_name(df, rule, source_file)
    normalized["merchant_raw"] = get_merchant_column(df, rule).map(normalize_merchant_text)
    normalized["amount"] = parse_amount(get_amount_column(df, rule)) * float(rule.get("amount_multiplier", 1))
    normalized["currency"] = rule.get("currency", "CAD")
    normalized["source_file"] = source_file
    normalized["ingested_at"] = datetime.now().replace(microsecond=0)
    classification_rules = load_classification_rules() if classification_rules is None else classification_rules
    normalized["transaction_type"] = normalized.apply(lambda row: classify_transaction(row, classification_rules), axis=1)
    normalized["scope"] = rule.get("default_scope", "personal")

    normalized["transaction_id"] = build_transaction_ids(normalized)
    normalized = categorize_transactions(normalized)
    normalized = apply_transaction_type_defaults(normalized)
    return normalized[
        [
            "transaction_id",
            "transaction_date",
            "posted_date",
            "institution",
            "account_name",
            "merchant_raw",
            "merchant_clean",
            "amount",
            "transaction_type",
            "scope",
            "currency",
            "category",
            "subcategory",
            "source_file",
            "ingested_at",
        ]
    ]


def get_required_column(df: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name in df.columns:
        return df[column_name]
    raise ValueError(f"Missing required column: {column_name}")


def optional_column_names(rule: dict[str, Any], base_name: str) -> list[str]:
    primary = rule.get(f"{base_name}_column")
    fallbacks = rule.get(f"fallback_{base_name}_columns", [])
    return [column for column in [primary, *fallbacks] if column]


def get_first_available_column(df: pd.DataFrame, column_names: list[str]) -> pd.Series:
    for column_name in column_names:
        if column_name in df.columns:
            return df[column_name]
    return pd.Series([pd.NaT] * len(df), index=df.index)


def get_merchant_column(df: pd.DataFrame, rule: dict[str, Any]) -> pd.Series:
    merchant_columns = rule.get("merchant_columns")
    if merchant_columns:
        available = [column for column in merchant_columns if column in df.columns]
        if not available:
            raise ValueError(f"Missing merchant columns. Tried: {merchant_columns}")
        return join_text_columns(df, available)

    columns = [rule.get("merchant_column"), *rule.get("fallback_merchant_columns", [])]
    available = [column for column in columns if column and column in df.columns]
    if available:
        return join_text_columns(df, available)
    raise ValueError(f"Missing merchant column. Tried: {[column for column in columns if column]}")


def get_amount_column(df: pd.DataFrame, rule: dict[str, Any]) -> pd.Series:
    if rule.get("debit_column") or rule.get("credit_column"):
        debit = parse_amount(get_first_available_column(df, [rule.get("debit_column")]))
        credit = parse_amount(get_first_available_column(df, [rule.get("credit_column")]))
        return debit - credit

    columns = [
        *rule.get("amount_columns", []),
        rule.get("amount_column"),
        *rule.get("fallback_amount_columns", []),
    ]
    available = [column for column in columns if column and column in df.columns]
    if not available:
        raise ValueError(f"Missing amount column. Tried: {[column for column in columns if column]}")

    amounts = pd.Series([pd.NA] * len(df), index=df.index, dtype="object")
    for column in available:
        values = df[column].replace("", pd.NA)
        amounts = amounts.fillna(values)
    return amounts


def join_text_columns(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    text = pd.Series([""] * len(df), index=df.index, dtype="object")
    for column in columns:
        values = df[column].fillna("").astype(str).str.strip()
        text = (text + " " + values).str.strip()
    return text.str.replace(r"\s+", " ", regex=True)


def get_account_name(df: pd.DataFrame, rule: dict[str, Any], source_file: str) -> pd.Series:
    if rule.get("account_name_template"):
        return build_account_name_from_template(df, rule, source_file)
    if rule.get("account_name_column") in df.columns:
        return df[rule["account_name_column"]].fillna(rule.get("account_name", "Unknown Account")).astype(str)
    return pd.Series([rule.get("account_name", rule.get("institution", "Unknown Account"))] * len(df), index=df.index)


def build_account_name_from_template(df: pd.DataFrame, rule: dict[str, Any], source_file: str) -> pd.Series:
    template = rule["account_name_template"]
    account_type_column = rule.get("account_type_column")
    account_number_column = rule.get("account_number_column")
    account_type = get_string_series(df, account_type_column, "")
    account_number = get_string_series(df, account_number_column, "")
    account_last4 = account_number.map(last4)
    account_aliases = {str(key): str(value) for key, value in rule.get("account_aliases", {}).items()}
    filename_stem = Path(source_file).stem

    values = []
    for index in df.index:
        alias = account_aliases.get(
            str(account_last4.loc[index]),
            fallback_account_alias(account_type.loc[index], account_last4.loc[index]),
        )
        values.append(
            template.format(
                account_type=account_type.loc[index],
                account_number=account_number.loc[index],
                account_last4=account_last4.loc[index],
                account_alias=alias,
                filename_stem=filename_stem,
            ).strip()
        )
    return pd.Series(values, index=df.index)


def get_string_series(df: pd.DataFrame, column_name: str | None, default: str) -> pd.Series:
    if column_name and column_name in df.columns:
        return df[column_name].fillna(default).astype(str).str.strip()
    return pd.Series([default] * len(df), index=df.index)


def last4(value: object) -> str:
    digits = re.sub(r"\D+", "", str(value))
    return digits[-4:] if len(digits) >= 4 else digits


def fallback_account_alias(account_type: str, account_last4: str) -> str:
    account_type = account_type.strip() or "Account"
    return f"RBC {account_type} {account_last4}".strip()


def parse_date(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed.dt.date


def parse_amount(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("CAD", "", regex=False)
        .str.strip()
    )

    def convert(value: str) -> float:
        value = str(value)
        if not value or value.lower() in {"nan", "none"}:
            return 0.0
        if re.match(r"^\(.*\)$", value):
            value = "-" + value.strip("()")
        return float(value)

    return cleaned.map(convert).round(2)


def classify_transaction(row: pd.Series, classification_rules: dict[str, Any] | None = None) -> str:
    rules = load_classification_rules() if classification_rules is None else classification_rules
    amount = float(row["amount"])
    merchant = str(row["merchant_raw"]).upper()
    merchant_words = set(re.sub(r"[^A-Z0-9 ]+", " ", merchant).split())
    account = str(row.get("account_name", "")).upper()
    cash_account = is_cash_account(account)

    if amount > 0:
        if is_stored_value_reload(merchant, amount, rules):
            return "stored_value_reload"
        if any(pattern in merchant for pattern in rules["reimbursement_patterns"]):
            return "reimbursement"
        if cash_account and any(pattern in merchant for pattern in rules["debt_payment_patterns"]):
            return "debt_payment"
        if is_self_transfer(merchant, rules):
            return "transfer"
        if "E-TRANSFER" in merchant or "ETRANSFER" in merchant:
            return "manual_review"
        return "expense"
    if amount == 0:
        return "zero"
    if any(pattern in merchant for pattern in rules["reimbursement_patterns"] + rules["refund_reimbursement_patterns"]):
        return "reimbursement"
    if "TAX REFUND" in merchant or "GST" in merchant or "PROV/LOCAL GVT" in merchant:
        return "income"
    if any(pattern in merchant for pattern in rules["refund_patterns"]):
        return "refund"
    if cash_account and any(pattern in merchant for pattern in rules["income_patterns"]):
        return "income"
    if is_self_transfer(merchant, rules):
        return "transfer"
    if "E-TRANSFER" in merchant or "ETRANSFER" in merchant:
        return "manual_review"
    if any(pattern in merchant for pattern in rules["payment_patterns"]):
        return "payment"
    if any(pattern in merchant_words for pattern in rules["payment_source_patterns"]):
        return "payment"
    if cash_account and any(pattern in merchant for pattern in rules["manual_review_patterns"]):
        return "manual_review"
    if cash_account:
        return "manual_review"
    return "credit"


def is_stored_value_reload(merchant: str, amount: float, rules: dict[str, Any]) -> bool:
    stored_value_rules = rules.get("stored_value_reload", {})
    minimum_amount = stored_value_rules.get("minimum_amount")
    merchants = stored_value_rules.get("merchants", [])
    return minimum_amount is not None and amount >= float(minimum_amount) and any(pattern in merchant for pattern in merchants)


def is_self_transfer(merchant: str, rules: dict[str, Any]) -> bool:
    return any(pattern in merchant for pattern in rules["self_transfer_patterns"])


def is_cash_account(account: str) -> bool:
    return any(
        marker in account
        for marker in [
            "CHEQUING",
            "PREFERRED PACKAGE",
            "WEALTHSIMPLE",
            "PC MONEY",
            "EQ BANK",
            "NEO",
        ]
    )


TRANSACTION_TYPE_DEFAULTS = {
    "reimbursement": ("", ""),
    "stored_value_reload": ("", ""),
    "manual_review": ("", ""),
    "payment": ("", ""),
    "debt_payment": ("", ""),
    "transfer": ("", ""),
    "income": ("", ""),
}


def apply_transaction_type_defaults(df: pd.DataFrame) -> pd.DataFrame:
    updated = df.copy()
    for transaction_type, (category, subcategory) in TRANSACTION_TYPE_DEFAULTS.items():
        uncategorized_placeholder = updated["category"].eq("Other") & updated["subcategory"].eq("Uncategorized")
        mask = (
            updated["transaction_type"].eq(transaction_type)
            & (
                updated["category"].isna()
                | updated["category"].eq("")
                | updated["category"].eq("Uncategorized")
                | uncategorized_placeholder
            )
        )
        updated.loc[mask, "category"] = category
        updated.loc[mask, "subcategory"] = subcategory
    return updated


def build_transaction_ids(df: pd.DataFrame) -> pd.Series:
    signatures = df.apply(build_transaction_signature, axis=1)
    occurrence_numbers = signatures.groupby(signatures).cumcount() + 1
    return pd.Series(
        [
            hash_transaction_id(signature, occurrence_number)
            for signature, occurrence_number in zip(signatures, occurrence_numbers, strict=True)
        ],
        index=df.index,
    )


def build_transaction_signature(row: pd.Series) -> str:
    transaction_date = pd.to_datetime(row["transaction_date"], errors="coerce")
    date_key = "" if pd.isna(transaction_date) else str(transaction_date.date())
    merchant_key = str(row["merchant_raw"]).upper().strip()
    transaction_type = str(row.get("transaction_type", "")).lower()
    if transaction_type in {"payment", "debt_payment"}:
        merchant_key = transaction_type.upper()

    key_parts = [
        date_key,
        f"{float(row['amount']):.2f}",
        merchant_key,
        str(row["account_name"]).upper().strip(),
    ]
    return "|".join(key_parts)


def hash_transaction_id(signature: str, occurrence_number: int) -> str:
    if occurrence_number == 1:
        return hashlib.sha256(signature.encode("utf-8")).hexdigest()
    key = f"{signature}|occurrence:{occurrence_number}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
