# Architecture

Personal Finance Automation is a local-first Streamlit desktop-style app backed by DuckDB.

## Runtime Shape

```text
CSV/PDF statements
  -> import preview
  -> raw import audit rows
  -> SQL source detection and mapping
  -> transaction normalization
  -> SQL merchant rules
  -> DuckDB transactions
  -> Streamlit dashboard
```

## Main Modules

- `src/app.py`: Streamlit UI, first-time setup, imports, dashboard, review queue, settings.
- `src/db.py`: DuckDB connection, base tables, app settings, inserts, updates, import audit access.
- `src/migrations.py`: SQL migration runner and metadata table verification.
- `src/metadata.py`: category and transaction type metadata queries.
- `src/source_metadata.py`: SQL-backed source detection and column mapping.
- `src/ingest.py`: file import, preview, raw row audit, duplicate tracking, processed/failed file movement.
- `src/normalize.py`: transaction normalization and transaction type classification.
- `src/categorize.py`: SQL merchant rule loading, matching, validation, and saving.
- `src/reclassify.py`: dry-run and apply workflow for reclassifying existing transactions.
- `src/backup.py`: backup export, restore, and pre-migration rollback backups.

## Data Ownership

DuckDB is the runtime source of truth for:

- transaction types
- categories and subcategories
- merchant rules
- source profiles
- source detection rules
- source column mappings
- import batches
- raw import rows
- classification audit

YAML files may remain for legacy migration or developer reference, but normal runtime behavior should not depend on YAML.

## Desktop Packaging

The app is kept compatible with future desktop packaging:

- no server database required
- no cloud dependency
- no hard-coded user home paths
- data folder can be overridden with `PERSONAL_FINANCE_HOME`
- app data defaults to OS-specific application support folders when packaged
