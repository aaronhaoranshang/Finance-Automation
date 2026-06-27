"""Polished PyQt6 interface for the Credit Card Due lifecycle tracker."""

from __future__ import annotations

import sys
from datetime import date
from functools import partial

from PyQt6.QtCore import QEvent, QPoint, QRect, QTimer, Qt
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QContextMenuEvent,
    QFont,
    QKeySequence,
    QMouseEvent,
    QMoveEvent,
    QResizeEvent,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
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
    set_pre_authorized_debit,
    undo_last_paid,
    update_card,
)
from settings import SettingsService, WidgetPreferences


APP_STYLESHEET = """
QMainWindow {
    background: #0f1116;
}
QWidget {
    color: #f5f7fb;
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
QCheckBox {
    color: #dfe4ec;
    spacing: 8px;
}
QCheckBox::indicator {
    background: #252a34;
    border: 1px solid #383f4d;
    border-radius: 5px;
    height: 18px;
    width: 18px;
}
QCheckBox::indicator:checked {
    background: #61d995;
    border-color: #61d995;
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
QToolButton#menuButton {
    background: #252a34;
    border: 1px solid #383f4d;
    border-radius: 10px;
    color: #dfe4ec;
    font-size: 20px;
    font-weight: 700;
    min-height: 34px;
    min-width: 38px;
}
QToolButton#menuButton:hover {
    background: #343b48;
}
QToolButton#menuButton::menu-indicator {
    image: none;
}
QMenu {
    background: #20242d;
    border: 1px solid #383f4d;
    border-radius: 8px;
    padding: 6px;
}
QMenu::item {
    border-radius: 6px;
    padding: 8px 22px 8px 12px;
}
QMenu::item:selected {
    background: #7657ff;
}
QMenu::separator {
    background: #383f4d;
    height: 1px;
    margin: 5px 8px;
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


def build_app_stylesheet(
    *,
    desktop_widget_mode: bool,
    opacity: float,
) -> str:
    """Return normal or translucent desktop-widget styling."""
    if not desktop_widget_mode:
        return APP_STYLESHEET

    alpha = max(0, min(255, round(opacity * 255)))
    panel_alpha = max(0, min(255, alpha - 22))
    # Qt provides reliable alpha compositing here, but not native macOS
    # backdrop blur without adding an AppKit bridge such as PyObjC.
    return (
        APP_STYLESHEET
        + f"""
