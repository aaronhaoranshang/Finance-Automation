from __future__ import annotations

import argparse
from pathlib import Path

from db import connect
from normalize import read_csv_flex
from pdf_extract import read_pdf_statement
from source_metadata import detect_source_from_db, get_enabled_source_profiles, get_source_column_mapping


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect SQL source profiles and mappings.")
    parser.add_argument("--detect", type=Path, help="Optional CSV/PDF file to test source detection.")
    parser.add_argument("--debug", action="store_true", help="Print source detection match/fail details.")
    args = parser.parse_args()

    con = connect()
    try:
        profiles = get_enabled_source_profiles(con)
        print("Enabled source profiles")
        print(profiles.to_string(index=False))
        for source_id in profiles["source_id"].tolist():
            print(f"\nMapping: {source_id}")
            print(get_source_column_mapping(con, source_id).to_string(index=False))

        if args.detect:
            raw = read_pdf_statement(args.detect) if args.detect.suffix.lower() == ".pdf" else read_csv_flex(args.detect)
            source_id, rule = detect_source_from_db(con, raw, args.detect, debug=args.debug)
            print(f"\nDetected: {source_id}")
            if args.debug:
                for line in rule.get("_debug", []):
                    print(line)
    finally:
        con.close()


if __name__ == "__main__":
    main()
