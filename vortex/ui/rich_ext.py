"""Extended Rich UI bridge."""

from __future__ import annotations

from typing import Iterable

from rich.table import Table

from vortex.core.ui import UnifiedRichUI
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class RichUIBridge:
    """Expose higher-level composites on top of :class:`UnifiedRichUI`."""

    def __init__(self, ui: UnifiedRichUI) -> None:
        self._ui = ui

    def render_table(
        self, title: str, headers: Iterable[str], rows: Iterable[Iterable[str]]
    ) -> None:
        table = Table(title=title)
        for header in headers:
            table.add_column(header)
        for row in rows:
            table.add_row(*list(row))
        self._ui.console.print(table)
        logger.debug("rich table rendered", extra={"title": title})

    def prompt(self, message: str) -> str:
        return self._ui.console.input(message + ": ")
