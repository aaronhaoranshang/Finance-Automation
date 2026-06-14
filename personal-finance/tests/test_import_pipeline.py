from __future__ import annotations


def write_mbna_csv(path, rows: str) -> None:
    path.write_text(f"Posted Date,Payee,Amount\n{rows}", encoding="utf-8")


def test_import_duplicate_tracking(app_modules):
    app_modules.paths.ensure_project_dirs()

    first_file = app_modules.paths.TO_IMPORT_DIR / "sample_mbna.csv"
    write_mbna_csv(first_file, "2026-01-02,STARBUCKS 123,5.25\n")
    first = app_modules.ingest.ingest_file(first_file)
    assert first["status"] == "processed"
    assert first["rows_inserted"] == 1
    assert first["duplicates"] == 0

    second_file = app_modules.paths.TO_IMPORT_DIR / "sample_mbna.csv"
    write_mbna_csv(second_file, "2026-01-02,STARBUCKS 123,5.25\n")
    second = app_modules.ingest.ingest_file(second_file)
    assert second["status"] == "processed"
    assert second["rows_inserted"] == 0
    assert second["duplicates"] == 1

    con = app_modules.db.connect()
    try:
        batches = con.execute(
            """
            SELECT status, rows_seen, rows_inserted, rows_duplicate, rows_failed
            FROM import_batch
            ORDER BY imported_at
            """
        ).fetchall()
        assert batches == [("processed", 1, 1, 0, 0), ("processed", 1, 0, 1, 0)]
        statuses = con.execute(
            """
            SELECT status
            FROM raw_import_row
            ORDER BY created_at, import_batch_id
            """
        ).fetchall()
        assert ("inserted",) in statuses
        assert ("duplicate",) in statuses
    finally:
        con.close()


def test_invalid_date_fails_import_with_row_error(app_modules):
    app_modules.paths.ensure_project_dirs()
    file_path = app_modules.paths.TO_IMPORT_DIR / "bad_date_mbna.csv"
    write_mbna_csv(file_path, "not-a-date,STARBUCKS 123,5.25\n")

    result = app_modules.ingest.ingest_file(file_path)
    assert result["status"] == "failed"
    assert result["rows_inserted"] == 0

    con = app_modules.db.connect()
    try:
        batch = con.execute(
            "SELECT status, rows_seen, rows_inserted, rows_failed FROM import_batch"
        ).fetchone()
        assert batch == ("failed", 1, 0, 1)
        row = con.execute("SELECT status, error_message FROM raw_import_row").fetchone()
        assert row[0] == "failed"
        assert "date" in row[1].lower()
    finally:
        con.close()


def test_missing_amount_fails_import(app_modules):
    app_modules.paths.ensure_project_dirs()
    file_path = app_modules.paths.TO_IMPORT_DIR / "missing_amount_mbna.csv"
    file_path.write_text("Posted Date,Payee\n2026-01-02,STARBUCKS 123\n", encoding="utf-8")

    result = app_modules.ingest.ingest_file(file_path)
    assert result["status"] == "failed"
    assert result["rows_inserted"] == 0

    con = app_modules.db.connect()
    try:
        batch = con.execute(
            "SELECT status, rows_seen, rows_inserted, rows_failed, message FROM import_batch"
        ).fetchone()
        assert batch[:4] == ("failed", 1, 0, 1)
        assert "could not detect source" in batch[4].lower()
        row = con.execute("SELECT status, error_message FROM raw_import_row").fetchone()
        assert row[0] == "failed"
        assert "could not detect source" in row[1].lower()
    finally:
        con.close()
