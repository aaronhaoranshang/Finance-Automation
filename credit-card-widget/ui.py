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
    CreditCard,
    DatabaseError,
    add_card,
    get_cards,
    mark_card_paid,
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
QFrame#cardPanel {
    background: #222630;
    border: 1px solid #303642;
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
QLabel#daysPastPayBy {
    color: #ff737d;
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
    """Compact main window for tracking recurring credit card due dates."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Credit Card Due")
        self.setMinimumSize(380, 560)
        self.resize(380, 680)
        self.setMaximumWidth(420)
        self.setStyleSheet(APP_STYLESHEET)

        self._build_ui()
        self.refresh_cards()

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
        self.card_name_input.returnPressed.connect(self.add_new_card)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)

        due_date_group = QVBoxLayout()
        due_date_group.setSpacing(5)

        due_date_label = QLabel("Current statement due date")
        due_date_label.setObjectName("sectionTitle")

        self.due_date_input = QDateEdit()
        self.due_date_input.setCalendarPopup(True)
        self.due_date_input.setDisplayFormat("MMM d, yyyy")
        self.due_date_input.setMinimumDate(QDate.currentDate())
        self.due_date_input.setDate(QDate.currentDate().addDays(14))
        self.due_date_input.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        due_date_group.addWidget(due_date_label)
        due_date_group.addWidget(self.due_date_input)

        add_button = QPushButton("Add")
        add_button.clicked.connect(self.add_new_card)

        add_row.addLayout(due_date_group, 1)
        add_row.addWidget(add_button, 0, Qt.AlignmentFlag.AlignBottom)

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

    def add_new_card(self) -> None:
        card_name = self.card_name_input.text().strip()
        due_date = self.due_date_input.date()

        if not card_name:
            self._show_warning("Card name cannot be empty.")
            self.card_name_input.setFocus()
            return
        if not due_date.isValid():
            self._show_warning("Please select a valid statement due date.")
            return
        try:
            add_card(card_name, due_date.toPyDate())
        except (ValueError, DatabaseError) as exc:
            self._show_error(str(exc))
            return

        self.card_name_input.clear()
        self.card_name_input.setFocus()
        self.refresh_cards()

    def refresh_cards(self) -> None:
        self._clear_card_list()
        try:
            cards = get_cards()
        except DatabaseError as exc:
            self._show_error(str(exc))
            return

        unpaid_heading = QLabel(f"MONTHLY CARDS  ·  {len(cards)}")
        unpaid_heading.setObjectName("sectionTitle")
        self.list_layout.addWidget(unpaid_heading)

        if cards:
            for card in cards:
                self.list_layout.addWidget(self._create_card(card))
        else:
            self.list_layout.addWidget(
                self._empty_label("No cards yet. Add one current due date above.")
            )

        self.list_layout.addStretch(1)

    def _create_card(self, credit_card: CreditCard) -> QFrame:
        card = QFrame()
        card.setObjectName("cardPanel")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 12, 12)
        layout.setSpacing(8)

        details = QVBoxLayout()
        details.setSpacing(3)

        name = QLabel(credit_card.card_name)
        name.setObjectName("cardName")
        pay_by = QLabel(
            f"Pay by {credit_card.pay_by_date.strftime('%b %d, %Y')}"
        )
        pay_by.setObjectName("dueDate")

        days_left = (credit_card.pay_by_date - date.today()).days
        status = QLabel(self._pay_by_status_text(days_left))
        if days_left < 0:
            status.setObjectName("daysPastPayBy")
        elif days_left == 0:
            status.setObjectName("daysToday")
        else:
            status.setObjectName("daysNormal")

        details.addWidget(name)
        details.addWidget(pay_by)
        details.addWidget(status)

        paid_button = QPushButton("Mark paid")
        paid_button.setObjectName("paidButton")
        paid_button.clicked.connect(partial(self._mark_paid, credit_card.id))

        layout.addLayout(details, 1)
        layout.addWidget(paid_button, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _mark_paid(self, card_id: int) -> None:
        try:
            mark_card_paid(card_id)
        except (ValueError, DatabaseError) as exc:
            self._show_error(str(exc))
            return
        self.refresh_cards()

    def _clear_card_list(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def _pay_by_status_text(days_left: int) -> str:
        if days_left == 0:
            return "Pay today"
        if days_left < 0:
            past_days = abs(days_left)
            suffix = "day" if past_days == 1 else "days"
            return f"{past_days} {suffix} past pay-by"
        suffix = "day" if days_left == 1 else "days"
        return f"{days_left} {suffix} until pay-by"

    @staticmethod
    def _empty_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("emptyLabel")
        label.setWordWrap(True)
        label.setContentsMargins(4, 8, 4, 10)
        return label

    def _show_warning(self, message: str) -> None:
        QMessageBox.warning(self, "Check the card", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(
            self,
            "Something went wrong",
            f"The card database could not be updated.\n\n{message}",
        )
