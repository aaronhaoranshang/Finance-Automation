"""Application entry point for Credit Card Due."""

import os
import sys
from datetime import date

from PyQt6.QtWidgets import QApplication, QMessageBox

from db import DatabaseError, add_card, get_cards, init_db
from settings import APPLICATION_NAME, ORGANIZATION_NAME
from ui import CreditCardWidget


def run_smoke_test() -> int:
    """Exercise packaged database initialization without opening a window."""
    try:
        init_db()
        cards = get_cards()
        if os.environ.get("CREDIT_CARD_WIDGET_SMOKE_SEED") == "1" and not cards:
            today = date.today()
            add_card(
                "Packaging Smoke Test",
                today.day,
                6 if today.day >= 6 else 25,
                5,
                today=today,
            )
            cards = get_cards()
            if not cards:
                return 1
    except Exception:
        return 1
    return 0


def main() -> int:
    if "--smoke-test" in sys.argv:
        return run_smoke_test()

    app = QApplication(sys.argv)
    app.setApplicationName(APPLICATION_NAME)
    app.setOrganizationName(ORGANIZATION_NAME)

    try:
        init_db()
    except DatabaseError as exc:
        QMessageBox.critical(
            None,
            "Database error",
            f"Credit Card Due could not initialize its local database.\n\n{exc}",
        )
        return 1

    window = CreditCardWidget()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
