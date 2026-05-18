# Personal Finance Automation

Local Mac-friendly finance automation with CSV ingestion, DuckDB storage, merchant rules, and a Streamlit dashboard.

## Setup

```bash
conda create -n finance python=3.12
conda activate finance
cd personal-finance
pip install -r requirements.txt
```

Or create the environment from the included file:

```bash
conda env create -f environment.yml
conda activate finance
```

## Use

Drop bank CSV files into `imports/to_import`, then run:

```bash
python src/ingest.py
streamlit run src/app.py
```

Preview an import before writing to DuckDB or moving files:

```bash
python src/ingest.py --dry-run
python src/ingest.py --dry-run imports/to_import/example.csv
```

The preview includes detected account, majority transaction month, processed filename, duplicate count, gross expenses, refunds/credits, card payments, net spend, and the file net total for quick reconciliation.

To auto-import new CSVs while the folder is open:

```bash
python src/watcher.py
```

The DuckDB file is created at `data/finance.duckdb`.

## Dashboard

Run:

```bash
streamlit run src/app.py
```

Main pages:

- `Overview`: filtered gross spend, refunds/credits, net spend, income, and ignored movement.
- `Monthly Detail`: month-level category, subcategory, merchant, account, and transaction drilldowns.
- `Reconciliation`: account-month and source-file tables for comparing against a manual tracker, with CSV download.
- `Drilldown`: choose a metric such as ignored movement, income, transfers, or refunds and see the exact transactions behind it.
- `Merchant Rules`: uncategorized queue plus flexible rule creation.
- `Transactions`: raw filtered transaction table.

Use the sidebar filters to reconcile one month/account/type at a time.

Processed CSVs are renamed when they move into `imports/processed`, using the account label and the month containing the majority of transactions. Examples:

- `MBNA Apr 2026.csv`
- `RBC Avion Apr 2026.csv`
- `RBC ION Apr 2026.csv`
- `Scotiabank Apr 2026.csv`

## Configure Sources

Bank-specific CSV rules live in `rules/source_rules.yml`. Each source can define detection columns, transaction/posting date columns, merchant columns, amount columns, and account naming.

Current statement mappings:

- `Apr2026_9426.csv` style files are detected as `MBNA 9426`.
- `download-transactions.csv` style RBC exports are detected from `Account Type`, `Account Number`, `Description 1`, and `CAD$`; `9419` is labelled `RBC ION`, while `6046` and `6064` are labelled `RBC Avion`.
- `Scotia_Momentum_Visa_Infinite__Card_3128_050926.csv` style files are detected as `Scotia Momentum Visa Infinite 3128`.
- `Preferred_Package_9623_051026.csv` style files are detected as `Scotiabank Preferred Package 9623`.
- `accountactivity*.csv` no-header Triangle exports are detected as Triangle account activity.
- `*Triangle-WorldEliteMastercard.pdf` PDF statements are parsed with `pdfplumber`.

Amounts are normalized so spending/outflows are positive and credits/payments are negative.

Transaction types:

- `expense`: included in spending.
- `payment`: card payment or bill payment; ignored for spending and net owed activity.
- `refund` / `credit`: subtracts from spending, so net spend is expenses minus refunds/merchant credits.
- `debt_payment`: cash leaving chequing to pay a credit card or similar debt; ignored for spending because the card purchases are already counted.
- `transfer`: movement between your own accounts; ignored for spending and income.
- `income`: true inflow such as employment income or rent collected.

For whole-person reporting, internal transfers are not income. They can still be useful for account-level cash flow, but they should not inflate total income or reduce spending.

## Configure Merchants

Merchant rules live in `rules/merchant_rules.yml`. You can edit the file directly or use the Streamlit `Uncategorized` page to save new rules.

After editing `rules/merchant_rules.yml` by hand, reapply the rules to transactions already in DuckDB:

```bash
python src/categorize.py --refresh-db
```

If you save a rule from the Streamlit `Uncategorized` page, the app refreshes existing rows for you.

The dashboard `Merchant Rules` page supports custom categories and optional subcategories. Leave subcategory blank when it does not add useful detail.

If DuckDB says another app has a lock, close DBeaver or Streamlit and run the command again.

To remove pre-2026 transactions after import:

```sql
DELETE FROM transactions
WHERE transaction_date < DATE '2026-01-01';
```
