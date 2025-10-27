"""Widgets composing the TUI layout."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import (
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
)

from .analytics_panel import analytics_dashboard, sessions_table
from .help import help_renderable
from .palette import PaletteEntry
from .settings import TUISettings
from vortex.org.ops_center import OpsSnapshot


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
        self._last_plain_text: str = ""
        yield self._log

    def show(self, renderable: RenderableType, *, plain_text: str | None = None) -> None:
        self._log.clear()
        self._log.write(renderable)
        self._last_plain_text = plain_text or (
            renderable.plain if hasattr(renderable, "plain") else str(renderable)
        )

    def append(self, renderable: RenderableType, *, plain_text: str | None = None) -> None:
        self._log.write(renderable)
        if plain_text:
            self._last_plain_text = plain_text

    def last_plain_text(self) -> str:
        return self._last_plain_text


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


class OrgCenterPanel(VortexPanel):
    """Panel showing organisation-wide metrics and alerts."""

    def compose(self) -> ComposeResult:
        self._summary = Static("Org metrics loading…", id="org-summary")
        self._alerts = RichLog(id="org-alerts", highlight=True)
        wrapper = Vertical(
            Label("Knowledge Graph & Ops", id="org-title"),
            self._summary,
            Label("Active Alerts", id="org-alerts-title"),
            self._alerts,
        )
        yield wrapper

    def update_snapshot(self, snapshot: OpsSnapshot) -> None:
        table = Table(show_header=False, box=None)
        table.add_column("Metric")
        table.add_column("Value")
        table.add_row("Nodes", str(snapshot.nodes))
        table.add_row("Pipelines", str(snapshot.pipelines))
        table.add_row("Incidents", str(snapshot.incidents))
        table.add_row("Latency", f"{snapshot.avg_latency_ms:.2f} ms")
        table.add_row("Token Cost", f"${snapshot.token_cost:.2f}")
        self._summary.update(table)
        self._alerts.clear()
        if not snapshot.alerts:
            self._alerts.write("No active alerts")
        else:
            for alert in snapshot.alerts:
                self._alerts.write(f"[{alert.level}] {alert.message}")

class CommandBar(Container):
    """Bottom command input used for slash commands and palette."""

    class SuggestionSelected(Message):
        """Message raised when an autocomplete entry is activated."""

        def __init__(self, command: str) -> None:
            super().__init__()
            self.command = command

    def __init__(self) -> None:
        super().__init__(id="command-bar")
        self.input = Input(placeholder="/plan or :palette", id="command-input")
        self.suggestions = ListView(id="command-suggestions")
        self.suggestions.can_focus = False
        self.suggestions.add_class("hidden")
        self._pending_entries: list[PaletteEntry] = []

    def on_mount(self) -> None:
        if self._pending_entries:
            self._render_suggestions(self._pending_entries)

    def compose(self) -> ComposeResult:
        yield self.input
        yield self.suggestions

    def update_suggestions(self, entries: list[PaletteEntry]) -> None:
        """Render fuzzy suggestions below the command input."""

        self._pending_entries = list(entries)
        if not entries:
            self.clear_suggestions()
            return
        self._render_suggestions(self._pending_entries)

    def clear_suggestions(self) -> None:
        self._pending_entries.clear()
        if self.suggestions.is_attached:
            self.suggestions.clear()
        else:
            self.suggestions._nodes._clear()
        self.suggestions.add_class("hidden")

    def _render_suggestions(self, entries: list[PaletteEntry]) -> None:
        if not entries:
            self.clear_suggestions()
            return
        items = [
            ListItem(Label(f"{entry.command} — {entry.hint}"), id=f"suggestion-{index}")
            for index, entry in enumerate(entries)
        ]
        for entry, item in zip(entries, items, strict=False):
            item.data = entry.command
        if self.suggestions.is_attached:
            self.suggestions.clear()
            self.suggestions.extend(items)
        else:
            self.suggestions._nodes._clear()
            for item in items:
                self.suggestions._add_child(item)
        self.suggestions.remove_class("hidden")

    @on(ListView.Selected, "#command-suggestions")
    def _suggestion_selected(self, event: ListView.Selected) -> None:
        item = event.item
        command = getattr(item, "data", None)
        if isinstance(command, str):
            self.post_message(self.SuggestionSelected(command))


class TelemetryBar(Static):
    """Persistent status bar showing resource usage."""

    cpu_usage: float = reactive(0.0)
    memory_usage: float = reactive(0.0)

    def render(self) -> RenderableType:  # pragma: no cover - trivial formatting
        return Text(
            f"CPU: {self.cpu_usage:4.1f}%  |  Memory: {self.memory_usage:4.1f}%",
            style="dim",
        )


class SessionsPanel(VortexPanel):
    """Render collaborator presence, locks, and checkpoints."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._content: Static | None = None
        self._pending: tuple[dict[str, dict], str | None, list[dict]] | None = None

    def compose(self) -> ComposeResult:
        self._content = Static("No collaborators yet", id="sessions-content")
        yield self._content

    def on_mount(self) -> None:
        if self._pending is not None:
            collaborators, lock_holder, checkpoints = self._pending
            self.update_sessions(
                collaborators, lock_holder=lock_holder, checkpoints=checkpoints
            )
            self._pending = None

    def update_sessions(
        self,
        collaborators: dict[str, dict],
        *,
        lock_holder: str | None,
        checkpoints: list[dict],
    ) -> None:
        if self._content is None or not self.is_attached or not self._content.is_attached:
            self._pending = (collaborators, lock_holder, checkpoints)
            return
        table = sessions_table(collaborators, lock_holder)
        if checkpoints:
            checkpoints_text = "\n".join(
                f"{item['identifier']}: {item['summary']}" for item in checkpoints[-5:]
            )
            table.caption = (table.caption or "") + f"\nCheckpoints: {checkpoints_text}"
        self._content.update(table)


