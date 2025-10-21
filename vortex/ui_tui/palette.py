"""Command palette definitions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from .context import TUISessionState


@dataclass
class PaletteEntry:
    """Describes a palette option rendered in the command bar."""

    label: str
    hint: str
    command: str

    def matches(self, query: str) -> bool:
        query_lower = query.lower()
        return query_lower in self.label.lower() or query_lower in self.hint.lower()


BASE_ENTRIES: List[PaletteEntry] = [
    PaletteEntry(label="Plan", hint="Generate an execution plan", command="/plan"),
    PaletteEntry(label="Apply", hint="Apply the current diff", command="/apply"),
    PaletteEntry(label="Undo", hint="Undo the last checkpoint", command="/undo"),
    PaletteEntry(label="Diff", hint="Show workspace diff", command="/diff"),
    PaletteEntry(label="Run Tests", hint="Execute pytest", command="/test"),
    PaletteEntry(label="Add Context", hint="Ingest a file", command="/ctx add"),
    PaletteEntry(label="Open Help", hint="Toggle help panel", command="/help"),
    PaletteEntry(label="Toggle Auto", hint="Configure autonomous steps", command="/auto"),
]


def iter_palette_entries(state: TUISessionState) -> Iterable[PaletteEntry]:
    """Yield palette entries including dynamic history items."""

    yield from BASE_ENTRIES
    for item in state.palette_history:
        yield PaletteEntry(label=f"Recent: {item}", hint="Recently executed", command=item)


__all__ = ["PaletteEntry", "iter_palette_entries"]
