# Credit Card Due

A compact macOS desktop app for tracking recurring monthly credit card
payment due dates. Data stays local in a DuckDB file; there are no bank
connections, email integrations, notifications, or web services.

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
runs. If the database file is missing, it is recreated automatically. An
existing database from the original one-time bill version is migrated
automatically while preserving its cards.

## Use the app

1. Enter a card name.
2. Enter the exact due date from its current statement once.
3. Click **Add**.
4. Click **Mark paid** when the payment is complete.

The app uses that first date as a monthly anchor. It displays one conservative
**Pay by** date exactly seven days before the projected due date. Marking a
card paid records the payment time, advances the projection by one month, and
immediately resets the card for the next billing cycle.

For due days 29-31, a shorter month uses its final calendar day. The original
monthly due day is retained, so a card configured for day 31 returns to day 31
in a later month that has one. Future dates are always calculated from that
stored anchor day, so short months do not cause cumulative drift.

The Canadian Bank Act guarantees at least 21 days between the end of a billing
cycle and the minimum-payment due date, but it does not guarantee that an
offline app can know every future statement date. The seven-day buffer is a
conservative planning aid, not a replacement for the date on a bank statement
or automatic payments.

## Add sample cards

With the virtual environment active, run:

```bash
python db.py --seed
python app.py
```

This adds three example recurring cards anchored to upcoming dates. Running
the seed command again skips exact duplicate card/anchor-day pairs.

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
