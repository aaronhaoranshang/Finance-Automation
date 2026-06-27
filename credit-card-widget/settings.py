"""Persistent presentation settings for Credit Card Due."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PyQt6.QtCore import QSettings


ORGANIZATION_NAME = "Credit Card Widget"
APPLICATION_NAME = "Credit Card Due"


@dataclass(frozen=True)
class WidgetPreferences:
    """User-controlled window behavior persisted across launches."""

    desktop_widget_mode: bool = False
    window_x: int | None = None
    window_y: int | None = None
    lock_position: bool = False
    always_on_top: bool = False
    stay_behind: bool = False
    opacity: float = 0.88
    normal_width: int = 450
    normal_height: int = 700


class SettingsService:
    """Typed wrapper around QSettings."""

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings(
            ORGANIZATION_NAME,
            APPLICATION_NAME,
        )

    def load(self) -> WidgetPreferences:
        always_on_top = self._bool("always_on_top", False)
        stay_behind = self._bool("stay_behind", False)
        if always_on_top and stay_behind:
            stay_behind = False

        return WidgetPreferences(
            desktop_widget_mode=self._bool("desktop_widget_mode", False),
            window_x=self._optional_int("window_x"),
            window_y=self._optional_int("window_y"),
            lock_position=self._bool("lock_position", False),
            always_on_top=always_on_top,
            stay_behind=stay_behind,
            opacity=self._float("opacity", 0.88, minimum=0.65, maximum=1.0),
            normal_width=self._int(
                "normal_width",
                450,
                minimum=420,
                maximum=480,
            ),
            normal_height=self._int(
                "normal_height",
                700,
                minimum=560,
                maximum=1200,
            ),
        )

    def save(self, preferences: WidgetPreferences) -> None:
        values = {
            "desktop_widget_mode": preferences.desktop_widget_mode,
            "window_x": preferences.window_x,
            "window_y": preferences.window_y,
            "lock_position": preferences.lock_position,
            "always_on_top": preferences.always_on_top,
            "stay_behind": preferences.stay_behind,
            "opacity": preferences.opacity,
            "normal_width": preferences.normal_width,
            "normal_height": preferences.normal_height,
        }
        for key, value in values.items():
            if value is None:
                self._settings.remove(key)
            else:
                self._settings.setValue(key, value)
        self._settings.sync()

    def update(
        self,
        preferences: WidgetPreferences,
        **changes: object,
    ) -> WidgetPreferences:
        updated = replace(preferences, **changes)
        self.save(updated)
        return updated

    def _bool(self, key: str, default: bool) -> bool:
        value = self._settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _optional_int(self, key: str) -> int | None:
        value = self._settings.value(key)
        if value in {None, ""}:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _int(
        self,
        key: str,
        default: int,
        *,
        minimum: int,
        maximum: int,
    ) -> int:
        value = self._settings.value(key, default)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(maximum, parsed))

    def _float(
        self,
        key: str,
        default: float,
        *,
        minimum: float,
        maximum: float,
    ) -> float:
        value = self._settings.value(key, default)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(maximum, parsed))
