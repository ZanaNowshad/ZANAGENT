"""Central definition of keyboard bindings."""
from __future__ import annotations

from textual.binding import Binding


GLOBAL_HOTKEYS = [
    Binding("tab", "focus_next", "Next Panel"),
    Binding("shift+tab", "focus_previous", "Previous Panel"),
    Binding("j", "list_down", "Down"),
    Binding("k", "list_up", "Up"),
    Binding("g", "list_top", "Top"),
    Binding("G", "list_bottom", "Bottom"),
    Binding("h", "diff_prev_hunk", "Prev Hunk"),
    Binding("l", "diff_next_hunk", "Next Hunk"),
    Binding("enter", "list_activate", "Activate"),
    Binding("a", "action_apply", "Apply"),
    Binding("u", "action_undo", "Undo"),
    Binding("p", "action_plan", "Plan"),
    Binding("s", "action_simulate", "Simulate"),
    Binding("t", "tools_toggle", "Tools"),
    Binding("T", "action_test", "Run Tests"),
    Binding(":", "palette_open", "Command Palette"),
    Binding("/", "slash_focus", "Slash Command"),
    Binding("?", "help_toggle", "Help"),
]


def bindings_for_app() -> list[Binding]:
    """Return the bindings list used by :class:`~textual.app.App`."""

    return list(GLOBAL_HOTKEYS)


__all__ = ["GLOBAL_HOTKEYS", "bindings_for_app"]
