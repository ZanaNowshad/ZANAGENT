import asyncio
from pathlib import Path

import pytest

from vortex.core.ui import UnifiedRichUI
from vortex.security.manager import UnifiedSecurityManager
from vortex.ui import DesktopGUI, MobileAPI, RichUIBridge, WebUI


@pytest.mark.asyncio
async def test_mobile_api_permission(tmp_path: Path) -> None:
    security = UnifiedSecurityManager(
        credential_dir=tmp_path,
        allowed_modules=["json"],
        forbidden_modules=[],
    )
    security.permissions.grant("tester", {"mobile:ping"})
    api = MobileAPI(security)
    response = await api.dispatch("tester", "ping", {"hello": "world"})
    assert "hello" in response


@pytest.mark.asyncio
async def test_web_ui_serves_request(tmp_path: Path) -> None:
    security = UnifiedSecurityManager(
        credential_dir=tmp_path,
        allowed_modules=["json"],
        forbidden_modules=[],
    )
    web = WebUI()

    async def status(_method: str) -> str:
        return "{\"ok\": true}"

    web.route("/status", status)
    payload = await web.simulate("GET", "/status")
    assert "\"ok\": true" in payload


def test_rich_bridge_and_desktop_gui() -> None:
    ui = UnifiedRichUI(enable_progress=False)
    bridge = RichUIBridge(ui)
    bridge.render_table("Title", ["A"], [["1"]])
    desktop = DesktopGUI()
    desktop.render("Dash", {"Panel": "Content"})