QMainWindow {{
    background: transparent;
}}
QFrame#shell {{
    background: rgba(19, 23, 31, {alpha});
    border: 1px solid rgba(255, 255, 255, 38);
    border-radius: 26px;
}}
QFrame#summaryCard {{
    background: rgba(42, 47, 59, {panel_alpha});
    border: 1px solid rgba(255, 255, 255, 35);
    border-radius: 18px;
}}
QFrame#summaryClear {{
    background: rgba(25, 52, 40, {panel_alpha});
    border: 1px solid rgba(106, 221, 154, 48);
    border-radius: 18px;
}}
QFrame#cardPanel {{
    background: rgba(38, 43, 54, {panel_alpha});
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 17px;
}}
QLabel#title {{
    font-size: 19px;
}}
QLabel#subtitle {{
    color: rgba(235, 239, 247, 185);
}}
QLabel#detailText, QLabel#mutedText {{
    color: rgba(235, 239, 247, 190);
}}
QPushButton {{
    min-height: 30px;
    padding: 0 11px;
}}
QToolButton#menuButton {{
    background: rgba(255, 255, 255, 22);
    border: 1px solid rgba(255, 255, 255, 35);
    min-height: 30px;
    min-width: 34px;
}}
"""
    )


def _format_date(value: date | None) -> str:
    if value is None:
        return "Not available"
    return value.strftime("%b %d, %Y").replace(" 0", " ")


def _clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        child_layout = item.layout()
        widget = item.widget()
        if child_layout is not None:
            _clear_layout(child_layout)
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


class CardFormDialog(QDialog):
    """Form used to add or edit recurring card configuration."""

    def __init__(
        self,
        card: CreditCard | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        is_editing = card is not None
        self.setWindowTitle("Edit Card" if is_editing else "Add Card")
        self.setModal(True)
        self.setMinimumWidth(350)
        self.setStyleSheet(APP_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        heading = QLabel("Edit credit card" if is_editing else "Add a card")
        heading.setObjectName("summaryTitle")
        layout.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(10)

        self.name_input = QLineEdit(card.card_name if card else "")
        self.name_input.setPlaceholderText("Card name")
        self.statement_day_input = self._day_input(card.statement_day if card else 5)
        self.due_day_input = self._day_input(card.due_day if card else 25)
        self.buffer_input = QSpinBox()
        self.buffer_input.setRange(0, 15)
        self.buffer_input.setValue(card.safety_buffer_days if card else 7)
        self.buffer_input.setSuffix(" days")
        self.pre_authorized_input = QCheckBox("Active")
        self.pre_authorized_input.setChecked(
            card.pre_authorized_debit if card else False
        )

        form.addRow("Card name", self.name_input)
        form.addRow("Statement day", self.statement_day_input)
        form.addRow("Due day", self.due_day_input)
        form.addRow("Safety buffer", self.buffer_input)
        form.addRow("Pre-authorized debit", self.pre_authorized_input)
        layout.addLayout(form)

        helper = QLabel(
            "Pay-by is a planning date before the official issuer due date. "
            "Pre-authorized debit is user-entered; verify it with your issuer."
        )
        helper.setObjectName("helperText")
        helper.setWordWrap(True)
        layout.addWidget(helper)

        accept_button = (
            QDialogButtonBox.StandardButton.Save
            if is_editing
            else QDialogButtonBox.StandardButton.Ok
        )
        buttons = QDialogButtonBox(
            accept_button | QDialogButtonBox.StandardButton.Cancel
        )
        if not is_editing:
            buttons.button(accept_button).setText("Add Card")
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

    def values(self) -> tuple[str, int, int, int, bool]:
        return (
            self.name_input.text(),
            self.statement_day_input.value(),
            self.due_day_input.value(),
            self.buffer_input.value(),
            self.pre_authorized_input.isChecked(),
        )


class CreditCardWidget(QMainWindow):
    """Compact desktop utility for credit-card payment cycles."""

    WIDGET_WIDTH = 360
    WIDGET_HEIGHT = 520

    def __init__(
        self,
        settings_service: SettingsService | None = None,
    ) -> None:
        super().__init__()
        self.settings_service = settings_service or SettingsService()
        self.preferences = self.settings_service.load()
        self._drag_offset: QPoint | None = None
        self._applying_window_mode = False
        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.setInterval(250)
        self._geometry_save_timer.timeout.connect(self._save_geometry)

        self.setWindowTitle("Credit Card Due")
        self.cards: list[CreditCard] = []

        self._build_ui()
        self._build_shortcuts()
        self._apply_window_mode(refresh=False)
        self._restore_position()
        self.refresh_cards()

    def _build_ui(self) -> None:
        root = QWidget()
        self.root_layout = QVBoxLayout(root)
        self.root_layout.setContentsMargins(10, 10, 10, 10)

        self.shell = QFrame()
        self.shell.setObjectName("shell")
        self.shell_layout = QVBoxLayout(self.shell)
        self.shell_layout.setContentsMargins(20, 20, 20, 18)
        self.shell_layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(10)

        self.title = QLabel("Credit Card Due")
        self.title.setObjectName("title")
        self.title.setFont(QFont(self.title.font().family(), 24, QFont.Weight.Bold))
        header.addWidget(self.title, 1)

        self.menu_button = QToolButton()
        self.menu_button.setObjectName("menuButton")
        self.menu_button.setText("⋯")
        self.menu_button.setToolTip("More options")
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.control_menu = self._build_control_menu(self.menu_button)
        self.menu_button.setMenu(self.control_menu)
        header.addWidget(self.menu_button)

        self.subtitle = QLabel(
            "Track when statements are ready and when payments are due."
        )
        self.subtitle.setObjectName("subtitle")
        self.subtitle.setWordWrap(True)
        self.shell_layout.addLayout(header)
        self.shell_layout.addWidget(self.subtitle)

        self.summary_frame = QFrame()
        self.summary_layout = QVBoxLayout(self.summary_frame)
        self.summary_layout.setContentsMargins(15, 14, 15, 14)
        self.summary_layout.setSpacing(6)
        self.shell_layout.addWidget(self.summary_frame)

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
        self.shell_layout.addWidget(self.success_row)

        self.cards_heading = QLabel("YOUR CARDS")
        self.cards_heading.setObjectName("sectionTitle")
        self.shell_layout.addWidget(self.cards_heading)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 2, 0, 2)
        self.list_layout.setSpacing(10)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.list_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.scroll.setWidget(self.list_container)
        self.shell_layout.addWidget(self.scroll, 1)

        self.root_layout.addWidget(self.shell)
        self.setCentralWidget(root)
        self._install_drag_targets(self.shell)

    def _build_control_menu(self, parent: QWidget) -> QMenu:
        menu = QMenu(parent)

        add_action = menu.addAction("Add a card")
        add_action.triggered.connect(self._add_card)
        menu.addSeparator()

        self.widget_mode_action = menu.addAction("Desktop Widget Mode")
        self.widget_mode_action.setCheckable(True)
        self.widget_mode_action.triggered.connect(self.set_desktop_widget_mode)

        self.always_on_top_action = menu.addAction("Always on Top")
        self.always_on_top_action.setCheckable(True)
        self.always_on_top_action.triggered.connect(self.set_always_on_top)

        self.stay_behind_action = menu.addAction("Stay Behind Normal Windows")
        self.stay_behind_action.setCheckable(True)
        self.stay_behind_action.triggered.connect(self.set_stay_behind)

        self.lock_position_action = menu.addAction("Lock Position")
        self.lock_position_action.setCheckable(True)
        self.lock_position_action.triggered.connect(self.set_lock_position)

        opacity_menu = menu.addMenu("Widget Opacity")
        self.opacity_group = QActionGroup(self)
        self.opacity_group.setExclusive(True)
        self.opacity_actions: dict[float, QAction] = {}
        for label, opacity in (("70%", 0.70), ("85%", 0.85), ("95%", 0.95)):
            action = opacity_menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked, value=opacity: (
                    self.set_widget_opacity(value) if checked else None
                )
            )
            self.opacity_group.addAction(action)
            self.opacity_actions[opacity] = action

        reset_position_action = menu.addAction("Reset Position")
        reset_position_action.triggered.connect(self.reset_window_position)

        menu.addSeparator()
        reset_action = menu.addAction("Reset All Data")
        reset_action.triggered.connect(self._reset_all_data)
        quit_action = menu.addAction("Quit Credit Card Due")
        quit_action.triggered.connect(QApplication.instance().quit)

        menu.aboutToShow.connect(self._sync_control_menu)
        return menu

    def _build_shortcuts(self) -> None:
        shortcut_sequence = (
            "Meta+Shift+W" if sys.platform == "darwin" else "Ctrl+Shift+W"
        )
        self.widget_mode_shortcut = QShortcut(
            QKeySequence(shortcut_sequence),
            self,
        )
        self.widget_mode_shortcut.activated.connect(
            lambda: self.set_desktop_widget_mode(
                not self.preferences.desktop_widget_mode
            )
        )

    def _sync_control_menu(self) -> None:
        self.widget_mode_action.setChecked(self.preferences.desktop_widget_mode)
        self.always_on_top_action.setChecked(self.preferences.always_on_top)
        self.stay_behind_action.setChecked(self.preferences.stay_behind)
        self.stay_behind_action.setEnabled(self.preferences.desktop_widget_mode)
        self.lock_position_action.setChecked(self.preferences.lock_position)
        self.lock_position_action.setEnabled(self.preferences.desktop_widget_mode)
        closest_opacity = min(
            self.opacity_actions,
            key=lambda value: abs(value - self.preferences.opacity),
        )
        for opacity, action in self.opacity_actions.items():
            action.setChecked(opacity == closest_opacity)

    def set_desktop_widget_mode(self, enabled: bool) -> None:
        if enabled == self.preferences.desktop_widget_mode:
            return
        if not self.preferences.desktop_widget_mode:
            self._save_geometry()
        self.preferences = self.settings_service.update(
            self.preferences,
            desktop_widget_mode=enabled,
        )
        self._apply_window_mode(refresh=True)
        self._save_geometry()

    def set_always_on_top(self, enabled: bool) -> None:
        changes: dict[str, object] = {"always_on_top": enabled}
        if enabled:
            changes["stay_behind"] = False
        self.preferences = self.settings_service.update(
            self.preferences,
            **changes,
        )
        self._apply_window_mode(refresh=False)

    def set_stay_behind(self, enabled: bool) -> None:
        changes: dict[str, object] = {"stay_behind": enabled}
        if enabled:
            changes["always_on_top"] = False
        self.preferences = self.settings_service.update(
            self.preferences,
            **changes,
        )
        self._apply_window_mode(refresh=False)

    def set_lock_position(self, enabled: bool) -> None:
        self.preferences = self.settings_service.update(
            self.preferences,
            lock_position=enabled,
        )
        self._drag_offset = None

    def set_widget_opacity(self, opacity: float) -> None:
        opacity = max(0.65, min(1.0, opacity))
        self.preferences = self.settings_service.update(
            self.preferences,
            opacity=opacity,
        )
        self.setStyleSheet(
            build_app_stylesheet(
                desktop_widget_mode=self.preferences.desktop_widget_mode,
                opacity=self.preferences.opacity,
            )
        )

    def reset_window_position(self) -> None:
        position = self._default_position()
        self.move(position)
        self._save_geometry()

    def _window_flags(self) -> Qt.WindowType:
        if self.preferences.desktop_widget_mode:
            flags = (
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.Tool
                | Qt.WindowType.NoDropShadowWindowHint
            )
            if self.preferences.always_on_top:
                flags |= Qt.WindowType.WindowStaysOnTopHint
            elif self.preferences.stay_behind:
                # This is the closest reliable Qt-only approximation to a
                # desktop-layer widget. It does not pin the window directly
                # to the wallpaper and behavior can vary by window manager.
                flags |= Qt.WindowType.WindowStaysOnBottomHint
            return flags

        flags = Qt.WindowType.Window
        if self.preferences.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        return flags

    def _apply_window_mode(self, *, refresh: bool) -> None:
        was_visible = self.isVisible()
        current_position = self.pos()
        self._applying_window_mode = True
        try:
            self.setWindowFlags(self._window_flags())
            widget_mode = self.preferences.desktop_widget_mode
            self.setAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground,
                widget_mode,
            )
            if sys.platform == "darwin":
                # Qt.Tool keeps the window out of the normal task switcher.
                # WA_MacAlwaysShowToolWindow keeps it visible while the app is
                # inactive. Qt alone cannot guarantee visibility on every
                # macOS Space without native AppKit collection behavior.
                self.setAttribute(
                    Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow,
                    widget_mode,
                )

            self.setStyleSheet(
                build_app_stylesheet(
                    desktop_widget_mode=widget_mode,
                    opacity=self.preferences.opacity,
                )
            )
            self.subtitle.setVisible(not widget_mode)
            self.cards_heading.setVisible(not widget_mode)

            if widget_mode:
                self.root_layout.setContentsMargins(0, 0, 0, 0)
                self.shell_layout.setContentsMargins(16, 16, 16, 15)
                self.shell_layout.setSpacing(10)
                self.setMinimumSize(self.WIDGET_WIDTH, self.WIDGET_HEIGHT)
                self.setMaximumSize(self.WIDGET_WIDTH, self.WIDGET_HEIGHT)
                self.resize(self.WIDGET_WIDTH, self.WIDGET_HEIGHT)
            else:
                self.root_layout.setContentsMargins(10, 10, 10, 10)
                self.shell_layout.setContentsMargins(20, 20, 20, 18)
                self.shell_layout.setSpacing(14)
                self.setMinimumSize(420, 560)
                self.setMaximumSize(480, 16777215)
                self.resize(
                    self.preferences.normal_width,
                    self.preferences.normal_height,
                )

            self.move(current_position)
            if was_visible:
                self.show()
        finally:
            self._applying_window_mode = False

        if refresh:
            self.refresh_cards()

    def _default_position(self) -> QPoint:
        screen = QApplication.primaryScreen()
        if screen is None:
            return QPoint(40, 40)
        available = screen.availableGeometry()
        if self.preferences.desktop_widget_mode:
            return QPoint(
                available.right() - self.width() - 24,
                available.top() + 24,
            )
        return QPoint(
            available.center().x() - self.width() // 2,
            available.center().y() - self.height() // 2,
        )

    def _restore_position(self) -> None:
        x = self.preferences.window_x
        y = self.preferences.window_y
        if x is None or y is None:
            self.move(self._default_position())
            return

        proposed = QRect(x, y, self.width(), self.height())
        visible = any(
            screen.availableGeometry().intersects(proposed)
            for screen in QApplication.screens()
        )
        self.move(QPoint(x, y) if visible else self._default_position())

    def _save_geometry(self) -> None:
        if self._applying_window_mode:
            return
        changes: dict[str, object] = {
            "window_x": self.x(),
            "window_y": self.y(),
        }
        if not self.preferences.desktop_widget_mode:
            changes.update(
                {
                    "normal_width": self.width(),
                    "normal_height": self.height(),
                }
            )
        self.preferences = self.settings_service.update(
            self.preferences,
            **changes,
        )

    def _install_drag_targets(self, widget: QWidget) -> None:
        for target in [widget, *widget.findChildren(QWidget)]:
            if isinstance(target, (QFrame, QLabel)):
                target.installEventFilter(self)

    def _add_card(self) -> None:
        dialog = CardFormDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        (
            card_name,
            statement_day,
            due_day,
            buffer_days,
            pre_authorized_debit,
        ) = dialog.values()
        try:
            add_card(
                card_name,
                statement_day,
                due_day,
                buffer_days,
                pre_authorized_debit,
            )
        except (ValueError, DatabaseError) as exc:
            self._show_error(str(exc))
            return

        cleaned_name = " ".join(card_name.split())
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
        self._install_drag_targets(self.summary_frame)
        self._install_drag_targets(self.list_container)

    def _render_summary(self) -> None:
        _clear_layout(self.summary_layout)
        due_cards = [
            card
            for card in self.cards
            if (
                card.status == PAYMENT_DUE
                and card.pay_by_date is not None
                and not card.pre_authorized_debit
            )
        ]
        if not due_cards:
            covered_due_count = sum(
                1
                for card in self.cards
                if card.status == PAYMENT_DUE and card.pre_authorized_debit
            )
            self.summary_frame.setObjectName("summaryClear")
            self.summary_frame.style().unpolish(self.summary_frame)
            self.summary_frame.style().polish(self.summary_frame)

            title_text = (
                "✓ No manual payment required"
                if covered_due_count
                else "✓ No payment required"
            )
            title = QLabel(title_text)
            title.setObjectName("statusGreen")
            title.setFont(QFont(title.font().family(), 16, QFont.Weight.Bold))
            detail_text = (
                "Due cards are covered by pre-authorized debit."
                if covered_due_count
                else "All cards are paid or waiting for the next statement."
            )
            detail = QLabel(detail_text)
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
        if self.preferences.desktop_widget_mode:
            paid_button.setObjectName("secondaryButton")
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
        panel.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum,
        )
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
            if card.pre_authorized_debit:
                countdown = QLabel("✓ AutoPay active")
                countdown.setObjectName("statusGreen")
            else:
                countdown = QLabel(self._payment_status_text(card))
                countdown.setObjectName(self._payment_status_style(card))
            due = QLabel(f"Official due date: {_format_date(card.current_due_date)}")
            due.setObjectName("detailText")
            pay_by = QLabel(f"Pay-by planning date: {_format_date(card.pay_by_date)}")
            pay_by.setObjectName("detailText")
            layout.addWidget(countdown)
            layout.addWidget(due)
            layout.addWidget(pay_by)
            if card.pre_authorized_debit:
                note = QLabel(
                    "Pre-authorized debit should handle this payment automatically."
                )
                note.setObjectName("detailText")
                note.setWordWrap(True)
                layout.addWidget(note)
        else:
            if card.status == PAID:
                paid = QLabel("No payment required")
                paid.setObjectName("statusGreen")
                layout.addWidget(paid)
            if card.pre_authorized_debit:
                covered = QLabel("✓ AutoPay active")
                covered.setObjectName("statusGreen")
                layout.addWidget(covered)
            next_statement = QLabel(
                "Next statement expected: "
                f"{_format_date(card.current_statement_date)}"
            )
            next_statement.setObjectName("detailText")
            layout.addWidget(next_statement)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        if card.status == PAYMENT_DUE and not card.pre_authorized_debit:
            paid_button = QPushButton("Mark Paid")
            if self.preferences.desktop_widget_mode:
                paid_button.setObjectName("secondaryButton")
            paid_button.clicked.connect(partial(self._mark_paid, card.id))
            actions.addWidget(paid_button)

        autopay_button = QPushButton(
            "Disable AutoPay" if card.pre_authorized_debit else "Enable AutoPay"
        )
        autopay_button.setObjectName("secondaryButton")
        autopay_button.clicked.connect(
            partial(
                self._toggle_pre_authorized_debit,
                card.id,
                not card.pre_authorized_debit,
            )
        )
        actions.addWidget(autopay_button)
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
        if self.preferences.desktop_widget_mode:
            edit_button.hide()
            delete_button.hide()
        self._install_drag_targets(panel)
        return panel

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if self.preferences.desktop_widget_mode and not self.preferences.lock_position:
            if event.type() == QEvent.Type.MouseButtonPress:
                mouse_event = event
                if (
                    isinstance(mouse_event, QMouseEvent)
                    and mouse_event.button() == Qt.MouseButton.LeftButton
                ):
                    self._drag_offset = (
                        mouse_event.globalPosition().toPoint()
                        - self.frameGeometry().topLeft()
                    )
                    return True
            elif event.type() == QEvent.Type.MouseMove:
                mouse_event = event
                if (
                    isinstance(mouse_event, QMouseEvent)
                    and self._drag_offset is not None
                    and mouse_event.buttons() & Qt.MouseButton.LeftButton
                ):
                    self.move(
                        mouse_event.globalPosition().toPoint() - self._drag_offset
                    )
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if self._drag_offset is not None:
                    self._drag_offset = None
                    self._save_geometry()
                    return True
        return super().eventFilter(watched, event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._sync_control_menu()
        self.control_menu.exec(event.globalPos())

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        if not self._applying_window_mode:
            self._geometry_save_timer.start()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if not self._applying_window_mode and not self.preferences.desktop_widget_mode:
            self._geometry_save_timer.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_geometry()
        super().closeEvent(event)

    @staticmethod
    def _card_status_title(card: CreditCard) -> str:
        if card.pre_authorized_debit:
            return "✓ AutoPay active"
        if card.status == PAID:
            return "✓ Paid"
        if card.status == NO_PAYMENT_REQUIRED:
            return "✓ No payment required"
        return "Payment due"

    @staticmethod
    def _card_status_style(card: CreditCard) -> str:
        if card.pre_authorized_debit or card.status in {PAID, NO_PAYMENT_REQUIRED}:
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

    def _toggle_pre_authorized_debit(self, card_id: int, enabled: bool) -> None:
        try:
            set_pre_authorized_debit(card_id, enabled)
        except (ValueError, DatabaseError) as exc:
            self._show_error(str(exc))
            return

        if enabled:
            message = "AutoPay enabled. Green check added for this card."
        else:
            message = "AutoPay disabled. Manual payment reminders restored."
        self._show_success(message)
        self.refresh_cards()

    def _edit_card(self, card: CreditCard) -> None:
        dialog = CardFormDialog(card, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        (
            card_name,
            statement_day,
            due_day,
            buffer_days,
            pre_authorized_debit,
        ) = dialog.values()
        try:
            update_card(
                card.id,
                card_name,
                statement_day,
                due_day,
                buffer_days,
                pre_authorized_debit,
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
            self.undo_button.clicked.connect(partial(self._undo_paid, undo_card_id))
        self.success_row.show()

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(
            self,
            "Something went wrong",
            f"The card database could not be updated.\n\n{message}",
        )
