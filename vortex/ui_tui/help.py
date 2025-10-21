"""Help panel renderables."""
from __future__ import annotations

from rich.console import Group
from rich.markdown import Markdown
from rich.table import Table

from .hotkeys import GLOBAL_HOTKEYS

SLASH_COMMANDS = [
    ("/plan", "Generate a dependency-aware execution plan"),
    ("/apply", "Create a checkpoint from the current diff"),
    ("/undo [id]", "Revert to a previous checkpoint"),
    ("/diff [path]", "Display workspace diff"),
    ("/test -k expr", "Run pytest with a keyword filter"),
    ("/ctx add <path>", "Attach a file to the working context"),
    ("/tool <name> {json}", "Invoke a registered tool"),
    ("/mode <chat|fix|gen|review|run>", "Switch the main panel mode"),
    ("/budget <value>", "Update the session budget (minutes)"),
    ("/auto <n>", "Configure autonomous step count"),
    ("/help", "Show this help overlay"),
]


def help_renderable() -> Group:
    """Return a combined help renderable with hotkeys and commands."""

    table = Table(title="Global Hotkeys", show_edge=False, expand=True)
    table.add_column("Key")
    table.add_column("Action")
    for binding in GLOBAL_HOTKEYS:
        table.add_row(binding.key.upper(), binding.description or "")

    cmd_table = Table(title="Slash Commands", show_edge=False, expand=True)
    cmd_table.add_column("Command")
    cmd_table.add_column("Description")
    for command, description in SLASH_COMMANDS:
        cmd_table.add_row(command, description)

    docs = Markdown(
        """
### Copyable Examples
```
/plan
/diff src/
/test -k planner
/mode review
```
        """
    )

    return Group(table, cmd_table, docs)


__all__ = ["help_renderable"]
