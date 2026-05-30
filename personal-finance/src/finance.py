from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from db import connect, load_transactions
from ingest import ingest_directory, ingest_file, preview_paths
from normalize import apply_transaction_type_defaults, classify_transaction, load_classification_rules
from paths import TO_IMPORT_DIR
from watcher import watch_imports


def run_import(args: argparse.Namespace) -> None:
    if args.dry_run:
        preview_paths(args.paths, admin=args.admin)
        return

    results = [ingest_file(path, admin=args.admin) for path in args.paths] if args.paths else ingest_directory(admin=args.admin)
    if not results:
        print(f"No CSV/PDF files found in {TO_IMPORT_DIR}.")
        return

    for result in results:
        if result["status"] == "processed":
            print(
                f"Processed {result['file']}: "
                f"{result['rows_inserted']}/{result['rows_seen']} new rows, "
                f"{result.get('duplicates', 0)} duplicates."
            )
        else:
            print(f"Failed {result['file']}: {result.get('error', 'unknown error')}")


def run_refresh(args: argparse.Namespace) -> None:
    rows = refresh_transaction_types(admin=args.admin)
    print(f"Refreshed {rows} transactions.")


def run_dashboard(args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "src/app.py",
        "--server.port",
        str(args.port),
    ]
    subprocess.run(command, check=False)


def run_watch(args: argparse.Namespace) -> None:
    watch_imports(admin=args.admin)


def refresh_transaction_types(admin: bool = False) -> int:
    classification_rules = load_classification_rules(admin=admin)
    con = connect()
    try:
        transactions = load_transactions(con)
        if transactions.empty:
            return 0

        refreshed = transactions.copy()
        refreshed["transaction_type"] = refreshed.apply(lambda row: classify_transaction(row, classification_rules), axis=1)
        if "scope" not in refreshed.columns:
            refreshed["scope"] = "personal"
        refreshed["scope"] = refreshed["scope"].fillna("personal").replace("", "personal")
        refreshed = apply_transaction_type_defaults(refreshed)

        payload = refreshed[["transaction_id", "transaction_type", "scope", "category", "subcategory"]].copy()
        con.register("transaction_refresh", payload)
        con.execute(
            """
            UPDATE transactions
            SET
                transaction_type = transaction_refresh.transaction_type,
                scope = transaction_refresh.scope,
                category = transaction_refresh.category,
                subcategory = transaction_refresh.subcategory
            FROM transaction_refresh
            WHERE transactions.transaction_id = transaction_refresh.transaction_id
            """
        )
        con.unregister("transaction_refresh")
        return len(payload)
    finally:
        con.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Personal finance automation CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import", help="Import CSV/PDF statements into DuckDB.")
    import_parser.add_argument("--admin", action="store_true", help="Use local private source and classification overlays.")
    import_parser.add_argument("--dry-run", action="store_true", help="Preview without writing or moving files.")
    import_parser.add_argument("paths", nargs="*", type=Path, help="Optional statement files. Defaults to imports/to_import.")
    import_parser.set_defaults(func=run_import)

    refresh_parser = subparsers.add_parser("refresh", help="Reclassify existing DuckDB transactions.")
    refresh_parser.add_argument("--admin", action="store_true", help="Use local private classification overlay.")
    refresh_parser.set_defaults(func=run_refresh)

    dashboard_parser = subparsers.add_parser("dashboard", help="Start the Streamlit dashboard.")
    dashboard_parser.add_argument("--port", type=int, default=8501)
    dashboard_parser.set_defaults(func=run_dashboard)

    watch_parser = subparsers.add_parser("watch", help="Watch imports/to_import and auto-import new statements.")
    watch_parser.add_argument("--admin", action="store_true", help="Use local private source and classification overlays.")
    watch_parser.set_defaults(func=run_watch)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
