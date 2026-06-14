# Personal Finance Automation

Local-first personal finance automation with CSV/PDF ingestion, DuckDB storage, SQL-backed metadata, merchant rules, and a Streamlit dashboard.

## Privacy First

- Your financial data stays on this device.
- No cloud sync is enabled by default.
- No bank login credentials are collected.
- You import files that you download yourself from your bank/card provider.

More detail: [`docs/PRIVACY.md`](docs/PRIVACY.md).

## Setup

```bash
conda env create -f environment.yml
conda activate finance
python src/finance.py dashboard --port 8502
```

Or install packages manually:

```bash
conda create -n finance python=3.12
conda activate finance
pip install -r requirements.txt
python src/finance.py dashboard --port 8502
```

## First Launch

On a new computer, the app starts with a setup screen:

1. Confirm local-first setup.
2. Choose base currency and region.
3. Create the local database.
4. Upload CSV/PDF statements from the Imports page.

The app creates:

- a local DuckDB database
- default transaction types
- default categories/subcategories
- default source profiles and column mappings
- default merchant rules
- import, processed, failed, backup, and user-data folders

## Main Pages

- `Imports`: upload, preview, reconcile totals, and import statements.
- `Overview`: monthly spend, income, refunds, reimbursements, and excluded movement.
- `Monthly Detail`: month-level category, merchant, account, and transaction views.
- `Audit`: import batches, raw row statuses, duplicate counts, and failed row messages.
- `Drilldown`: inspect the exact transactions behind dashboard metrics.
- `Review Queue`: classify uncertain transactions and optionally save future rules.
- `Merchant Rules`: manage My Rules and inspect default rules.
- `Transactions`: filter and edit individual transactions.
- `Settings`: database path, backup, restore, export, and reset tools.

## Data Model

The app keeps transaction type separate from category/subcategory.

- `transaction_type` describes money movement nature, such as `expense`, `income`, `payment`, `transfer`, or `reimbursement`.
- `category` and `subcategory` describe spending purpose, such as `Food / Coffee` or `Travel / Flights`.

Category dropdowns read from SQL metadata in `category_master`; they are not inferred from old transactions.

More detail: [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md).

## Import Pipeline

Each import creates an `import_batch`, stores every raw row in `raw_import_row`, normalizes transactions, tracks duplicates row-by-row, and writes classification audit entries.

More detail: [`docs/IMPORT_PIPELINE.md`](docs/IMPORT_PIPELINE.md).

## Backups

Use Settings to export a backup zip containing the DuckDB database and metadata CSV exports. Restore creates a rollback backup before replacing the current local database.

The app also creates a database backup before applying new migrations to an existing database.

## Development

Runtime configuration lives in DuckDB metadata tables, not YAML:

- `transaction_type_master`
- `category_master`
- `merchant_rule`
- `source_profile`
- `source_detection_rule`
- `source_column_mapping`
- `import_batch`
- `raw_import_row`
- `transaction_classification_audit`

Developer docs:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)
- [`docs/IMPORT_PIPELINE.md`](docs/IMPORT_PIPELINE.md)
- [`docs/PRIVACY.md`](docs/PRIVACY.md)

## Tests

```bash
pytest
```

## Desktop Packaging

Desktop builds use PyInstaller and should be built on the target operating system.

macOS:

```bash
./scripts/build_macos.sh
```

Windows PowerShell:

```powershell
.\scripts\build_windows.ps1
```

The app is intentionally kept compatible with future desktop packaging: local database, OS-specific app data folder when packaged, no server dependency, and no cloud requirement.
