# Personal Finance Automation

Local personal finance automation with CSV/PDF ingestion, DuckDB storage, merchant rules, and a desktop dashboard.

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

Start the app:

```bash
python src/finance.py dashboard --port 8502
```

On a new computer, the app starts fresh with an empty local DuckDB database and generic rules. Open the `Imports` page, upload CSV/PDF statements, preview them, then import.

Use `src/finance.py` only for optional terminal automation. The other Python files are internal modules used by the app.

For your personal database, use `--admin`:

```bash
python src/finance.py import --admin --dry-run
python src/finance.py import --admin
python src/finance.py dashboard --port 8502
```

Common commands:

```bash
python src/finance.py import --admin                  # import files from imports/to_import
python src/finance.py import --admin --dry-run        # preview import without writing/moving files
python src/finance.py refresh --admin                 # reclassify existing DuckDB rows after rule changes
python src/finance.py dashboard --port 8502           # open the dashboard
python src/finance.py watch --admin                   # auto-import new CSV/PDF files dropped into imports/to_import
```

The preview includes detected account, majority transaction month, processed filename, duplicate count, gross expenses, refunds/credits, payments, reimbursements, prepaid card reloads, needs-review amount, personal net spend, and the file net total for quick checking. Personal net spend subtracts both refunds/credits and reimbursements/paybacks from gross expenses.

In development, the DuckDB file is created at `data/finance.duckdb`. In a packaged desktop app, each computer gets its own fresh local data folder:

- macOS: `~/Library/Application Support/Personal Finance Automation`
- Windows: `%LOCALAPPDATA%\Personal Finance Automation`

Set `PERSONAL_FINANCE_HOME` if you want to override the data folder.

Runtime metadata is stored in DuckDB. On first connection, the app runs SQL migrations from `migrations/` and tracks them in `schema_migrations`. The current migration set creates and seeds:

- `transaction_type_master`
- `category_master`
- `merchant_rule`
- `source_profile`
- `source_detection_rule`
- `source_column_mapping`
- `import_batch`
- `raw_import_row`
- `transaction_classification_audit`

Dashboard category and subcategory pickers read from `category_master`, not from historical transactions. Custom categories and subcategories saved in the dashboard are written back to DuckDB metadata.

## Build Desktop App

Desktop builds use PyInstaller. Build on the target operating system: create the Windows `.exe` on Windows, and create the macOS `.app` on macOS.

macOS:

```bash
conda activate finance
./scripts/build_macos.sh
```

Output:

```text
dist/Personal Finance.app
```

Windows PowerShell:

```powershell
conda activate finance
.\scripts\build_windows.ps1
```

Output:

```text
dist\PersonalFinance\PersonalFinance.exe
```

The packaged app starts with generic rules and an empty local database on each computer. The real `rules/admin_*.yml` files are not bundled; only the example templates are included.

## Generic vs Private Mode

The generic mode is safe to share: it uses source rules, merchant rules, and broad transaction logic.

Your private mode is enabled with `--admin`. It loads two ignored local files:

- `rules/admin_classification_rules.yml`: personalized classification rules such as your own names, friend reimbursements, Costco refund treatment, and PayPower reload patterns.
- `rules/admin_source_rules.yml`: personalized account labels and account-number aliases.

Shareable templates live at `rules/admin_classification_rules.example.yml` and `rules/admin_source_rules.example.yml`.

Use private mode for your real books:

```bash
python src/finance.py import --admin
python src/finance.py import --admin --dry-run
python src/finance.py refresh --admin
```

Use generic mode for a clean/public version:

```bash
python src/finance.py import
python src/finance.py refresh
```

Use one mode consistently per DuckDB file. Your personal database should use `--admin` for imports and refreshes; the generic mode is for a clean/public database.

## Dashboard

Run:

```bash
python src/finance.py dashboard --port 8502
```

Main pages:

- `Imports`: upload CSV/PDF statements, preview totals, and import into the local database.
- `Overview`: filtered gross spend, refunds/credits, personal net spend, income, reimbursements/paybacks, and excluded-from-spend movement.
- `Monthly Detail`: month-level category, subcategory, merchant, account, and transaction drilldowns.
- `Audit`: account-month and source-file tables for checking imported totals, with CSV download.
- `Drilldown`: choose a metric such as Excluded From Spend, Income, Internal Transfers, or Refunds/Credits and see the exact transactions behind it.
- `Review Queue`: fix ambiguous rows directly in the dashboard, including Type, Scope, Category, optional Subcategory, and reusable merchant rules.
- `Merchant Rules`: uncategorized queue plus flexible rule creation.
- `Transactions`: raw filtered transaction table plus a single-transaction editor.

