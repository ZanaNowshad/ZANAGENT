"""Help panel renderables."""
from __future__ import annotations

from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .hotkeys import GLOBAL_HOTKEYS

CORE_COMMANDS = [
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
]

ACCESSIBILITY_COMMANDS = [
    ("/accessibility on|off", "Toggle announcements"),
    ("/accessibility verbosity minimal|normal|verbose", "Narration detail"),
    ("/accessibility narration on|off", "Screen-reader narration"),
    ("/accessibility contrast on|off", "High contrast palette"),
    ("/theme dark|light|high_contrast", "Switch visual theme"),
    ("/theme custom <path>", "Load theme overrides from disk"),
]

OPERATIONS_COMMANDS = [
    ("/settings", "Open the settings surface"),
    ("/lyra [prompt]", "Ask the Lyra inline assistant"),
    ("/doctor", "Run diagnostics for terminal compatibility"),
    ("/reload theme", "Reload theme files"),
    ("/quit", "Confirm exit and persist session"),
    ("/help", "Show this help overlay"),
]


def help_renderable() -> Panel:
    """Return a combined help renderable with hotkeys and commands."""

    hotkeys = Table(title="Global Hotkeys", show_edge=False, expand=True)
    hotkeys.add_column("Key")
    hotkeys.add_column("Action")
    for binding in GLOBAL_HOTKEYS:
        hotkeys.add_row(binding.key.upper(), binding.description or "")

    core = Table(title="Core Commands", show_edge=False, expand=True)
    core.add_column("Command")
    core.add_column("Description")
    for command, description in CORE_COMMANDS:
        core.add_row(command, description)

    accessibility = Table(title="Accessibility & Theming", show_edge=False, expand=True)
    accessibility.add_column("Command")
    accessibility.add_column("Description")
    for command, description in ACCESSIBILITY_COMMANDS:
        accessibility.add_row(command, description)

    operations = Table(title="Operations", show_edge=False, expand=True)
    operations.add_column("Command")
    operations.add_column("Description")
    for command, description in OPERATIONS_COMMANDS:
        operations.add_row(command, description)

    docs = Markdown(
        """
### Copyable Examples
```
/plan
/diff src/
/test -k planner
/accessibility narration on
/theme custom ~/.vortex/theme.toml
/lyra how do I mock asyncio tasks?
```

### Palette
Type `:` to open the palette. Start typing to fuzzy-search commands, tools, files, and tests.

### Accessibility
Use `/accessibility` or `--screen-reader` to enable narration. High-contrast palettes and plain-text summaries are WCAG AA compliant.
        """,
    )

    content = Group(hotkeys, core, accessibility, operations, docs)
    return Panel(content, title="Help & Shortcuts", border_style="cyan")


__all__ = ["help_renderable"]
