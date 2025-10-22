"""Rich renderables for analytics and collaboration dashboards."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


def _sparkline(points: Sequence[float]) -> str:
    if not points:
        return ""
    low = min(points)
    high = max(points)
    if high - low < 1e-9:
        return SPARK_BLOCKS[0] * len(points)
    scale = len(SPARK_BLOCKS) - 1
    blocks: list[str] = []
    for value in points:
        normalised = int(round((value - low) / (high - low) * scale))
        blocks.append(SPARK_BLOCKS[normalised])
    return "".join(blocks)


@dataclass
class _PanelRenderable:
    """Base wrapper exposing ``render`` for unit test helpers."""

    panel: Panel

    def render(self) -> RenderableType:
        return self.panel

    def __rich__(self) -> RenderableType:  # pragma: no cover - passthrough
        return self.panel


class AnalyticsDashboardRenderable(_PanelRenderable):
    """Analytics dashboard renderable wrapper."""


class AnalyticsTrendRenderable(_PanelRenderable):
    """Timeline renderable wrapper."""


def analytics_kpi_table(kpis: Dict[str, float]) -> Table:
    table = Table(title="Key Performance Indicators", show_edge=False, expand=True)
    table.add_column("Metric", justify="left")
    table.add_column("Value", justify="right")
    for key, value in sorted(kpis.items()):
        if key == "events":
            table.add_row("Events", f"{value:.0f}")
        elif key == "cost":
            table.add_row("Cost", f"${value:.2f}")
        elif key == "tokens":
            table.add_row("Tokens", f"{value:.0f}")
        elif key == "avg_duration":
            table.add_row("Avg Duration", f"{value:.2f}s")
        else:
            table.add_row(key.replace("_", " ").title(), f"{value:.2f}")
    return table


def analytics_event_table(events: Iterable[Dict[str, float]]) -> Table:
    table = Table(title="Activity Mix", expand=True)
    table.add_column("Kind")
    table.add_column("Count", justify="right")
    table.add_column("Success", justify="right")
    table.add_column("Avg Duration", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost", justify="right")
    for entry in events:
        table.add_row(
            str(entry.get("kind", "")),
            f"{entry.get('count', 0):.0f}",
            f"{entry.get('successes', 0):.0f}",
            f"{entry.get('avg_duration', 0.0):.2f}s",
            f"{entry.get('tokens', 0.0):.0f}",
            f"${entry.get('cost', 0.0):.2f}",
        )
    return table


def analytics_dashboard(
    summary: Dict[str, Any], insights: List[str]
) -> AnalyticsDashboardRenderable:
    kpi = analytics_kpi_table(summary.get("kpis", {}))
    events = analytics_event_table(summary.get("events", []))
    insight_block = Text("\n".join(insights) or "No insights yet.", style="italic")
    renderable = Group(kpi, Rule(style="dim"), events, Rule(style="dim"), insight_block)
    title = f"Session Analytics — success {summary.get('success_rate', 0.0)*100:.1f}%"
    panel = Panel(renderable, title=title, border_style="cyan")
    return AnalyticsDashboardRenderable(panel)


def analytics_trend_panel(series: Dict[str, List[Tuple[float, float]]]) -> AnalyticsTrendRenderable:
    table = Table(title="Timeline", show_edge=False, expand=True)
    table.add_column("Event")
    table.add_column("Trend")
    for name, points in series.items():
        spark = _sparkline([value for _, value in points])
        table.add_row(name, spark)
    panel = Panel(table, border_style="magenta")
    return AnalyticsTrendRenderable(panel)


def sessions_table(collaborators: Dict[str, Dict[str, Any]], lock_holder: str | None) -> Table:
    table = Table(title="Collaborators", expand=True)
    table.add_column("Identity")
    table.add_column("Role")
    table.add_column("Access")
    table.add_column("Last Seen")
    for key, entry in sorted(collaborators.items()):
        access = "Read-only" if entry.get("read_only") else "Read/Write"
        last_seen = entry.get("last_seen", 0.0)
        table.add_row(
            key,
            str(entry.get("role", "collaborator")),
            access,
            time_ago(last_seen),
        )
    if lock_holder:
        table.caption = f"Active lock: {lock_holder}"
    return table


def time_ago(timestamp: float) -> str:
    if not timestamp:
        return "unknown"
    delta = max(0.0, time.time() - float(timestamp))
    if delta < 60:
        return f"{delta:.0f}s ago"
    if delta < 3600:
        return f"{delta/60:.1f}m ago"
    return f"{delta/3600:.1f}h ago"


__all__ = [
    "AnalyticsDashboardRenderable",
    "AnalyticsTrendRenderable",
    "analytics_dashboard",
    "analytics_trend_panel",
    "analytics_kpi_table",
    "analytics_event_table",
    "sessions_table",
]
