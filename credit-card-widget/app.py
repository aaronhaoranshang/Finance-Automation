"""Application entry point for Credit Card Due."""

import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from db import DatabaseError, initialize_database
from ui import CreditCardWidget


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Credit Card Due")
    app.setOrganizationName("Credit Card Widget")

    try:
        initialize_database()
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
