"""PyQt6 user interface for Credit Card Due."""

from __future__ import annotations

from datetime import date
from functools import partial

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from db import (
    CreditCardBill,
    DatabaseError,
    add_bill,
    get_bills,
    mark_bill_paid,
    mark_bill_unpaid,
)


APP_STYLESHEET = """
QMainWindow {
    background: #111318;
}
QWidget {
    color: #f5f7fb;
    font-family: "SF Pro Text", "Helvetica Neue", Arial;
    font-size: 13px;
}
QFrame#shell {
    background: #181b22;
    border: 1px solid #292e39;
    border-radius: 22px;
}
QLabel#title {
    font-size: 24px;
    font-weight: 700;
}
QLabel#subtitle, QLabel#emptyLabel {
    color: #8f98a8;
}
QLabel#sectionTitle {
    color: #b9c1ce;
    font-size: 12px;
    font-weight: 700;
}
QLineEdit, QDateEdit {
    background: #222630;
    border: 1px solid #343a47;
    border-radius: 10px;
    min-height: 38px;
    padding: 0 10px;
    selection-background-color: #7657ff;
}
QLineEdit:focus, QDateEdit:focus {
    border-color: #7657ff;
}
QDateEdit::drop-down {
    border: 0;
    width: 24px;
}
QPushButton {
    background: #7657ff;
    border: 0;
    border-radius: 10px;
    color: white;
    font-weight: 700;
    min-height: 38px;
    padding: 0 14px;
}
QPushButton:hover {
    background: #876dff;
}
QPushButton:pressed {
    background: #6545ed;
}
QPushButton#paidButton {
    background: #2a303b;
    color: #dce2ec;
    min-height: 30px;
    padding: 0 10px;
}
QPushButton#paidButton:hover {
    background: #363e4b;
}
QPushButton#restoreButton {
    background: transparent;
    color: #8f98a8;
    min-height: 26px;
    padding: 0 6px;
}
QPushButton#restoreButton:hover {
    color: #dce2ec;
}
QFrame#billCard {
    background: #222630;
    border: 1px solid #303642;
    border-radius: 14px;
}
QFrame#paidCard {
    background: #1d2027;
    border: 1px solid #292e37;
    border-radius: 14px;
}
QLabel#cardName {
    font-size: 14px;
    font-weight: 700;
}
QLabel#dueDate {
    color: #9ba4b3;
    font-size: 12px;
}
QLabel#daysNormal {
    color: #a998ff;
    font-weight: 700;
}
QLabel#daysToday {
    color: #ffcc66;
    font-weight: 700;
}
QLabel#daysOverdue {
    color: #ff737d;
    font-weight: 700;
}
QLabel#paidText, QLabel#paidCardName {
    color: #737c8b;
}
QLabel#paidCardName {
    font-weight: 700;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: 0;
}
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 4px 0;
}
QScrollBar::handle:vertical {
    background: #3b4250;
    border-radius: 3px;
    min-height: 28px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


class CreditCardWidget(QMainWindow):
    """Compact main window for adding and tracking card bills."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Credit Card Due")
        self.setMinimumSize(380, 560)
        self.resize(380, 680)
        self.setMaximumWidth(420)
        self.setStyleSheet(APP_STYLESHEET)

        self._build_ui()
        self.refresh_bills()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)

        shell = QFrame()
        shell.setObjectName("shell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(20, 20, 20, 20)
        shell_layout.setSpacing(14)

        title = QLabel("Credit Card Due")
        title.setObjectName("title")
        title.setFont(QFont(title.font().family(), 24, QFont.Weight.Bold))
        subtitle = QLabel("Keep payment dates in sight.")
        subtitle.setObjectName("subtitle")

        shell_layout.addWidget(title)
        shell_layout.addWidget(subtitle)

        self.card_name_input = QLineEdit()
        self.card_name_input.setPlaceholderText("Card name")
        self.card_name_input.setClearButtonEnabled(True)
        self.card_name_input.returnPressed.connect(self.add_new_bill)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)

        self.due_date_input = QDateEdit()
        self.due_date_input.setCalendarPopup(True)
        self.due_date_input.setDisplayFormat("MMM d, yyyy")
        self.due_date_input.setDate(QDate.currentDate().addDays(7))
        self.due_date_input.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        add_button = QPushButton("Add")
        add_button.clicked.connect(self.add_new_bill)

        add_row.addWidget(self.due_date_input, 1)
        add_row.addWidget(add_button)

        shell_layout.addWidget(self.card_name_input)
        shell_layout.addLayout(add_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 4, 0, 4)
        self.list_layout.setSpacing(10)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.list_container)

        shell_layout.addWidget(scroll, 1)
        root_layout.addWidget(shell)
        self.setCentralWidget(root)

    def add_new_bill(self) -> None:
        card_name = self.card_name_input.text().strip()
        selected_date = self.due_date_input.date()

        if not card_name:
            self._show_warning("Card name cannot be empty.")
            self.card_name_input.setFocus()
            return
        if not selected_date.isValid():
            self._show_warning("Please select a valid due date.")
            return

        try:
            add_bill(card_name, selected_date.toPyDate())
        except (ValueError, DatabaseError) as exc:
            self._show_error(str(exc))
            return

        self.card_name_input.clear()
        self.card_name_input.setFocus()
        self.refresh_bills()

    def refresh_bills(self) -> None:
        self._clear_bill_list()
        try:
            unpaid_bills = get_bills(is_paid=False)
            paid_bills = get_bills(is_paid=True)
        except DatabaseError as exc:
            self._show_error(str(exc))
            return

        unpaid_heading = QLabel(f"UPCOMING  ·  {len(unpaid_bills)}")
        unpaid_heading.setObjectName("sectionTitle")
        self.list_layout.addWidget(unpaid_heading)

        if unpaid_bills:
            for bill in unpaid_bills:
                self.list_layout.addWidget(self._create_unpaid_card(bill))
        else:
            self.list_layout.addWidget(
                self._empty_label("No unpaid bills. A pleasantly quiet list.")
            )

        paid_heading = QLabel(f"PAID  ·  {len(paid_bills)}")
        paid_heading.setObjectName("sectionTitle")
        paid_heading.setContentsMargins(0, 8, 0, 0)
        self.list_layout.addWidget(paid_heading)

        if paid_bills:
            for bill in paid_bills:
                self.list_layout.addWidget(self._create_paid_card(bill))
        else:
            self.list_layout.addWidget(self._empty_label("Paid bills will appear here."))

        self.list_layout.addStretch(1)

    def _create_unpaid_card(self, bill: CreditCardBill) -> QFrame:
        card = QFrame()
        card.setObjectName("billCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 12, 12)
        layout.setSpacing(8)

        details = QVBoxLayout()
        details.setSpacing(3)

        name = QLabel(bill.card_name)
        name.setObjectName("cardName")
        due_date = QLabel(f"Due {bill.due_date.strftime('%b %d, %Y')}")
        due_date.setObjectName("dueDate")

        days_left = (bill.due_date - date.today()).days
        status = QLabel(self._days_remaining_text(days_left))
        if days_left < 0:
            status.setObjectName("daysOverdue")
        elif days_left == 0:
            status.setObjectName("daysToday")
        else:
            status.setObjectName("daysNormal")

        details.addWidget(name)
        details.addWidget(due_date)
        details.addWidget(status)

        paid_button = QPushButton("Mark paid")
        paid_button.setObjectName("paidButton")
        paid_button.clicked.connect(partial(self._mark_paid, bill.id))

        layout.addLayout(details, 1)
        layout.addWidget(paid_button, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _create_paid_card(self, bill: CreditCardBill) -> QFrame:
        card = QFrame()
        card.setObjectName("paidCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 10, 10, 10)

        details = QVBoxLayout()
        details.setSpacing(2)

        name = QLabel(bill.card_name)
        name.setObjectName("paidCardName")
        paid_text = QLabel(f"Due {bill.due_date.strftime('%b %d, %Y')}  ·  Paid")
        paid_text.setObjectName("paidText")

        details.addWidget(name)
        details.addWidget(paid_text)

        restore_button = QPushButton("Undo")
        restore_button.setObjectName("restoreButton")
        restore_button.clicked.connect(partial(self._mark_unpaid, bill.id))

        layout.addLayout(details, 1)
        layout.addWidget(restore_button, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _mark_paid(self, bill_id: int) -> None:
        try:
            mark_bill_paid(bill_id)
        except DatabaseError as exc:
            self._show_error(str(exc))
            return
        self.refresh_bills()

    def _mark_unpaid(self, bill_id: int) -> None:
        try:
            mark_bill_unpaid(bill_id)
        except DatabaseError as exc:
            self._show_error(str(exc))
            return
        self.refresh_bills()

    def _clear_bill_list(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def _days_remaining_text(days_left: int) -> str:
        if days_left == 0:
            return "Due today"
        if days_left < 0:
            overdue_days = abs(days_left)
            suffix = "day" if overdue_days == 1 else "days"
            return f"Overdue by {overdue_days} {suffix}"
        suffix = "day" if days_left == 1 else "days"
        return f"{days_left} {suffix} remaining"

    @staticmethod
    def _empty_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("emptyLabel")
        label.setWordWrap(True)
        label.setContentsMargins(4, 8, 4, 10)
        return label

    def _show_warning(self, message: str) -> None:
        QMessageBox.warning(self, "Check the bill", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(
            self,
            "Something went wrong",
            f"The bill database could not be updated.\n\n{message}",
        )
