import asyncio
import socket
from pathlib import Path

import pytest

from vortex.performance.analytics import SessionAnalyticsStore
from vortex.ui_tui.session_manager import SessionManager


@pytest.mark.asyncio
async def test_session_manager_broadcast_and_share(tmp_path: Path) -> None:
    analytics = SessionAnalyticsStore(database=tmp_path / "analytics.sqlite")
    manager = SessionManager(root=tmp_path / "sessions", analytics=analytics)

    metadata = await manager.create_session("Collab", "alice")
    sessions = await manager.list_sessions()
    assert metadata.session_id in {item.session_id for item in sessions}

    await manager.join_session(metadata.session_id, "bob", role="reviewer")
    iterator = await manager.subscribe(metadata.session_id)

    await manager.broadcast(
        metadata.session_id,
        "plan",
        {"summary": "Plan drafted"},
        author=f"alice@{socket.gethostname()}",
        metrics={"success": True, "duration": 0.1},
    )

    event = await asyncio.wait_for(iterator.__anext__(), timeout=2)
    assert event.kind == "plan"

    details = await manager.session_details(metadata.session_id)
    assert len(details["collaborators"]) == 2

    summary = await manager.analytics_snapshot(metadata.session_id)
    assert summary["events"]

    token = await manager.share_session(metadata.session_id, role="observer", read_only=True)
    session_id, role, read_only = manager.parse_share_token(token)
    assert session_id == metadata.session_id
    assert role == "observer"
    assert read_only is True
