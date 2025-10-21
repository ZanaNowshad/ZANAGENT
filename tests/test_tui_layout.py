from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("textual")

from vortex.ui_tui.layout import build_layout
from vortex.ui_tui.panels import CommandBar, ContextPanel, MainPanel, TelemetryBar


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


def test_context_panel_stores_path(tmp_path: Path) -> None:
    panel = ContextPanel(tmp_path)
    assert panel.id == "context-panel"
    assert panel.can_focus


def test_telemetry_bar_defaults() -> None:
    bar = TelemetryBar()
    assert bar.cpu_usage == 0.0
    assert "CPU" in bar.render().plain
