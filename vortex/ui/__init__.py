"""User interface adapters."""

from __future__ import annotations

from vortex.ui.desktop import DesktopGUI
from vortex.ui.mobile import MobileAPI
from vortex.ui.rich_ext import RichUIBridge
from vortex.ui.web import WebUI

__all__ = ["DesktopGUI", "MobileAPI", "RichUIBridge", "WebUI"]
