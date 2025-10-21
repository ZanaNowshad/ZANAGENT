"""Accessibility helpers for the TUI."""
from __future__ import annotations

from textual.app import App
from textual.message import Message


class AccessibilityAnnouncer:
    """Dispatches announcements for assistive technologies.

    Textual exposes ``App.notify`` which integrates with screen readers on
    supported terminals. We centralise invocations in this helper to simplify
    testing and to avoid flooding users with duplicate notifications.
    """

    def __init__(self, app: App, *, enabled: bool) -> None:
        self._app = app
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value

    async def announce(self, message: str, *, severity: str = "info") -> None:
        if not self._enabled:
            return
        self._app.log(f"announce[{severity}]: {message}")
        await self._app.notify(message, severity=severity)


class AccessibilityToggle(Message):
    """Message emitted when accessibility mode changes."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        super().__init__()


__all__ = ["AccessibilityAnnouncer", "AccessibilityToggle"]
