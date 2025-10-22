import asyncio
from pathlib import Path

import pytest

pytest.importorskip("textual")

from vortex.ui_tui.app import PanelUpdateCoalescer, RefreshCoalescer
from vortex.ui_tui.themes import theme_css


class DummyApp:
    def __init__(self) -> None:
        self.count = 0

    async def refresh(self) -> None:
        self.count += 1


@pytest.mark.asyncio
async def test_refresh_coalescer_limits_refreshes() -> None:
    app = DummyApp()
    coalescer = RefreshCoalescer(app, interval=0.01)
    coalescer.request()
    coalescer.request()
    await asyncio.sleep(0.05)
    assert app.count == 1


def test_theme_css_high_contrast() -> None:
    css = theme_css("dark", no_color=False, high_contrast=True)
    assert "#" in css
    assert "background" in css


@pytest.mark.asyncio
async def test_panel_update_coalescer_batches(tmp_path: Path) -> None:
    app = DummyApp()
    recorder: list[str] = []
    coalescer = PanelUpdateCoalescer(app, interval=0.01)
    coalescer.enqueue(lambda: recorder.append("first"))
    coalescer.enqueue(lambda: recorder.append("second"))
    await asyncio.sleep(0.05)
    assert recorder == ["first", "second"]
    assert app.count == 1


def test_theme_css_custom(tmp_path: Path) -> None:
    palette = tmp_path / "theme.yaml"
    palette.write_text(
        """
palette:
  screen:
    background: "#222222"
    color: "#eeeeee"
  panels:
    main:
      border: "#ff00ff"
"""
    )
    css = theme_css("dark", no_color=False, custom=palette)
    assert "#222222" in css
    assert "#ff00ff" in css
