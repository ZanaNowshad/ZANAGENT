"""Widget collection composing the Vortex TUI."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from rich.console import RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DirectoryTree, Footer, Header, Input, Label, ListItem, ListView, RichLog, Static

from .help import help_renderable


class VortexPanel(Static):
    """Base widget with a convenience ``update`` method."""

    can_focus = True

    def update_renderable(self, renderable: RenderableType) -> None:
        self.update(renderable)


class MainPanel(VortexPanel):
    """Primary panel rendering chat, plans, diffs, and logs."""

    DEFAULT_CSS = "#main-panel RichLog {height: 100%;}"

    def compose(self) -> ComposeResult:
        self._log = RichLog(highlight=True, markup=True)
        yield self._log

    def show(self, renderable: RenderableType) -> None:
        self._log.clear()
        self._log.write(renderable)

    def append(self, renderable: RenderableType) -> None:
        self._log.write(renderable)


class ContextPanel(VortexPanel):
    """File tree and context snippets."""

    def __init__(self, path: Path) -> None:
        super().__init__(id="context-panel")
        self._path = path

    def compose(self) -> ComposeResult:
        tree = DirectoryTree(str(self._path), id="context-tree")
        yield tree


class ActionsPanel(VortexPanel):
    """List of contextual actions with keyboard hints."""

    ACTIONS: Iterable[tuple[str, str]] = (
        ("Plan", "p"),
        ("Apply", "a"),
        ("Undo", "u"),
        ("Simulate", "s"),
        ("Run Tests", "t"),
    )

    def compose(self) -> ComposeResult:
        items = [
            ListItem(Label(f"{label} [{key}]"), id=f"action-{label.lower()}")
            for label, key in self.ACTIONS
        ]
        self._list = ListView(*items, id="actions-list")
        yield self._list

    def focus_index(self, index: int) -> None:
        self._list.index = index


class StatusPanel(VortexPanel):
    """Status summary table."""

    def compose(self) -> ComposeResult:
        placeholder = Text("Loading status…", style="italic")
        yield Static(placeholder, id="status-content")

    def update_status(self, renderable: RenderableType) -> None:
        content = self.query_one("#status-content", Static)
        content.update(renderable)


class ToolPanel(VortexPanel):
    """Toggleable panel listing available tools."""

    def compose(self) -> ComposeResult:
        self._list = ListView(id="tool-list")
        yield self._list

    def populate(self, tools: Iterable[str]) -> None:
        items = [ListItem(Label(tool)) for tool in tools]
        self._list.clear()
        self._list.extend(items)


class HelpPanel(VortexPanel):
    """Toggleable help overlay."""

    def compose(self) -> ComposeResult:
        yield Static(help_renderable(), id="help-content")


class CommandBar(Container):
    """Bottom command input used for slash commands and palette."""

    def __init__(self) -> None:
        super().__init__(id="command-bar")
        self.input = Input(placeholder="/plan or :palette", id="command-input")

    def compose(self) -> ComposeResult:
        yield self.input


class RootLayout(Container):
    """Overall layout container orchestrating sub-panels."""

    def __init__(self, root_path: Optional[Path] = None) -> None:
        super().__init__(id="root-layout")
        self._root_path = root_path or Path.cwd()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-row"):
            yield MainPanel(id="main-panel")
            with Vertical(id="side-panels"):
                yield ContextPanel(self._root_path)
                yield ActionsPanel(id="actions-panel")
        yield StatusPanel(id="status-panel")
        yield ToolPanel(id="tool-panel", classes="hidden")
        yield HelpPanel(id="help-panel", classes="hidden")
        yield CommandBar()
        yield Footer()


__all__ = [
    "ActionsPanel",
    "CommandBar",
    "ContextPanel",
    "HelpPanel",
    "MainPanel",
    "RootLayout",
    "StatusPanel",
    "ToolPanel",
]
