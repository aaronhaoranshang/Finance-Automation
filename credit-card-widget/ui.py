"""Polished PyQt6 interface for the Credit Card Due lifecycle tracker."""

from __future__ import annotations

from datetime import date
from functools import partial

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from db import (
    NO_PAYMENT_REQUIRED,
    PAID,
    PAYMENT_DUE,
    CreditCard,
    DatabaseError,
    add_card,
    days_until,
    delete_card,
    get_cards,
    mark_card_paid,
    reset_all_data,
    undo_last_paid,
    update_card,
)


APP_STYLESHEET = """
QMainWindow {
    background: #0f1116;
}
QWidget {
    color: #f5f7fb;
    font-family: "SF Pro Text", "Helvetica Neue", Arial;
    font-size: 13px;
}
QFrame#shell {
    background: #171a21;
    border: 1px solid #292e39;
    border-radius: 22px;
}
QFrame#summaryCard {
    background: #20242d;
    border: 1px solid #353c49;
    border-radius: 16px;
}
QFrame#summaryClear {
    background: #19241f;
    border: 1px solid #294537;
    border-radius: 16px;
}
QFrame#formCard {
    background: #1c2028;
    border: 1px solid #2b313c;
    border-radius: 16px;
}
QFrame#cardPanel {
    background: #21252e;
    border: 1px solid #303744;
    border-radius: 15px;
}
QLabel#title {
    font-size: 24px;
    font-weight: 700;
}
QLabel#subtitle, QLabel#helperText, QLabel#emptyText, QLabel#mutedText {
    color: #929bab;
}
QLabel#helperText, QLabel#emptyText {
    font-size: 12px;
}
QLabel#sectionTitle {
    color: #bbc3d0;
    font-size: 12px;
    font-weight: 700;
}
QLabel#summaryTitle {
    font-size: 17px;
    font-weight: 700;
}
QLabel#cardName {
    font-size: 15px;
    font-weight: 700;
}
QLabel#detailText {
    color: #a5adba;
    font-size: 12px;
}
QLabel#statusGreen {
    color: #61d995;
    font-weight: 700;
}
QLabel#statusNormal {
    color: #aa9cff;
    font-weight: 700;
}
QLabel#statusWarning {
    color: #ffca66;
    font-weight: 700;
}
QLabel#statusDanger {
    color: #ff737d;
    font-weight: 700;
}
QLabel#successMessage {
    color: #84dfaa;
    font-size: 12px;
}
QLineEdit, QSpinBox {
    background: #252a34;
    border: 1px solid #383f4d;
    border-radius: 10px;
    min-height: 38px;
    padding: 0 10px;
    selection-background-color: #7657ff;
}
QLineEdit:focus, QSpinBox:focus {
    border-color: #7d62ff;
}
QSpinBox::up-button, QSpinBox::down-button {
    border: 0;
    width: 20px;
    background: transparent;
}
QPushButton {
    background: #7657ff;
    border: 0;
    border-radius: 10px;
    color: white;
    font-weight: 700;
    min-height: 36px;
    padding: 0 14px;
}
QPushButton:hover {
    background: #876dff;
}
QPushButton:pressed {
    background: #6545ed;
}
QPushButton#secondaryButton {
    background: #2c323e;
    color: #dfe4ec;
    min-height: 30px;
    padding: 0 10px;
}
QPushButton#secondaryButton:hover {
    background: #39414f;
}
QPushButton#dangerButton {
    background: transparent;
    color: #e38a91;
    min-height: 30px;
    padding: 0 7px;
}
QPushButton#dangerButton:hover {
    background: #34252b;
    color: #ff9ca4;
}
QPushButton#linkButton {
    background: transparent;
    color: #aa9cff;
    min-height: 26px;
    padding: 0 5px;
}
QPushButton#linkButton:hover {
    color: #c5bcff;
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
QDialog {
    background: #171a21;
}
QMessageBox {
    background: #171a21;
}
"""


