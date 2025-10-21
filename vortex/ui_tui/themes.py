"""Theme definitions and helpers for the TUI."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

try:  # pragma: no cover - tomllib optional import guard
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ThemeDefinition:
    """Declarative representation of a theme."""

    name: str
    css: str


BASE_THEMES: Dict[str, ThemeDefinition] = {
    "dark": ThemeDefinition(
        name="dark",
        css="""
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
    ),
    "light": ThemeDefinition(
        name="light",
        css="""
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
    ),
    "high_contrast": ThemeDefinition(
        name="high_contrast",
        css="""
Screen {
    background: #000000;
    color: #ffffff;
}

#main-panel, #context-panel, #actions-panel, #status-panel, #tool-panel, #help-panel {
    border: round #ffffff;
    background: #000000;
}

.hidden {
    display: none;
}
""",
    ),
    "mono": ThemeDefinition(
        name="mono",
        css="""
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
    ),
}


class ThemeError(RuntimeError):
    """Raised when a custom theme cannot be loaded."""


def theme_css(mode: str, *, no_color: bool, high_contrast: bool = False, custom: Path | None = None) -> str:
    """Return CSS for the requested theme with fallbacks.

    ``mode`` accepts ``dark`` or ``light``; ``auto`` defaults to ``dark``. When
    ``no_color`` is ``True`` we fall back to a monochrome palette compatible with
    16-colour terminals. High contrast toggles override the requested mode.
    ``custom`` allows operators to load a TOML/YAML palette with the following
    structure::

        [palette.screen]
        background = "#000000"
        color = "#ffffff"

        [palette.panels.main]
        border = "#ffffff"
        background = "#000000"

    Only a subset of keys are required; missing values inherit from the base
    theme ensuring partial overrides remain ergonomic.
    """

    if no_color:
        return BASE_THEMES["mono"].css
    if custom is not None:
        try:
            return _load_custom_theme(custom)
        except Exception as exc:  # pragma: no cover - runtime configuration errors
            raise ThemeError(str(exc)) from exc
    if high_contrast:
        return BASE_THEMES["high_contrast"].css
    mode = mode if mode in {"dark", "light"} else "dark"
    return BASE_THEMES[mode].css


def _load_custom_theme(path: Path) -> str:
    data = _read_palette(path)
    if not data:
        raise ThemeError(f"Custom theme {path} is empty")
    base = BASE_THEMES["dark"].css
    palette = data.get("palette") or {}
    css = _merge_palette(base, palette)
    _validate_contrast(css)
    return css


def _read_palette(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ThemeError(f"Custom theme {path} does not exist")
    if path.suffix in {".yaml", ".yml"}:
        return yaml.safe_load(path.read_text()) or {}
    if path.suffix == ".toml" and tomllib is not None:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    raise ThemeError("Unsupported theme format; use TOML or YAML")


def _merge_palette(base_css: str, palette: Dict[str, Any]) -> str:
    screen = palette.get("screen", {})
    panels = palette.get("panels", {})
    main = panels.get("main", {})
    context = panels.get("context", {})
    actions = panels.get("actions", {})
    status = panels.get("status", {})
    tool = panels.get("tool", {})
    help_panel = panels.get("help", {})
    replacements = {
        "SCREEN_BACKGROUND": screen.get("background", "#0f1117"),
        "SCREEN_COLOR": screen.get("color", "#f5f7ff"),
        "MAIN_BORDER": main.get("border", "#4f46e5"),
        "MAIN_BACKGROUND": main.get("background", "#111827"),
        "CONTEXT_BORDER": context.get("border", "#2563eb"),
        "CONTEXT_BACKGROUND": context.get("background", "#0b1220"),
        "ACTIONS_BORDER": actions.get("border", "#7c3aed"),
        "ACTIONS_BACKGROUND": actions.get("background", "#141826"),
        "STATUS_BORDER": status.get("border", "#1f2937"),
        "STATUS_BACKGROUND": status.get("background", "#0f172a"),
        "TOOL_BORDER": tool.get("border", "#0891b2"),
        "TOOL_BACKGROUND": tool.get("background", "#082f49"),
        "HELP_BORDER": help_panel.get("border", "#0891b2"),
        "HELP_BACKGROUND": help_panel.get("background", "#082f49"),
    }
    template = """
Screen {
    background: SCREEN_BACKGROUND;
    color: SCREEN_COLOR;
}

#main-panel {
    border: heavy MAIN_BORDER;
    background: MAIN_BACKGROUND;
}

#context-panel {
    border: round CONTEXT_BORDER;
    background: CONTEXT_BACKGROUND;
}

#actions-panel {
    border: round ACTIONS_BORDER;
    background: ACTIONS_BACKGROUND;
}

#status-panel {
    border: round STATUS_BORDER;
    background: STATUS_BACKGROUND;
}

#tool-panel {
    border: round TOOL_BORDER;
    background: TOOL_BACKGROUND;
}

#help-panel {
    border: round HELP_BORDER;
    background: HELP_BACKGROUND;
}

.hidden {
    display: none;
}
"""
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def _validate_contrast(css: str) -> None:
    background = _extract_color(css, "background")
    foreground = _extract_color(css, "color")
    if background and foreground:
        ratio = _contrast_ratio(background, foreground)
        if ratio < 4.5:  # WCAG AA threshold
            raise ThemeError(
                f"Theme contrast ratio {ratio:.2f} is below WCAG AA requirements"
            )


def _extract_color(css: str, token: str) -> Optional[str]:
    for line in css.splitlines():
        line = line.strip()
        if line.startswith(f"{token}:"):
            value = line.split(":", 1)[1].strip().rstrip(";")
            if value.startswith("#"):
                return value
    return None


def _contrast_ratio(color_a: str, color_b: str) -> float:
    def luminance(hex_color: str) -> float:
        rgb = tuple(int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
        linear = [
            component / 12.92 if component <= 0.03928 else ((component + 0.055) / 1.055) ** 2.4
            for component in rgb
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lum1 = luminance(color_a)
    lum2 = luminance(color_b)
    lighter, darker = max(lum1, lum2), min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)


__all__ = ["BASE_THEMES", "ThemeDefinition", "ThemeError", "theme_css"]
