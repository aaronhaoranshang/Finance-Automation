# Finance Automation

Local-first personal finance automation for importing bank/card statements, normalizing transactions, categorizing merchants, and reviewing spending in a dashboard.

The app is designed so a friend can test it with their own files without editing code or sharing financial data with a cloud service.

## Project

The active app lives in [`personal-finance/`](personal-finance/).

## Local-First Privacy

- Financial data stays on the user's device.
- No bank login credentials are collected.
- No cloud sync is enabled by default.
- The local DuckDB database is ignored by git.

See [`personal-finance/docs/PRIVACY.md`](personal-finance/docs/PRIVACY.md).

## Quick Start

```bash
cd personal-finance
conda env create -f environment.yml
conda activate finance
python src/finance.py dashboard --port 8502
```

On first launch, the app creates a local database, runs SQL migrations, seeds default categories/source profiles/rules, and opens the import flow.

## Developer Docs

- [`ARCHITECTURE.md`](personal-finance/docs/ARCHITECTURE.md)
- [`DATA_MODEL.md`](personal-finance/docs/DATA_MODEL.md)
- [`IMPORT_PIPELINE.md`](personal-finance/docs/IMPORT_PIPELINE.md)
- [`PRIVACY.md`](personal-finance/docs/PRIVACY.md)

## Tests

```bash
cd personal-finance
pytest
```