Use the sidebar filters to check one Month, Account, Scope, or Type at a time. Scope defaults to `Personal`; switch a transaction to `Shared` from the `Review Queue` or `Transactions` page when needed.

Processed CSVs are renamed when they move into `imports/processed`, using the account label and the month containing the majority of transactions. Examples:

- `MBNA Apr 2026.csv`
- `RBC Avion Apr 2026.csv`
- `RBC ION Apr 2026.csv`
- `Scotiabank Apr 2026.csv`

## Configure Sources

Bank-specific CSV rules live in `rules/source_rules.yml`. Each source can define detection columns, transaction/posting date columns, merchant columns, amount columns, and generic account naming. Private account aliases live in `rules/admin_source_rules.yml` and are applied only with `--admin`.

Current statement mappings:

- `Apr2026_9426.csv` style files are detected as an MBNA credit card.
- `download-transactions.csv` style RBC exports are detected from `Account Type`, `Account Number`, `Description 1`, and `CAD$`; private aliases such as `RBC ION` or `RBC Avion` are applied only in `--admin` mode.
- `Scotia_Momentum_Visa_Infinite__Card_3128_050926.csv` style files are detected as a Scotia credit card.
- `Preferred_Package_9623_051026.csv` style files are detected as a Scotiabank bank account.
- `accountactivity*.csv` no-header Triangle exports are detected as Triangle account activity.
- `*Triangle-WorldEliteMastercard.pdf` PDF statements are parsed with `pdfplumber`.

Amounts are normalized so spending/outflows are positive and credits/payments are negative.

Transaction types shown in the app:

- `Expense`: real spending.
- `Refund`: merchant refund that reduces spending.
- `Merchant Credit`: statement credit or adjustment that reduces spending.
- `Card Payment`: payment made to a credit card; ignored for spending to avoid double counting.
- `Debt Payment`: cash leaving chequing to pay a card, loan, or line of credit; ignored for spending.
- `Internal Transfer`: movement between your own accounts; ignored for spending and income.
- `Reimbursement`: friend payback, pass-through purchase reimbursement, or merchant credit that should not be income.
- `Prepaid Card Reload`: large reload/top-up transaction, such as loading PayPower or another stored-value card; ignored for spending.
- `Needs Review`: ambiguous cash/e-transfer activity that needs a manual decision.
- `Income`: true inflow such as payroll, rent collected, interest, or tax refund.

For whole-person reporting, internal transfers are not income. They can still be useful for account-level cash flow, but they should not inflate total income or reduce spending.

## Configure Merchants

Merchant rules live in `rules/merchant_rules.yml`. You can edit the file directly or use the Streamlit `Merchant Rules` page to save new rules.

If you save a rule from the Streamlit `Merchant Rules` page, or save a transaction with `Save as merchant rule and apply to similar merchants` checked, the app refreshes existing rows for you. Rule matching checks the normal merchant text, a compact version, and a noise-stripped version, so one rule like `PHO ANH VU` can match variants such as `PHOANHVU`, `PHO_ANH_VU`, `PHO ANH VU 20260520`, and bank descriptions that include changing terminal or store numbers. A rule like `TIM HORTONS` can also match `TIM HORTONS 1218` or `TIM 1218 HORTONS`.

If you save a transaction without saving it as a merchant rule, the app treats that as a one-time manual decision. Future merchant-rule refreshes skip that row, so it does not keep returning to the review queue just because you chose not to create a reusable rule.

After changing transaction-type logic, reclassify existing DuckDB rows:

```bash
python src/finance.py refresh --admin
```

The dashboard `Merchant Rules` page supports custom categories and optional subcategories. Leave subcategory blank when it does not add useful detail.

If DuckDB says another app has a lock, close DBeaver or Streamlit and run the command again.

To remove pre-2026 transactions after import:

```sql
DELETE FROM transactions
WHERE transaction_date < DATE '2026-01-01';
```