def _format_date(value: date | None) -> str:
    if value is None:
        return "Not available"
    return value.strftime("%b %d, %Y").replace(" 0", " ")


def _clear_layout(layout: QVBoxLayout | QHBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        child_layout = item.layout()
        widget = item.widget()
        if child_layout is not None:
            _clear_layout(child_layout)  # type: ignore[arg-type]
        if widget is not None:
            widget.deleteLater()


class EditCardDialog(QDialog):
    """Small editor for recurring card configuration."""

    def __init__(self, card: CreditCard, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Card")
        self.setModal(True)
        self.setMinimumWidth(350)
        self.setStyleSheet(APP_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        heading = QLabel("Edit credit card")
        heading.setObjectName("summaryTitle")
        layout.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(10)

        self.name_input = QLineEdit(card.card_name)
        self.statement_day_input = self._day_input(card.statement_day)
        self.due_day_input = self._day_input(card.due_day)
        self.buffer_input = QSpinBox()
        self.buffer_input.setRange(0, 15)
        self.buffer_input.setValue(card.safety_buffer_days)
        self.buffer_input.setSuffix(" days")

        form.addRow("Card name", self.name_input)
        form.addRow("Statement day", self.statement_day_input)
        form.addRow("Due day", self.due_day_input)
        form.addRow("Safety buffer", self.buffer_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _day_input(value: int) -> QSpinBox:
        input_widget = QSpinBox()
        input_widget.setRange(1, 31)
        input_widget.setValue(value)
        input_widget.setPrefix("Day ")
        return input_widget

    def values(self) -> tuple[str, int, int, int]:
        return (
            self.name_input.text(),
            self.statement_day_input.value(),
            self.due_day_input.value(),
            self.buffer_input.value(),
        )


class CreditCardWidget(QMainWindow):
    """Compact desktop utility for credit-card payment cycles."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Credit Card Due")
        self.setMinimumSize(420, 700)
        self.resize(450, 820)
        self.setMaximumWidth(480)
        self.setStyleSheet(APP_STYLESHEET)
        self.cards: list[CreditCard] = []

        self._build_ui()
        self.refresh_cards()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)

        shell = QFrame()
        shell.setObjectName("shell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(20, 20, 20, 18)
        shell_layout.setSpacing(14)

        title = QLabel("Credit Card Due")
        title.setObjectName("title")
        title.setFont(QFont(title.font().family(), 24, QFont.Weight.Bold))
        subtitle = QLabel(
            "Track when statements are ready and when payments are due."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        shell_layout.addWidget(title)
        shell_layout.addWidget(subtitle)

        self.summary_frame = QFrame()
        self.summary_layout = QVBoxLayout(self.summary_frame)
        self.summary_layout.setContentsMargins(15, 14, 15, 14)
        self.summary_layout.setSpacing(6)
        shell_layout.addWidget(self.summary_frame)

        form_card = self._build_add_form()
        shell_layout.addWidget(form_card)

        self.success_row = QWidget()
        success_layout = QHBoxLayout(self.success_row)
        success_layout.setContentsMargins(2, 0, 2, 0)
        success_layout.setSpacing(6)
        self.success_label = QLabel()
        self.success_label.setObjectName("successMessage")
        self.success_label.setWordWrap(True)
        self.undo_button = QPushButton("Undo")
        self.undo_button.setObjectName("linkButton")
        self.undo_button.hide()
        success_layout.addWidget(self.success_label, 1)
        success_layout.addWidget(self.undo_button)
        self.success_row.hide()
        shell_layout.addWidget(self.success_row)

        cards_heading = QLabel("YOUR CARDS")
        cards_heading.setObjectName("sectionTitle")
        shell_layout.addWidget(cards_heading)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 2, 0, 2)
        self.list_layout.setSpacing(10)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.list_container)
        shell_layout.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        reset_button = QPushButton("Reset all data")
        reset_button.setObjectName("dangerButton")
        reset_button.clicked.connect(self._reset_all_data)
        footer.addWidget(reset_button)
        shell_layout.addLayout(footer)

        root_layout.addWidget(shell)
        self.setCentralWidget(root)

    def _build_add_form(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("formCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(9)

        heading = QLabel("Add a card")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)

        self.card_name_input = QLineEdit()
        self.card_name_input.setPlaceholderText("Card name")
        self.card_name_input.setClearButtonEnabled(True)
        layout.addWidget(self.card_name_input)

        day_grid = QGridLayout()
        day_grid.setHorizontalSpacing(8)
        day_grid.setVerticalSpacing(5)

        statement_label = QLabel("Statement day")
        statement_label.setObjectName("helperText")
        due_label = QLabel("Due day")
        due_label.setObjectName("helperText")
        buffer_label = QLabel("Pay early")
        buffer_label.setObjectName("helperText")

        self.statement_day_input = self._day_input(5)
        self.due_day_input = self._day_input(25)
        self.buffer_input = QSpinBox()
        self.buffer_input.setRange(0, 15)
        self.buffer_input.setValue(7)
        self.buffer_input.setSuffix(" days")

        day_grid.addWidget(statement_label, 0, 0)
        day_grid.addWidget(due_label, 0, 1)
        day_grid.addWidget(buffer_label, 0, 2)
        day_grid.addWidget(self.statement_day_input, 1, 0)
        day_grid.addWidget(self.due_day_input, 1, 1)
        day_grid.addWidget(self.buffer_input, 1, 2)
        layout.addLayout(day_grid)

        helper = QLabel(
            "Statement day is when your statement usually becomes available.\n"
            "Due day is the official payment due day. Pay-by is a conservative "
            "planning date before it."
        )
        helper.setObjectName("helperText")
        helper.setWordWrap(True)
        layout.addWidget(helper)

        add_button = QPushButton("Add Card")
        add_button.clicked.connect(self.add_new_card)
        layout.addWidget(add_button)
        self.card_name_input.returnPressed.connect(self.add_new_card)
        return frame

    @staticmethod
    def _day_input(value: int) -> QSpinBox:
        input_widget = QSpinBox()
        input_widget.setRange(1, 31)
        input_widget.setValue(value)
        input_widget.setPrefix("Day ")
        input_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        return input_widget

    def add_new_card(self) -> None:
        card_name = self.card_name_input.text()
        try:
            add_card(
                card_name,
                self.statement_day_input.value(),
                self.due_day_input.value(),
                self.buffer_input.value(),
            )
        except (ValueError, DatabaseError) as exc:
            self._show_error(str(exc))
            return

        cleaned_name = " ".join(card_name.split())
        self.card_name_input.clear()
        self.card_name_input.setFocus()
        self._show_success(f"Added {cleaned_name}.")
        self.refresh_cards()

    def refresh_cards(self) -> None:
        try:
            self.cards = get_cards()
        except (ValueError, DatabaseError) as exc:
            self._show_error(str(exc))
            return
        self._render_summary()
        self._render_cards()

    def _render_summary(self) -> None:
        _clear_layout(self.summary_layout)
        due_cards = [
            card
            for card in self.cards
            if card.status == PAYMENT_DUE and card.pay_by_date is not None
        ]
        if not due_cards:
            self.summary_frame.setObjectName("summaryClear")
            self.summary_frame.style().unpolish(self.summary_frame)
            self.summary_frame.style().polish(self.summary_frame)

            title = QLabel("✓ No payment required")
            title.setObjectName("statusGreen")
            title.setFont(
                QFont(title.font().family(), 16, QFont.Weight.Bold)
            )
            detail = QLabel(
                "All cards are paid or waiting for the next statement."
            )
            detail.setObjectName("mutedText")
            detail.setWordWrap(True)
            self.summary_layout.addWidget(title)
            self.summary_layout.addWidget(detail)
            return

        urgent = min(
            due_cards,
            key=lambda card: (
                card.pay_by_date or date.max,
                card.current_due_date or date.max,
            ),
        )
        self.summary_frame.setObjectName("summaryCard")
        self.summary_frame.style().unpolish(self.summary_frame)
        self.summary_frame.style().polish(self.summary_frame)

        eyebrow = QLabel("NEXT PAYMENT")
        eyebrow.setObjectName("sectionTitle")
        name = QLabel(urgent.card_name)
        name.setObjectName("summaryTitle")
        status = QLabel(self._payment_status_text(urgent))
        status.setObjectName(self._payment_status_style(urgent))
        dates = QLabel(
            f"Pay by {_format_date(urgent.pay_by_date)}  ·  "
            f"Due {_format_date(urgent.current_due_date)}"
        )
        dates.setObjectName("detailText")
        dates.setWordWrap(True)
        paid_button = QPushButton("Mark Paid")
        paid_button.clicked.connect(partial(self._mark_paid, urgent.id))

        self.summary_layout.addWidget(eyebrow)
        self.summary_layout.addWidget(name)
        self.summary_layout.addWidget(status)
        self.summary_layout.addWidget(dates)
        self.summary_layout.addWidget(paid_button)

    def _render_cards(self) -> None:
        _clear_layout(self.list_layout)
        if not self.cards:
            title = QLabel("No cards yet.")
            title.setObjectName("summaryTitle")
            detail = QLabel(
                "Add your statement and due-day information once. "
                "The app will roll it forward monthly."
            )
            detail.setObjectName("emptyText")
            detail.setWordWrap(True)
            self.list_layout.addWidget(title)
            self.list_layout.addWidget(detail)
            self.list_layout.addStretch(1)
            return

        for card in self.cards:
            self.list_layout.addWidget(self._create_card_panel(card))
        self.list_layout.addStretch(1)

    def _create_card_panel(self, card: CreditCard) -> QFrame:
        panel = QFrame()
        panel.setObjectName("cardPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 12, 11)
        layout.setSpacing(5)

        header = QHBoxLayout()
        name = QLabel(card.card_name)
        name.setObjectName("cardName")
        status = QLabel(self._card_status_title(card))
        status.setObjectName(self._card_status_style(card))
        header.addWidget(name, 1)
        header.addWidget(status)
        layout.addLayout(header)

        if card.status == PAYMENT_DUE:
            countdown = QLabel(self._payment_status_text(card))
            countdown.setObjectName(self._payment_status_style(card))
            due = QLabel(f"Official due date: {_format_date(card.current_due_date)}")
            due.setObjectName("detailText")
            pay_by = QLabel(
                f"Pay-by planning date: {_format_date(card.pay_by_date)}"
            )
            pay_by.setObjectName("detailText")
            layout.addWidget(countdown)
            layout.addWidget(due)
            layout.addWidget(pay_by)
        else:
            if card.status == PAID:
                paid = QLabel("No payment required")
                paid.setObjectName("statusGreen")
                layout.addWidget(paid)
            next_statement = QLabel(
                "Next statement expected: "
                f"{_format_date(card.current_statement_date)}"
            )
            next_statement.setObjectName("detailText")
            layout.addWidget(next_statement)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        if card.status == PAYMENT_DUE:
            paid_button = QPushButton("Mark Paid")
            paid_button.clicked.connect(partial(self._mark_paid, card.id))
            actions.addWidget(paid_button)
        actions.addStretch(1)

        edit_button = QPushButton("Edit")
        edit_button.setObjectName("secondaryButton")
        edit_button.clicked.connect(partial(self._edit_card, card))
        delete_button = QPushButton("Delete")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(partial(self._delete_card, card))
        actions.addWidget(edit_button)
        actions.addWidget(delete_button)
        layout.addLayout(actions)
        return panel

    @staticmethod
    def _card_status_title(card: CreditCard) -> str:
        if card.status == PAID:
            return "✓ Paid"
        if card.status == NO_PAYMENT_REQUIRED:
            return "✓ No payment required"
        return "Payment due"

    @staticmethod
    def _card_status_style(card: CreditCard) -> str:
        if card.status in {PAID, NO_PAYMENT_REQUIRED}:
            return "statusGreen"
        return CreditCardWidget._payment_status_style(card)

    @staticmethod
    def _payment_status_text(card: CreditCard) -> str:
        if card.pay_by_date is None:
            return "Payment due"
        remaining = days_until(card.pay_by_date)
        if remaining < 0:
            overdue_days = abs(remaining)
            suffix = "day" if overdue_days == 1 else "days"
            return f"Past pay-by by {overdue_days} {suffix}"
        if remaining == 0:
            return "Pay today"
        suffix = "day" if remaining == 1 else "days"
        return f"{remaining} {suffix} left"

    @staticmethod
    def _payment_status_style(card: CreditCard) -> str:
        if card.pay_by_date is None:
            return "statusNormal"
        remaining = days_until(card.pay_by_date)
        if remaining < 0:
            return "statusDanger"
        if remaining <= 3:
            return "statusWarning"
        return "statusNormal"

    def _mark_paid(self, card_id: int) -> None:
        try:
            mark_card_paid(card_id)
        except (ValueError, DatabaseError) as exc:
            self._show_error(str(exc))
            return
        self._show_success(
            "Marked paid. No payment required until the next statement.",
            undo_card_id=card_id,
        )
        self.refresh_cards()

    def _undo_paid(self, card_id: int) -> None:
        try:
            undo_last_paid(card_id)
        except (ValueError, DatabaseError) as exc:
            self._show_error(str(exc))
            return
        self._show_success("Payment status restored.")
        self.refresh_cards()

    def _edit_card(self, card: CreditCard) -> None:
        dialog = EditCardDialog(card, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        card_name, statement_day, due_day, buffer_days = dialog.values()
        try:
            update_card(
                card.id,
                card_name,
                statement_day,
                due_day,
                buffer_days,
            )
        except (ValueError, DatabaseError) as exc:
            self._show_error(str(exc))
            return
        cleaned_name = " ".join(card_name.split())
        self._show_success(f"Updated {cleaned_name}.")
        self.refresh_cards()

    def _delete_card(self, card: CreditCard) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Delete Card")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("Delete this card? This cannot be undone.")
        box.setInformativeText(card.card_name)
        delete_button = box.addButton(
            "Delete Card",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not delete_button:
            return
        try:
            delete_card(card.id)
        except (ValueError, DatabaseError) as exc:
            self._show_error(str(exc))
            return
        self._show_success(f"Deleted {card.card_name}.")
        self.refresh_cards()

    def _reset_all_data(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Reset All Data")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(
            "Reset all cards? This removes all locally stored cards, "
            "including sample cards."
        )
        reset_button = box.addButton(
            "Reset All Data",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not reset_button:
            return
        try:
            reset_all_data()
        except DatabaseError as exc:
            self._show_error(str(exc))
            return
        self._show_success("All data reset.")
        self.refresh_cards()

    def _show_success(
        self,
        message: str,
        *,
        undo_card_id: int | None = None,
    ) -> None:
        self.success_label.setText(message)
        try:
            self.undo_button.clicked.disconnect()
        except TypeError:
            pass
        if undo_card_id is None:
            self.undo_button.hide()
        else:
            self.undo_button.show()
            self.undo_button.clicked.connect(
                partial(self._undo_paid, undo_card_id)
            )
        self.success_row.show()

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(
            self,
            "Something went wrong",
            f"The card database could not be updated.\n\n{message}",
        )
