"""Desktop-style terminal UI."""
from __future__ import annotations

from typing import Dict

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel

from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class DesktopGUI:
    """Render a split-panel dashboard in the terminal."""

    def __init__(self) -> None:
        self._console = Console()

    def render(self, title: str, panels: Dict[str, str]) -> None:
        layout = Layout(name="root")
        layout.split_row(*(Layout(Panel(content, title=name)) for name, content in panels.items()))
        self._console.print(Panel(layout, title=title))
        logger.debug("desktop gui render", extra={"title": title, "panels": list(panels)})