class TeamPanel(VortexPanel):
    """Render connected nodes and roles for team collaboration."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._content: Static | None = None
        self._pending: tuple[Dict[str, Any], Dict[str, Any]] | None = None

    def compose(self) -> ComposeResult:
        self._content = Static("No team connected", id="team-content")
        yield self._content

    def on_mount(self) -> None:
        if self._pending:
            nodes, ledger = self._pending
            self.update_nodes(nodes, ledger)
            self._pending = None

    def update_nodes(self, nodes: Dict[str, Any], ledger: Dict[str, Any]) -> None:
        if self._content is None or not self.is_attached or not self._content.is_attached:
            self._pending = (nodes, ledger)
            return
        table = Table(title="Team", expand=True)
        table.add_column("Node")
        table.add_column("Role")
        table.add_column("Repos")
        table.add_column("Status")
        for node_id, details in nodes.items():
            repos = ", ".join(details.get("repositories", [])[:2])
            if len(details.get("repositories", [])) > 2:
                repos += ", …"
            status = "RO" if details.get("read_only") else "RW"
            table.add_row(details.get("name", node_id), details.get("role", "editor"), repos or "-", status)
        if ledger:
            caption = f"Tokens: {ledger.get('tokens', 0):.0f} • Minutes: {ledger.get('minutes', 0):.1f}"
            table.caption = caption
        self._content.update(table)


class AnalyticsPanel(VortexPanel):
    """Render KPIs and insights for the active session."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._content: Static | None = None
        self._pending: tuple[dict, list[str]] | None = None

    def compose(self) -> ComposeResult:
        self._content = Static("Analytics pending", id="analytics-content")
        yield self._content

    def on_mount(self) -> None:
        if self._pending is not None:
            summary, insights = self._pending
            self.update_summary(summary, insights)
            self._pending = None

    def update_summary(self, summary: dict, insights: list[str]) -> None:
        if self._content is None or not self.is_attached or not self._content.is_attached:
            self._pending = (summary, insights)
            return
        self._content.update(analytics_dashboard(summary, insights))


class ProjectDashboardPanel(VortexPanel):
    """Display milestones, pipelines, and governance health."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._content: Static | None = None
        self._pending: Dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        self._content = Static("Project dashboard pending", id="project-dashboard")
        yield self._content

    def on_mount(self) -> None:
        if self._pending is not None:
            self.update_dashboard(self._pending)
            self._pending = None

    def update_dashboard(self, payload: Dict[str, Any]) -> None:
        if self._content is None or not self.is_attached or not self._content.is_attached:
            self._pending = payload
            return
        milestones = payload.get("milestones", [])
        pipelines = payload.get("pipelines", [])
        governance = payload.get("governance", [])
        table = Table.grid(expand=True)
        table.add_column(justify="left")
        table.add_column(justify="left")
        milestone_table = Table(title="Milestones", expand=True)
        milestone_table.add_column("ID")
        milestone_table.add_column("Status")
        milestone_table.add_column("Due")
        for milestone in milestones[:5]:
            milestone_table.add_row(
                str(milestone.get("identifier") or milestone.get("name")),
                milestone.get("status", "planned"),
                milestone.get("due", "-"),
            )
        pipeline_table = Table(title="Pipelines", expand=True)
        pipeline_table.add_column("Name")
        pipeline_table.add_column("Summary")
        for entry in pipelines[:5]:
            pipeline_table.add_row(entry.get("pipeline", ""), entry.get("summary", ""))
        governance_table = Table(title="Governance", expand=True)
        governance_table.add_column("Check")
        governance_table.add_column("Status")
        for report in governance[:5]:
            for check in report.get("checks", []):
                governance_table.add_row(check.get("name", "policy"), check.get("status", "pass"))
        table.add_row(milestone_table, pipeline_table)
        table.add_row(governance_table, Text(payload.get("summary", "")))
        self._content.update(table)


class RootLayout(Container):
    """Overall layout container orchestrating sub-panels."""

    def __init__(self, root_path: Optional[Path] = None, *, settings: Optional[TUISettings] = None) -> None:
        super().__init__(id="root-layout")
        self._root_path = root_path or Path.cwd()
        self._settings = settings
        if settings and settings.high_contrast:
            self.add_class("high-contrast")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-row"):
            yield MainPanel(id="main-panel")
            with Vertical(id="side-panels"):
                yield ContextPanel(self._root_path)
                yield SessionsPanel(id="sessions-panel")
                yield TeamPanel(id="team-panel")
                yield OrgCenterPanel(id="org-panel")
                yield AnalyticsPanel(id="analytics-panel")
                yield ProjectDashboardPanel(id="project-panel")
                yield ActionsPanel(id="actions-panel")
        yield StatusPanel(id="status-panel")
        yield ToolPanel(id="tool-panel", classes="hidden")
        yield HelpPanel(id="help-panel", classes="hidden")
        yield CommandBar()
        yield TelemetryBar(id="telemetry-bar")
        yield Footer()


__all__ = [
    "ActionsPanel",
    "CommandBar",
    "ContextPanel",
    "HelpPanel",
    "MainPanel",
    "RootLayout",
    "SessionsPanel",
    "TeamPanel",
    "AnalyticsPanel",
    "OrgCenterPanel",
    "ProjectDashboardPanel",
    "StatusPanel",
    "TelemetryBar",
    "ToolPanel",
]
