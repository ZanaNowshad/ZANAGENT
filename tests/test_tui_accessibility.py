import pytest

import pytest

pytest.importorskip("textual")

from vortex.ui_tui.accessibility import AccessibilityAnnouncer, AccessibilityPreferences


class DummyApp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def notify(self, message: str, severity: str = "info") -> None:
        self.calls.append((message, severity))


@pytest.mark.asyncio
async def test_announcer_respects_preferences() -> None:
    app = DummyApp()
    prefs = AccessibilityPreferences(enabled=True, verbosity="normal")
    announcer = AccessibilityAnnouncer(app, preferences=prefs)

    await announcer.announce("Hello")
    await announcer.announce("Hello")  # deduplicated
    await announcer.announce_plain_text("Line one\nLine two")

    assert app.calls[0] == ("Hello", "info")
    assert len(app.calls) == 2

    prefs.verbosity = "minimal"
    await announcer.announce_plain_text("First line\nSecond line")
    assert app.calls[-1][0] == "First line"

    announcer.set_enabled(False)
    await announcer.announce("Ignored")
    assert len(app.calls) == 3

    announcer.set_enabled(True)
    await announcer.announce("Back")
    assert app.calls[-1] == ("Back", "info")


@pytest.mark.asyncio
async def test_announcer_panel_and_progress() -> None:
    app = DummyApp()
    prefs = AccessibilityPreferences(enabled=True, verbosity="verbose")
    announcer = AccessibilityAnnouncer(app, preferences=prefs)

    await announcer.announce_panel("main", detail="diff view")
    await announcer.announce_progress("apply", percent=42)
    await announcer.announce_error("Failure")
    announcer.set_high_contrast(True)

    assert any("Focus on Main panel" in message for message, _ in app.calls)
    assert any("Apply 42%" in message for message, _ in app.calls)
    assert app.calls[-1] == ("Failure", "error")
