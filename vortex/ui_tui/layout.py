"""Layout helpers for composing the Textual app."""
from __future__ import annotations

from pathlib import Path

from .panels import RootLayout


def build_layout(root_path: Path | None = None) -> RootLayout:
    """Return the root layout widget.

    The helper keeps ``App.compose`` tidy and allows tests to instantiate the
    layout independently of the running application.
    """

    return RootLayout(root_path)


__all__ = ["build_layout"]
