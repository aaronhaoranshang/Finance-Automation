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

These requirements apply only when running from source. A packaged macOS app
includes Python, PyQt6, DuckDB, and all native libraries. Recipients do not
need Terminal, Python, Homebrew, DuckDB, DBeaver, or development tools.

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

## Desktop widget mode

Open the `⋯` menu and enable **Desktop Widget Mode**. The window becomes a
frameless, translucent 360 × 520 card designed to sit near the edge of the
desktop. Use the same menu, or press **Command-Shift-W** on macOS
(**Control-Shift-W** on Windows/Linux), to return to normal app mode.

In widget mode:

- drag any non-button area of the card to move it
- enable **Lock Position** to prevent accidental dragging
- enable **Always on Top** to keep it above normal windows
- optionally try **Stay Behind Normal Windows** for a desktop-like layer
- choose a widget opacity of 70%, 85%, or 95%
- choose **Reset Position** if the card is moved off-screen
- right-click the widget or use `⋯` to open the controls and quit the app

Widget mode, position, lock state, window layer, and opacity persist between
launches. The app also checks that a saved position still intersects a
connected display before restoring it.

### macOS window limitations

The translucent surface uses Qt alpha compositing and has a glass-inspired
appearance. It does not use private macOS APIs or PyObjC, so it is not a true
live wallpaper blur.

`Qt.Tool` removes the widget from the normal application-window switcher on
macOS. The packaged app can still have a Dock icon because hiding that icon
dynamically while preserving normal app mode requires native AppKit lifecycle
handling. Similarly, **Stay Behind Normal Windows** uses Qt's
`WindowStaysOnBottomHint`; macOS may treat it differently across releases,
Spaces, and Mission Control. True wallpaper-level pinning and guaranteed
visibility on every Space are not available reliably through portable PyQt6
window flags.

## Build a clickable macOS app

Your friend does not need Python or Terminal if you send them a packaged app.
Build it on a Mac with:

```bash
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh
```

The build creates:

```text
dist/Credit Card Due.app
dist/Credit Card Due-macOS-Apple-Silicon.zip
```

The build also runs the packaged executable against a temporary DuckDB
database containing a card row. It stops before creating the ZIP if packaged
imports or database loading fail.

Send the ZIP matching the recipient's Mac:

- **Apple Silicon** for M1, M2, M3, M4, and later Apple chips
- **Intel** for older Intel-based Macs

Your friend can unzip it, drag **Credit Card Due** into Applications, and
double-click it. The app supports macOS 11 or later.

The current build is unsigned. On first launch, macOS Gatekeeper may require
the recipient to right-click the app and choose **Open**. Removing that warning
for general public distribution requires an Apple Developer certificate,
code signing, and notarization.

The build script automatically labels its ZIP for the Mac architecture on
which it runs. The included GitHub Actions workflow builds both Apple Silicon
and Intel packages on their native architectures.

### Signed and notarized releases

For warning-free public distribution, configure these environment variables
before building:

```text
APPLE_SIGNING_IDENTITY
APPLE_ID
APPLE_TEAM_ID
APPLE_APP_PASSWORD
```

The build signs through PyInstaller and, when all notarization credentials are
present, submits the ZIP to Apple's notary service and staples the approval to
the app. Never commit these credentials.

The GitHub Actions workflow can import a Developer ID certificate from
repository secrets and produce both architecture-specific artifacts. See
`.github/workflows/credit-card-widget-macos.yml`.

## Add a card

Open the `⋯` menu in the top-right corner and choose **Add a card**.

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

If **AutoPay / pre-authorized debit** is active for a card, the card shows a
green **AutoPay active** indicator. It still displays the official due date and
pay-by planning date as a manual fallback, but it is not treated as the next
manual payment in the summary. After the official due date passes, the app
rolls that card forward automatically to the next statement cycle.

This setting is entered by you. The app does not connect to your issuer or bank
to verify that the pre-authorized debit is actually active.

### Paid

After **Mark Paid**, the card displays a green check, **Paid**, and
**No payment required**. The next statement date is shown, but no countdown
appears until that statement cycle starts. The success message also offers an
immediate **Undo** action.

## Edit or delete a card

Use **Enable AutoPay** directly on a card to turn on the green check indicator.
Use **Disable AutoPay** if you later need manual reminders again.

Use **Edit** on a card to change its name, statement day, due day, safety
buffer, or pre-authorized debit setting.

Use **Delete** to remove a card. The app asks for confirmation and then
soft-deactivates the card.

## Reset all data

Open the top-right `⋯` menu and choose **Reset all data** to remove all locally
stored cards, including sample cards. A confirmation dialog protects this
action.

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

When running from source, DuckDB data is stored in:

```text
credit-card-widget/cards.duckdb
```

The packaged macOS app dynamically resolves the logged-in user's home folder
and stores that user's private database in:

```text
~/Library/Application Support/Credit Card Due/cards.duckdb
```

The database is not embedded in the app or shared with other users.
The app creates the folder automatically and applies owner-only permissions
on macOS. No source-machine username or absolute developer path is used at
runtime.

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
lifecycle transitions, duplicate prevention, deletion, reset, undo, settings
persistence, and desktop widget window-mode behavior.

## Project layout

```text
credit-card-widget/
├── app.py
├── db.py
├── settings.py
├── ui.py
├── packaging/
│   └── credit_card_widget.spec
├── scripts/
│   └── build_macos.sh
├── tests/
│   ├── test_db.py
│   ├── test_settings.py
│   └── test_widget_mode.py
├── requirements-build.txt
├── requirements.txt
└── README.md
```

## Disclaimer

This app is a local planning tool. Always verify payment due dates with your
official credit card statement or bank app.
