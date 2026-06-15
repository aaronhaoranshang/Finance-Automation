from __future__ import annotations

import pandas as pd

from db import connect, load_import_batches, load_raw_import_rows


def load_import_batch_table() -> pd.DataFrame:
    con = connect()
    try:
        return load_import_batches(con)
    finally:
        con.close()


def load_raw_import_row_table(import_batch_id: str) -> pd.DataFrame:
    con = connect()
    try:
        return load_raw_import_rows(con, import_batch_id)
    finally:
        con.close()

