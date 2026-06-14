from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


SOURCE_PROFILE_COLUMNS = [
    "source_id",
    "source_name",
    "institution",
    "account_type",
    "file_type",
    "account_name",
    "account_name_template",
    "processed_file_label",
    "processed_file_label_template",
    "currency",
    "amount_multiplier",
    "default_scope",
    "account_aliases",
    "priority",
    "enabled",
]


def get_enabled_source_profiles(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        f"""
        SELECT {", ".join(SOURCE_PROFILE_COLUMNS)}
        FROM source_profile
        WHERE enabled
        ORDER BY priority, source_id
        """
    ).df()


def detect_source_from_db(
    con: duckdb.DuckDBPyConnection,
    raw_df: pd.DataFrame,
    file_path: Path,
    debug: bool = False,
) -> tuple[str, dict[str, Any]]:
    profiles = get_enabled_source_profiles(con)
    rules = con.execute(
        """
        SELECT
            rule_id,
            source_id,
            required_columns,
            optional_columns,
            filename_pattern,
            header_pattern,
            column_value_rules,
            priority,
            enabled
        FROM source_detection_rule
        WHERE enabled
        ORDER BY priority, rule_id
        """
    ).df()
    if profiles.empty or rules.empty:
        raise ValueError("No enabled SQL source profiles/detection rules found.")

    profile_by_id = {row.source_id: row._asdict() for row in profiles.itertuples(index=False)}
    columns = {str(column).strip() for column in raw_df.columns}
    header_text = " ".join(sorted(columns))
    filename = file_path.name
    debug_lines = []
    matches = []

    for row in rules.itertuples(index=False):
        profile = profile_by_id.get(row.source_id)
        if not profile:
            continue

        required_columns = json_list(row.required_columns)
        optional_columns = json_list(row.optional_columns)
        column_value_rules = json_dict(row.column_value_rules)

        missing_required = [column for column in required_columns if column not in columns]
        required_ok = not missing_required
        optional_ok = not optional_columns or any(column in columns for column in optional_columns)
        if not required_columns and optional_columns:
            optional_ok = any(column in columns for column in optional_columns)
        filename_ok = pattern_matches(row.filename_pattern, filename)
        header_ok = pattern_matches(row.header_pattern, header_text)
        values_ok, missing_values = column_values_match(raw_df, column_value_rules)

        matched = required_ok and optional_ok and filename_ok and header_ok and values_ok
        specificity = (
            len(required_columns) * 10
            + len(optional_columns)
            + len(column_value_rules) * 5
            + int(bool(row.filename_pattern)) * 3
            + int(bool(row.header_pattern)) * 2
        )
        if matched:
            matches.append((int(row.priority), -specificity, int(profile.get("priority") or 100), int(row.rule_id), row.source_id, profile))

        if debug:
            debug_lines.append(
                f"{row.source_id}: "
                f"required={'ok' if required_ok else 'missing ' + ', '.join(missing_required)}; "
                f"optional={'ok' if optional_ok else 'no optional column matched'}; "
                f"filename={'ok' if filename_ok else 'no match'}; "
                f"header={'ok' if header_ok else 'no match'}; "
                f"values={'ok' if values_ok else 'no values ' + ', '.join(missing_values)}; "
                f"matched={matched}"
            )

    if not matches:
        detail = f" Columns: {sorted(columns)}"
        if debug and debug_lines:
            detail += "\n" + "\n".join(debug_lines)
        raise ValueError(f"Could not detect source for {file_path.name}.{detail}")

    matches.sort()
    _, _, _, _, source_id, profile = matches[0]
    rule = source_profile_to_rule(profile)
    rule["_metadata_source"] = True
    if debug:
        rule["_debug"] = debug_lines
    return str(source_id), rule


def get_source_column_mapping(con: duckdb.DuckDBPyConnection, source_id: str) -> pd.DataFrame:
    return con.execute(
        """
        SELECT
            source_column,
            target_column,
            required,
            transform_rule,
            sort_order,
            enabled
        FROM source_column_mapping
        WHERE source_id = ?
          AND enabled
        ORDER BY target_column, sort_order, mapping_id
        """,
        [source_id],
    ).df()


