"""Application entry point for Credit Card Due."""

import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from db import DatabaseError, get_cards, init_db
from ui import CreditCardWidget


def run_smoke_test() -> int:
    """Exercise packaged database initialization without opening a window."""
    try:
        init_db()
        get_cards()
    except Exception:
        return 1
    return 0


def main() -> int:
    if "--smoke-test" in sys.argv:
        return run_smoke_test()

    app = QApplication(sys.argv)
    app.setApplicationName("Credit Card Due")
    app.setOrganizationName("Credit Card Widget")

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
