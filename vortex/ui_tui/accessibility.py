"""Accessibility helpers for the Vortex Textual interface."""

from __future__ import annotations

import asyncio
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
    high_contrast: bool = False


class AccessibilityAnnouncer:
    """Dispatch announcements for assistive technologies and screen readers.

    Textual's :meth:`~textual.app.App.notify` API integrates nicely with
    terminal screen readers on macOS/Linux.  The announcer keeps a per-frame
    dedupe buffer and exposes helpers for common cues (panel focus, progress,
    errors) so callers remain declarative.
    """

    def __init__(self, app: App, *, preferences: AccessibilityPreferences) -> None:
        self._app = app
        self._preferences = preferences
        self._last_message: Optional[str] = None
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        """Return whether announcements are currently enabled."""

        return self._preferences.enabled

    def set_enabled(self, value: bool) -> None:
        """Toggle the narrator without mutating external state."""

        self._preferences.enabled = value

    def set_verbosity(self, level: str) -> None:
        """Update narration verbosity (minimal/normal/verbose)."""

        self._preferences.verbosity = level

    def set_high_contrast(self, enabled: bool) -> None:
        """Persist the high contrast preference for screen-reader hints."""

        self._preferences.high_contrast = enabled

    async def announce(
        self,
        message: str,
        *,
        severity: str = "info",
        dedupe: bool = True,
    ) -> None:
        """Emit an announcement if the operator opted-in."""

        if not self.enabled or not message:
            return
        async with self._lock:
            if dedupe and message == self._last_message:
                return
            self._last_message = message
        await self._app.notify(message, severity=severity)

    async def announce_panel(self, panel: str, *, detail: str | None = None) -> None:
        """Announce panel focus changes with optional extra context."""

        if not self.enabled:
            return
        suffix = f": {detail}" if detail and self._preferences.verbosity != "minimal" else ""
        await self.announce(f"Focus on {panel} panel{suffix}", severity="information")

    async def announce_plain_text(self, summary: str) -> None:
        """Emit a summary of the latest diff/log for screen readers."""

        if not self.enabled or not summary:
            return
        if self._preferences.verbosity == "minimal":
            summary = summary.splitlines()[0] if summary else summary
        await self.announce(summary, severity="information", dedupe=False)

    async def announce_progress(self, label: str, percent: int | None = None) -> None:
        """Surface progress updates in a compact, ARIA-style string."""

        if not self.enabled:
            return
        if percent is None or self._preferences.verbosity == "minimal":
            message = f"{label} in progress"
        else:
            message = f"{label} {percent}% complete"
        await self.announce(message, severity="information", dedupe=False)

    async def announce_error(self, message: str) -> None:
        """Emit high-priority error announcements."""

        await self.announce(message, severity="error", dedupe=False)


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
