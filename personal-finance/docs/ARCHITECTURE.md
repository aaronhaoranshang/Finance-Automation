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

- `src/app.py`: thin Streamlit entrypoint and page router.
- `src/ui/pages/`: page-level Streamlit rendering for imports, dashboard views, review, rules, transactions, and settings.
- `src/ui/components.py`: reusable Streamlit controls and display helpers.
- `src/ui/constants.py`: UI labels, options, and fallback display values.
- `src/ui/theme.py`: Streamlit page configuration and shared theme setup.
- `src/services/`: application-facing services for dashboard calculations, transactions, categories, rules, reviews, imports, and backups.
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

## Dependency Direction

```text
app.py
  -> ui/pages
  -> ui/components + services
  -> domain/data modules
  -> DuckDB
```

Page modules own user interaction. Services own reusable calculations and database workflows. Core modules such as `ingest.py`, `categorize.py`, and `reclassify.py` remain independent of Streamlit so the UI can be replaced later without rewriting finance logic.

## Desktop Packaging

The app is kept compatible with future desktop packaging:

- no server database required
- no cloud dependency
- no hard-coded user home paths
- data folder can be overridden with `PERSONAL_FINANCE_HOME`
- app data defaults to OS-specific application support folders when packaged
