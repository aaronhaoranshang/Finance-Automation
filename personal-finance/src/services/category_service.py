from __future__ import annotations

import pandas as pd

from db import connect
from metadata import (
    add_user_category,
    disable_user_category,
    get_categories,
    get_category_master,
    get_subcategories,
    get_user_category_pairs,
    validate_category_pair,
)


def available_categories(_df: pd.DataFrame | None = None) -> list[str]:
    con = connect()
    try:
        categories = get_categories(con)
    finally:
        con.close()
    return [*categories, "Custom"]


def available_subcategories(category: str, _df: pd.DataFrame | None = None) -> list[str]:
    con = connect()
    try:
        subcategories = get_subcategories(con, category)
    finally:
        con.close()
    return subcategories


def save_category_metadata(category: str, subcategory: str = "", sort_order: int = 100) -> None:
    category = category.strip()
    subcategory = subcategory.strip()
    if subcategory and not category:
        raise ValueError("Select an existing category before adding a subcategory.")
    if not category:
        return
    if category == "Custom":
        raise ValueError("Enter a real category name, not Custom.")

    con = connect()
    try:
        add_user_category(con, category, subcategory, sort_order=sort_order)
    finally:
        con.close()


def category_pair_valid(category: str, subcategory: str) -> bool:
    con = connect()
    try:
        return validate_category_pair(con, category, subcategory)
    finally:
        con.close()


def category_master_pairs() -> set[tuple[str, str]]:
    con = connect()
    try:
        category_master = get_category_master(con)
    finally:
        con.close()
    if category_master.empty:
        return set()
    return {(str(row.category), str(row.subcategory or "")) for row in category_master.itertuples()}


def load_category_master(include_disabled: bool = False) -> pd.DataFrame:
    con = connect()
    try:
        return get_category_master(con, include_disabled=include_disabled)
    finally:
        con.close()


def load_user_category_pairs() -> pd.DataFrame:
    con = connect()
    try:
        return get_user_category_pairs(con)
    finally:
        con.close()


def disable_category_metadata(category: str, subcategory: str) -> None:
    con = connect()
    try:
        disable_user_category(con, category, subcategory)
    finally:
        con.close()
