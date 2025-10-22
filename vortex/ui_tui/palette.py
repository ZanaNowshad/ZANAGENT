"""Command palette definitions."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any, Iterable, List

try:  # pragma: no cover - optional dependency for fuzzy scoring
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - fallback when rapidfuzz unavailable
    fuzz = None  # type: ignore[assignment]

from .context import TUISessionState


@dataclass
class PaletteEntry:
    """Describes a palette option rendered in the command bar."""

    label: str
    hint: str
    command: str
    category: str = "command"

    def matches(self, query: str) -> bool:
        query_lower = query.lower()
        return query_lower in self.label.lower() or query_lower in self.hint.lower()

    def score(self, query: str) -> int:
        if not query:
            return 100
        if fuzz is None:
            return 80 if self.matches(query) else 0
        return int(
            max(
                fuzz.partial_ratio(query, self.label),
                fuzz.partial_ratio(query, self.command),
                fuzz.partial_ratio(query, self.hint),
            )
        )


BASE_ENTRIES: List[PaletteEntry] = [
    PaletteEntry(label="Plan", hint="Generate an execution plan", command="/plan"),
    PaletteEntry(label="Apply", hint="Apply the current diff", command="/apply"),
    PaletteEntry(label="Undo", hint="Undo the last checkpoint", command="/undo"),
    PaletteEntry(label="Diff", hint="Show workspace diff", command="/diff"),
    PaletteEntry(label="Run Tests", hint="Execute pytest", command="/test"),
    PaletteEntry(label="Add Context", hint="Ingest a file", command="/ctx add"),
    PaletteEntry(label="Open Help", hint="Toggle help panel", command="/help"),
    PaletteEntry(label="Toggle Auto", hint="Configure autonomous steps", command="/auto"),
    PaletteEntry(label="Toggle Accessibility", hint="Enable announcements", command="/accessibility on"),
    PaletteEntry(label="Narration On", hint="Screen reader narration", command="/accessibility narration on"),
    PaletteEntry(label="High Contrast", hint="Screen reader contrast", command="/accessibility contrast on"),
    PaletteEntry(label="Theme", hint="Switch between dark, light, high contrast", command="/theme dark"),
    PaletteEntry(label="Custom Theme", hint="Load theme from file", command="/theme custom ~/.vortex/theme.toml"),
    PaletteEntry(label="Settings", hint="Open settings wizard", command="/settings"),
    PaletteEntry(label="Lyra Assistant", hint="Ask the Lyra inline helper", command="/lyra"),
    PaletteEntry(label="Diagnostics", hint="Run environment checks", command="/doctor"),
    PaletteEntry(label="Quit", hint="Confirm and exit", command="/quit"),
]


def iter_palette_entries(state: TUISessionState, runtime: Any | None = None) -> Iterable[PaletteEntry]:
    """Yield palette entries including dynamic history items."""

    yield from BASE_ENTRIES
    for item in state.palette_history:
        yield PaletteEntry(label=f"Recent: {item}", hint="Recently executed", command=item)
    if runtime is not None:
        plugins = getattr(runtime, "plugins", None)
        if plugins is not None:
            try:
                for name in sorted(plugins.discover().keys()):
                    yield PaletteEntry(
                        label=f"Tool: {name}",
                        hint="Invoke tool",
                        command=f"/tool {name}",
                        category="tool",
                    )
            except Exception:  # pragma: no cover - plugin discovery failures are tolerated
                pass
        repo_root = Path.cwd()
        for path in islice(repo_root.rglob("*"), 40):
            if path.is_file():
                rel = path.relative_to(repo_root)
                yield PaletteEntry(
                    label=f"File: {rel}",
                    hint="Open diff for file",
                    command=f"/diff {rel}",
                    category="file",
                )


def search_entries(
    state: TUISessionState, query: str, runtime: Any | None = None, *, limit: int = 10
) -> List[PaletteEntry]:
    """Return palette entries ordered by fuzzy score."""

    entries = list(iter_palette_entries(state, runtime))
    scored = [(entry.score(query), entry) for entry in entries]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for score, entry in scored if score > 0][:limit]


__all__ = ["PaletteEntry", "iter_palette_entries", "search_entries"]
