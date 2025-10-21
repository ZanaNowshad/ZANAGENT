"""Accessibility helpers for the TUI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from textual.app import App
from textual.message import Message


@dataclass
class AccessibilityPreferences:
    """Mutable preferences controlling assistive cues."""

    enabled: bool = False
    verbosity: str = "normal"
    announce_narration: bool = False


class AccessibilityAnnouncer:
    """Dispatches announcements for assistive technologies."""

    def __init__(self, app: App, *, preferences: AccessibilityPreferences) -> None:
        self._app = app
        self._preferences = preferences
        self._last_message: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return self._preferences.enabled

    def set_enabled(self, value: bool) -> None:
        self._preferences.enabled = value

    def set_verbosity(self, level: str) -> None:
        self._preferences.verbosity = level

    async def announce(self, message: str, *, severity: str = "info", dedupe: bool = True) -> None:
        """Emit an announcement if the user has opted-in."""

        if not self.enabled:
            return
        if dedupe and message == self._last_message:
            return
        self._last_message = message
        await self._app.notify(message, severity=severity)

    async def announce_panel(self, panel: str) -> None:
        if not self.enabled:
            return
        await self.announce(f"Focus on {panel} panel", severity="information")

    async def announce_plain_text(self, summary: str) -> None:
        if not self.enabled or not summary:
            return
        if self._preferences.verbosity == "minimal":
            summary = summary.splitlines()[0] if summary else summary
        await self.announce(summary, severity="information", dedupe=False)


class AccessibilityToggle(Message):
    """Message emitted when accessibility mode changes."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        super().__init__()


class AccessibilityPreferencesChanged(Message):
    """Message emitted when verbosity/narration toggles update."""

    def __init__(self, preferences: AccessibilityPreferences) -> None:
        self.preferences = preferences
        super().__init__()


__all__ = [
    "AccessibilityAnnouncer",
    "AccessibilityPreferences",
    "AccessibilityPreferencesChanged",
    "AccessibilityToggle",
]
