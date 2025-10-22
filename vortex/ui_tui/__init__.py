"""Terminal user interface package for Vortex."""

from __future__ import annotations

from .context import TUIOptions
from .settings import TUISettings

try:  # pragma: no cover - optional dependency for headless test environments
    from .app import VortexTUI, launch_tui
except ModuleNotFoundError:  # pragma: no cover - textual not installed
    VortexTUI = None  # type: ignore[assignment]

    async def launch_tui(*_: object, **__: object) -> None:  # type: ignore[override]
        raise RuntimeError("Textual is required for the Vortex TUI")


__all__ = ["VortexTUI", "launch_tui", "TUIOptions", "TUISettings"]
