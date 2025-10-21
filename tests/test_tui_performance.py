import asyncio

import pytest

pytest.importorskip("textual")

from vortex.ui_tui.app import RefreshCoalescer
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
