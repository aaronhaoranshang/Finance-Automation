# Credit Card Due

Credit Card Due is a compact, local-only desktop utility for tracking when
credit card statements are ready and when payment is required.

It follows a simple payment lifecycle:

- Before the next statement: **No payment required**
- After the expected statement date: a payment countdown appears
- After **Mark Paid**: the card stays paid until the next statement cycle

The app uses Python, PyQt6, and DuckDB. It does not connect to banks, read
email or PDFs, send notifications, use cloud sync, or run a web server.

## Requirements

- Python 3.11 or newer
- macOS, Windows, or Linux with PyQt6 support

## Install and run

From the `credit-card-widget` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\activate
```

## Add a card

Enter:

- **Card name**: a recognizable name such as `Travel Visa`
- **Statement day**: the day of the month the statement usually becomes
  available
- **Due day**: the official payment due day shown by the issuer
- **Pay early**: the number of days, from 0 to 15, before the official due
  date that the app recommends paying

Example:

- Statement day: 5
- Due day: 25
- Pay early: 7 days

For a July cycle, the statement is expected July 5, the official due date is
July 25, and the planning pay-by date is July 18.

If the due day is earlier than or equal to the statement day, the due date is
placed in the following month. For example, a July 25 statement with due day
15 is due August 15.

Days 29, 30, and 31 are clamped to the final day of shorter months without
changing the stored anchor day. A day-31 schedule returns to day 31 in months
that contain it.

## Understand the statuses

### No payment required

The next statement is not expected yet. The app displays the next expected
statement date and does not show a payment countdown.

### Payment due

The expected statement date has arrived. The app displays:

- the official projected due date
- the conservative pay-by planning date
- the number of days left, **Pay today**, or **Past pay-by**

### Paid

After **Mark Paid**, the card displays a green check, **Paid**, and
**No payment required**. The next statement date is shown, but no countdown
appears until that statement cycle starts. The success message also offers an
immediate **Undo** action.

## Edit or delete a card

Use **Edit** on a card to change its name, statement day, due day, or safety
buffer.

Use **Delete** to remove a card. The app asks for confirmation and then
soft-deactivates the card.

## Reset all data

Use **Reset all data** at the bottom of the app to remove all locally stored
cards, including sample cards. A confirmation dialog protects this action.

You can also reset from the command line:

```bash
python db.py --reset
```

## Optional sample data

The app never adds sample cards during normal launch. To add development
samples manually:

```bash
python db.py --seed
python app.py
```

The samples are clearly named:

- Sample Visa
- Sample Mastercard
- Sample Store Card

They can be deleted individually in the UI or removed with **Reset all data**
or `python db.py --reset`.

## Database location

By default, DuckDB data is stored in:

```text
credit-card-widget/cards.duckdb
```

To use another location, set `CREDIT_CARD_WIDGET_DB_PATH`:

```bash
export CREDIT_CARD_WIDGET_DB_PATH="$HOME/.credit-card-widget/cards.duckdb"
python app.py
```

The app recognizes older `credit_card_bills` demo schemas. Supported legacy
data is imported into the current `credit_cards` table, and the original
table is retained under a `credit_card_bills_legacy` backup name.

## Run tests

```bash
pytest
```

The tests focus on monthly date calculations, short months, payment
lifecycle transitions, duplicate prevention, deletion, reset, and undo.

## Project layout

```text
credit-card-widget/
├── app.py
├── db.py
├── ui.py
├── tests/
│   └── test_db.py
├── requirements.txt
└── README.md
```

## Disclaimer

This app is a local planning tool. Always verify payment due dates with your
official credit card statement or bank app.
