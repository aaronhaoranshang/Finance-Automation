"""Settings persistence tests for desktop widget mode."""

from PyQt6.QtCore import QSettings

from settings import SettingsService, WidgetPreferences


def test_widget_preferences_round_trip(tmp_path):
    settings = QSettings(
        str(tmp_path / "widget-settings.ini"),
        QSettings.Format.IniFormat,
    )
    service = SettingsService(settings)
    preferences = WidgetPreferences(
        desktop_widget_mode=True,
        window_x=120,
        window_y=240,
        lock_position=True,
        always_on_top=True,
        stay_behind=False,
        opacity=0.75,
        normal_width=470,
        normal_height=810,
    )

    service.save(preferences)

    assert service.load() == preferences


def test_widget_preferences_use_safe_defaults(tmp_path):
    settings = QSettings(
        str(tmp_path / "widget-settings.ini"),
        QSettings.Format.IniFormat,
    )
    settings.setValue("desktop_widget_mode", "true")
    settings.setValue("opacity", "not-a-number")
    settings.setValue("normal_width", 9999)
    settings.setValue("normal_height", 1)
    settings.sync()

    preferences = SettingsService(settings).load()

    assert preferences.desktop_widget_mode is True
    assert preferences.opacity == 0.88
    assert preferences.normal_width == 480
    assert preferences.normal_height == 560


def test_settings_update_persists_selected_changes(tmp_path):
    settings = QSettings(
        str(tmp_path / "widget-settings.ini"),
        QSettings.Format.IniFormat,
    )
    service = SettingsService(settings)
    initial = service.load()

    updated = service.update(
        initial,
        desktop_widget_mode=True,
        lock_position=True,
        window_x=44,
        window_y=55,
    )

    assert updated.desktop_widget_mode is True
    assert updated.lock_position is True
    assert service.load().window_x == 44
    assert service.load().window_y == 55


def test_conflicting_window_layers_prefer_always_on_top(tmp_path):
    settings = QSettings(
        str(tmp_path / "widget-settings.ini"),
        QSettings.Format.IniFormat,
    )
    settings.setValue("always_on_top", True)
    settings.setValue("stay_behind", True)
    settings.sync()

    preferences = SettingsService(settings).load()

    assert preferences.always_on_top is True
    assert preferences.stay_behind is False
