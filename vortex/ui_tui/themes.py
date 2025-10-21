"""Theme definitions for the TUI."""
from __future__ import annotations

THEMES: dict[str, str] = {
    "dark": """
Screen {
    background: #0f1117;
    color: #f5f7ff;
}

#main-panel {
    border: heavy #4f46e5;
    background: #111827;
}

#context-panel {
    border: round #2563eb;
    background: #0b1220;
}

#actions-panel {
    border: round #7c3aed;
    background: #141826;
}

#status-panel {
    border: round #1f2937;
    background: #0f172a;
}

#tool-panel, #help-panel {
    border: round #0891b2;
    background: #082f49;
}

.hidden {
    display: none;
}
""",
    "light": """
Screen {
    background: #f8fafc;
    color: #020617;
}

#main-panel {
    border: heavy #2563eb;
    background: #e2e8f0;
}

#context-panel {
    border: round #0ea5e9;
    background: #e0f2fe;
}

#actions-panel {
    border: round #7c3aed;
    background: #ede9fe;
}

#status-panel {
    border: round #1f2937;
    background: #e2e8f0;
}

#tool-panel, #help-panel {
    border: round #0891b2;
    background: #cffafe;
}

.hidden {
    display: none;
}
""",
    "mono": """
Screen {
    background: black;
    color: white;
}

#main-panel, #context-panel, #actions-panel, #status-panel, #tool-panel, #help-panel {
    border: round white;
    background: black;
}

.hidden {
    display: none;
}
""",
}


def theme_css(mode: str, *, no_color: bool) -> str:
    """Return CSS for the requested theme.

    ``mode`` accepts ``dark`` or ``light``; ``auto`` defaults to ``dark`` as the
    majority of terminal-first users work in dark environments. When
    ``no_color`` is ``True`` we fall back to a monochrome palette that renders
    correctly even on 16-colour terminals.
    """

    if no_color:
        return THEMES["mono"]
    if mode not in {"dark", "light"}:
        mode = "dark"
    return THEMES[mode]


__all__ = ["theme_css", "THEMES"]
