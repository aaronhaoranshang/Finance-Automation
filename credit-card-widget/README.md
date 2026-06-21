# Credit Card Due

A compact macOS desktop app for manually tracking credit card payment due
dates. Data stays local in a DuckDB file; there are no bank connections,
email integrations, notifications, or web services.

## Requirements

- Python 3.11 or newer
- macOS (the app can also run anywhere PyQt6 is supported)

## Install and run

From the `credit-card-widget` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The app creates `cards.duckdb` beside the Python files the first time it
runs. If the database file is missing, it is recreated automatically.

## Use the app

1. Enter a card name.
2. Choose its payment due date.
3. Click **Add**.
4. Click **Mark paid** when the payment is complete.

Unpaid bills are sorted by due date. Paid bills are shown in a separate,
greyed-out section and can be moved back with **Undo**.

## Add sample cards

With the virtual environment active, run:

```bash
python db.py --seed
python app.py
```

This adds three example cards with dates relative to today. Running the seed
command again skips exact duplicate card/date pairs.

## Project layout

```text
credit-card-widget/
├── .gitignore       # ignores local data and environment files
├── app.py           # application entry point
├── db.py            # DuckDB schema and data operations
├── ui.py            # PyQt6 interface
├── requirements.txt
└── README.md
```
