# Data Model

The app separates money movement from spending purpose.

## Core Transaction Fields

`transactions` stores one normalized row per transaction:

- `transaction_id`: deterministic unique ID used for duplicate prevention.
- `transaction_date`: date used for dashboards.
- `posted_date`: posted date when available.
- `institution`: bank/card/provider.
- `account_name`: normalized account label.
- `merchant_raw`: original merchant/description text.
- `merchant_clean`: display merchant name.
- `amount`: normalized amount.
- `transaction_type`: nature of the money movement.
- `scope`: personal/shared.
- `category`: spending purpose.
- `subcategory`: optional spending purpose detail.
- `source_file`: imported filename.
- `ingested_at`: import timestamp.

## Transaction Type

`transaction_type` describes what kind of movement happened.

Examples:

- `expense`: real spending.
- `refund`: refund that reduces spending.
- `income`: true income such as payroll or interest.
- `payment`: credit card payment shown on a card statement.
- `debt_payment`: bank account outflow to pay a card, loan, or line of credit.
- `transfer`: movement between owned accounts.
- `reimbursement`: money paid back to you.
- `stored_value_reload`: prepaid or stored-value reload.
- `manual_review`: ambiguous transaction.

Transaction type behavior is configured in `transaction_type_master`.

## Category And Subcategory

`category` and `subcategory` describe spending purpose only.

Valid examples:

- `Food / Coffee`
- `Food / Groceries`
- `Travel / Flights`
- `Shopping / Household`

Invalid examples:

- `Debt Payment / Credit Card Payment`
- `Transfer / Internal Transfer`
- `Income / Salary`

Those are transaction types or movement labels, not spending purposes.

Category options come from `category_master`; they are not inferred from historical transactions.

## Rules

`merchant_rule` stores default and user rules. User rules override default rules. A rule can assign:

- merchant display name
- transaction type
- scope
- category
- subcategory

Rules are validated against `transaction_type_master` and `category_master`.

## Import Audit

`import_batch` stores file-level import status. `raw_import_row` stores raw row JSON and row-level status:

- `inserted`
- `duplicate`
- `failed`
- `skipped`
- `pending`

`transaction_classification_audit` records classification changes and rule matches.
