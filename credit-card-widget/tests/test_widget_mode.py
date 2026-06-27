"""Qt window-mode behavior tests for Credit Card Due."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication

import db
from settings import SettingsService
from ui import CreditCardWidget, build_app_stylesheet


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def widget_window(tmp_path, monkeypatch, qt_app):
    monkeypatch.setenv(db.DB_PATH_ENV, str(tmp_path / "cards.duckdb"))
    db.init_db()
    settings = QSettings(
        str(tmp_path / "widget-settings.ini"),
        QSettings.Format.IniFormat,
    )
    service = SettingsService(settings)
    window = CreditCardWidget(service)
    yield window, service
    window.close()
    qt_app.processEvents()


def test_widget_mode_applies_frameless_translucent_window(widget_window):
    window, service = widget_window

    window.set_desktop_widget_mode(True)

    flags = window.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.Tool
    assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert window.width() == window.WIDGET_WIDTH
    assert window.height() == window.WIDGET_HEIGHT
    assert window.subtitle.isHidden()
    assert service.load().desktop_widget_mode is True


def test_returning_to_normal_mode_restores_normal_window(widget_window):
    window, service = widget_window
    window.set_desktop_widget_mode(True)

    window.set_desktop_widget_mode(False)

    flags = window.windowFlags()
    assert not flags & Qt.WindowType.FramelessWindowHint
    assert not window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert not window.subtitle.isHidden()
    assert window.minimumWidth() == 420
    assert service.load().desktop_widget_mode is False


def test_window_layer_settings_are_mutually_exclusive(widget_window):
    window, service = widget_window
    window.set_desktop_widget_mode(True)

    window.set_stay_behind(True)
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnBottomHint
    assert service.load().always_on_top is False

    window.set_always_on_top(True)
    preferences = service.load()
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnBottomHint
    assert preferences.always_on_top is True
    assert preferences.stay_behind is False


def test_position_lock_opacity_and_position_persist(widget_window):
    window, service = widget_window
    window.set_desktop_widget_mode(True)
    window.set_lock_position(True)
    window.set_widget_opacity(0.70)
    window.move(36, 48)
    window._save_geometry()

    preferences = service.load()

    assert preferences.lock_position is True
    assert preferences.opacity == 0.70
    assert preferences.window_x == window.x()
    assert preferences.window_y == window.y()


def test_widget_stylesheet_uses_translucent_rounded_card():
    stylesheet = build_app_stylesheet(
        desktop_widget_mode=True,
        opacity=0.85,
    )

    assert "background: transparent" in stylesheet
    assert "background: rgba(" in stylesheet
    assert "border-radius: 26px" in stylesheet
