# Import Pipeline

The import pipeline is built to be auditable and safe.

## Steps

1. User uploads or drops a CSV/PDF into the import flow.
2. App computes a file hash.
3. App creates an `import_batch`.
4. Every raw row is stored in `raw_import_row` as JSON.
5. SQL source detection chooses a `source_profile`.
6. SQL column mappings normalize the raw statement fields.
7. Transaction IDs are generated deterministically.
8. Merchant rules classify transactions.
9. New transactions are inserted.
10. Duplicate rows are marked as `duplicate`.
11. Failed rows keep their error messages.
12. File moves to `processed/` or `failed/`.

## Source Detection

Source detection reads `source_detection_rule` ordered by priority. It can match by:

- required columns
- optional columns
- filename pattern
- header pattern
- column value rules

Missing required columns fail clearly.

## Column Mapping

`source_column_mapping` maps source-specific columns into normalized target fields such as:

- `transaction_date`
- `posted_date`
- `merchant_raw`
- `amount`
- `debit_amount`
- `credit_amount`
- `account_name`
- `account_type`

Supported transform rules include:

- `parse_date`
- `parse_amount`
- `credit_card_sign`
- `debit_credit_split`
- `clean_text`

Invalid dates and missing required amounts fail import instead of becoming silent zeroes.

## Duplicate Tracking

Duplicates are tracked per incoming row. Re-importing the same file creates a new `import_batch`, but rows whose deterministic `transaction_id` already exists are marked `duplicate` and are not inserted again.

## Reclassification

Rule changes do not silently mutate historical data. Users can run a reclassification dry run, inspect proposed changes, and then apply. Applied changes are written to `transaction_classification_audit`.
