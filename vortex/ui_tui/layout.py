"""Layout helpers for composing the Textual app."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .panels import RootLayout
from .settings import TUISettings


def build_layout(
    root_path: Path | None = None, settings: Optional[TUISettings] = None
) -> RootLayout:
    """Return the root layout widget configured for the current session."""

    return RootLayout(root_path, settings=settings)


__all__ = ["build_layout"]
