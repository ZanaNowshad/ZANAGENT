from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("textual")

from vortex.ui_tui.layout import build_layout
from vortex.ui_tui.palette import PaletteEntry
from vortex.ui_tui.panels import (
    AnalyticsPanel,
    CommandBar,
    ContextPanel,
    MainPanel,
    SessionsPanel,
    TelemetryBar,
)
from vortex.ui_tui.settings import TUISettingsManager


def test_build_layout_metadata(tmp_path: Path) -> None:
    layout = build_layout(tmp_path)
    assert layout.id == "root-layout"
    assert getattr(layout, "_root_path") == tmp_path


def test_main_panel_logging(tmp_path: Path) -> None:
    panel = MainPanel(id="main-panel")
    list(panel.compose())
    # Ensure the panel can accept renderables without raising
    panel.show("hello")
    panel.append("world")


def test_command_bar_placeholder() -> None:
    bar = CommandBar()
    assert bar.input.placeholder == "/plan or :palette"


def test_command_bar_suggestions_toggle() -> None:
    bar = CommandBar()
    entry = PaletteEntry(label="Plan", hint="Plan", command="/plan")
    bar.update_suggestions([entry])
    assert not bar.suggestions.has_class("hidden")
    assert len(bar.suggestions.children) == 1
    bar.clear_suggestions()
    assert bar.suggestions.has_class("hidden")


def test_command_bar_suggestion_selected_message() -> None:
    bar = CommandBar()
    entry = PaletteEntry(label="Plan", hint="Plan", command="/plan")
    bar.update_suggestions([entry])
    captured: list[CommandBar.SuggestionSelected] = []

    def capture(message: CommandBar.SuggestionSelected) -> None:
        captured.append(message)

    bar.post_message = capture  # type: ignore[assignment]
    event = SimpleNamespace(item=bar.suggestions.children[0])
    event.item.data = entry.command  # type: ignore[attr-defined]
    bar._suggestion_selected(event)  # type: ignore[arg-type]
    assert captured and captured[0].command == "/plan"


def test_context_panel_stores_path(tmp_path: Path) -> None:
    panel = ContextPanel(tmp_path)
    assert panel.id == "context-panel"
    assert panel.can_focus


def test_telemetry_bar_defaults() -> None:
    bar = TelemetryBar()
    assert bar.cpu_usage == 0.0
    assert "CPU" in bar.render().plain


def test_sessions_and_analytics_panels() -> None:
    sessions = SessionsPanel()
    list(sessions.compose())
    sessions.update_sessions(
        {"alice@host": {"user": "alice", "host": "host", "role": "owner", "read_only": False, "last_seen": 0.0}},
        lock_holder=None,
        checkpoints=[{"identifier": "cp-001", "summary": "init"}],
    )
    analytics = AnalyticsPanel()
    list(analytics.compose())
    analytics.update_summary({"kpis": {}, "events": [], "success_rate": 0.0}, [])


@pytest.mark.asyncio
async def test_settings_manager_persistence(tmp_path: Path) -> None:
    manager = TUISettingsManager(
        global_path=tmp_path / "config.toml", local_path=tmp_path / "session.toml"
    )
    settings = await manager.load()
    settings.model = "gpt-4"
    settings.theme = "light"
    settings.custom_theme_path = tmp_path / "theme.yaml"
    await manager.persist(settings)
    reloaded = await manager.reload()
    assert reloaded.model == "gpt-4"
    assert reloaded.theme == "light"
    assert reloaded.custom_theme_path == tmp_path / "theme.yaml"
