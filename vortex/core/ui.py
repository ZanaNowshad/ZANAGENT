"""Rich-based terminal UI helpers."""

from __future__ import annotations

import contextlib
from typing import Iterable, List, Optional

from rich.console import Console
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text


class UnifiedRichUI:
    """Wrap the Rich console to provide consistent UX."""

    def __init__(self, *, theme: str = "default", enable_progress: bool = True) -> None:
        self.console = Console()
        self.theme = theme
        self.enable_progress = enable_progress

    def print_header(self, title: str) -> None:
        self.console.rule(Text(title, style="bold cyan"))

    def info(self, message: str) -> None:
        self.console.print(Text(message, style="green"))

    def warn(self, message: str) -> None:
        self.console.print(Text(message, style="yellow"))

    def error(self, message: str) -> None:
        self.console.print(Text(message, style="bold red"))

    @contextlib.contextmanager
    def spinner(self, message: str) -> Iterable[None]:
        if not self.enable_progress:
            self.info(message)
            yield
            return
        progress = Progress(SpinnerColumn(), TextColumn("{task.description}"), TimeElapsedColumn())
        task = progress.add_task(message, total=None)
        with progress:
            yield
            progress.update(task, completed=1)

    def table(self, title: str, columns: List[str], rows: List[List[str]]) -> Table:
        table = Table(title=title)
        for column in columns:
            table.add_column(column)
        for row in rows:
            table.add_row(*row)
        return table

    @contextlib.contextmanager
    def live(self) -> Iterable[Live]:
        with Live(console=self.console, refresh_per_second=4) as live:
            yield live


__all__ = ["UnifiedRichUI"]