def apply_source_mapping(
    raw_df: pd.DataFrame,
    source_id: str,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    if con is None:
        from db import connect

        owned_con = connect()
        try:
            return apply_source_mapping(raw_df, source_id, con=owned_con)
        finally:
            owned_con.close()

    mappings = get_source_column_mapping(con, source_id)
    if mappings.empty:
        raise ValueError(f"No source column mappings configured for {source_id}.")

    mapped = pd.DataFrame(index=raw_df.index)
    for target_column, target_mappings in mappings.groupby("target_column", sort=False):
        mapped[target_column] = build_mapped_column(raw_df, target_column, target_mappings)

    if "amount" not in mapped.columns and {"debit_amount", "credit_amount"}.issubset(mapped.columns):
        mapped["amount"] = mapped["debit_amount"].fillna(0) - mapped["credit_amount"].fillna(0)

    validate_mapped_source(mapped, mappings, source_id)
    return mapped


def build_mapped_column(raw_df: pd.DataFrame, target_column: str, mappings: pd.DataFrame) -> pd.Series:
    pieces = []
    missing_required = []
    for row in mappings.itertuples(index=False):
        source_column = str(row.source_column)
        required = bool(row.required)
        if source_column not in raw_df.columns:
            if required:
                missing_required.append(source_column)
            elif target_column in {"debit_amount", "credit_amount"}:
                pieces.append(pd.Series([0.0] * len(raw_df), index=raw_df.index))
            continue

        series = raw_df[source_column]
        value_required = required and len(mappings) == 1
        pieces.append(apply_transform(series, str(row.transform_rule or ""), value_required))

    if missing_required:
        raise ValueError(f"Missing required source column(s) for {target_column}: {', '.join(missing_required)}")
    if not pieces:
        return pd.Series([pd.NA] * len(raw_df), index=raw_df.index, dtype="object")
    if target_column in {"merchant_raw", "description_raw"}:
        return join_text_pieces(pieces)
    return first_non_null(pieces)


def apply_transform(series: pd.Series, transform_rule: str, required: bool) -> pd.Series:
    transforms = [part.strip() for part in transform_rule.split("|") if part.strip()]
    result = series.copy()
    for transform in transforms:
        if transform == "clean_text":
            result = clean_text(result)
        elif transform == "parse_date":
            parsed = pd.to_datetime(result, errors="coerce").dt.date
            if required and parsed.isna().any():
                raise ValueError("Invalid or missing date in required date column.")
            result = parsed
        elif transform == "parse_amount":
            result = parse_amount_strict(result, required=required)
        elif transform == "credit_card_sign":
            result = parse_amount_strict(result, required=required) * -1
        elif transform == "debit_credit_split":
            result = parse_amount_strict(result, required=False, blank_as_zero=True)
        elif transform == "":
            continue
        else:
            raise ValueError(f"Unsupported source transform_rule: {transform}")
    return result


def validate_mapped_source(mapped: pd.DataFrame, mappings: pd.DataFrame, source_id: str) -> None:
    required_targets = set(mappings.loc[mappings["required"].astype(bool), "target_column"].dropna().astype(str))
    if "transaction_date" in required_targets:
        if "transaction_date" not in mapped.columns or pd.Series(mapped["transaction_date"]).isna().any():
            raise ValueError(f"{source_id}: transaction_date is required and contains missing/invalid values.")
    if "amount" in required_targets:
        if "amount" not in mapped.columns or pd.Series(mapped["amount"]).isna().any():
            raise ValueError(f"{source_id}: amount is required and contains missing/invalid values.")
    if "amount" in mapped.columns and pd.Series(mapped["amount"]).isna().any():
        raise ValueError(f"{source_id}: amount mapping produced missing/invalid values.")
    if "merchant_raw" in mapped.columns and clean_text(mapped["merchant_raw"]).eq("").any():
        raise ValueError(f"{source_id}: merchant_raw mapping produced blank values.")
    if {"debit_amount", "credit_amount"}.intersection(required_targets):
        if "amount" not in mapped.columns or pd.Series(mapped["amount"]).isna().any():
            raise ValueError(f"{source_id}: debit/credit amount mapping did not produce a valid amount.")


def parse_amount_strict(series: pd.Series, required: bool, blank_as_zero: bool = False) -> pd.Series:
    text = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("CAD", "", regex=False)
        .str.strip()
    )
    blanks = text.eq("") | text.str.lower().isin({"nan", "none", "<na>"})
    if required and blanks.any():
        raise ValueError("Missing amount in required amount column.")
    text = text.mask(blanks, "0" if blank_as_zero else pd.NA)
    text = text.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    parsed = pd.to_numeric(text, errors="coerce")
    if required and parsed.isna().any():
        raise ValueError("Invalid amount in required amount column.")
    if blank_as_zero:
        parsed = parsed.fillna(0)
    return parsed.round(2)


def clean_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.replace(r"\s+", " ", regex=True)


def join_text_pieces(pieces: list[pd.Series]) -> pd.Series:
    text = pd.Series([""] * len(pieces[0]), index=pieces[0].index, dtype="object")
    for piece in pieces:
        text = (text + " " + clean_text(piece)).str.strip()
    return text.str.replace(r"\s+", " ", regex=True)


def first_non_null(pieces: list[pd.Series]) -> pd.Series:
    result = pd.Series([pd.NA] * len(pieces[0]), index=pieces[0].index, dtype="object")
    for piece in pieces:
        values = piece.replace("", pd.NA)
        result = result.fillna(values)
    return result


def source_profile_to_rule(profile: dict[str, Any]) -> dict[str, Any]:
    account_aliases = json_dict(profile.get("account_aliases"))
    return {
        "institution": profile.get("institution") or profile.get("source_name") or profile.get("source_id"),
        "account_name": profile.get("account_name") or profile.get("source_name") or "Unknown Account",
        "account_name_template": profile.get("account_name_template") or "",
        "processed_file_label": profile.get("processed_file_label") or "",
        "processed_file_label_template": profile.get("processed_file_label_template") or "",
        "currency": profile.get("currency") or "CAD",
        "amount_multiplier": float(profile.get("amount_multiplier") or 1),
        "default_scope": profile.get("default_scope") or "personal",
        "account_aliases": account_aliases,
    }


def column_values_match(raw_df: pd.DataFrame, rules: dict[str, Any]) -> tuple[bool, list[str]]:
    missing = []
    for column, expected_values in rules.items():
        if column not in raw_df.columns:
            missing.append(column)
            continue
        expected = {str(value).strip() for value in expected_values}
        actual = set(raw_df[column].dropna().astype(str).str.strip().tolist())
        if not actual.intersection(expected):
            missing.append(f"{column}={sorted(expected)}")
    return not missing, missing


def pattern_matches(pattern: object, value: str) -> bool:
    if pattern is None or pd.isna(pattern) or str(pattern).strip() == "":
        return True
    text = str(pattern).strip()
    try:
        return re.search(text, value, re.I) is not None
    except re.error:
        return text.lower() in value.lower()


def json_list(value: object) -> list[str]:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return []
    parsed = json.loads(str(value))
    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON list, got: {value}")
    return [str(item) for item in parsed]


def json_dict(value: object) -> dict[str, Any]:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return {}
    parsed = json.loads(str(value))
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object, got: {value}")
    return parsed
