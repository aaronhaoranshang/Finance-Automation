# Privacy

Personal Finance Automation is designed as a local-first finance app.

## What Stays Local

- Your financial data stays on your device.
- Statements are imported from files you choose, such as CSV or PDF exports.
- The app stores normalized transactions, rules, categories, and audit rows in a local DuckDB database.
- Backups are files you create and control.

## What The App Does Not Do

- No cloud sync is enabled by default.
- No bank login credentials are collected.
- No online banking scraping is performed.
- No statement data is sent to an external service by the core app.
- No subscription account is required for the local app.

## Local Files

Development installs store data under `personal-finance/data/` by default. Packaged desktop installs use the operating system's application data folder:

- macOS: `~/Library/Application Support/Personal Finance Automation`
- Windows: `%LOCALAPPDATA%\Personal Finance Automation`

You can override the folder with `PERSONAL_FINANCE_HOME`.

## Backups

The Settings page can export a backup zip containing the local DuckDB database and helpful metadata exports. Restoring a backup replaces the current local database, and the app creates a rollback backup first when possible.

## Future Paid App Boundary

Licensing, payments, and optional sync are intentionally out of scope for the current local app. If those are added later, they should be separate from transaction storage and should not require uploading statement data.
