import asyncio
import base64
from pathlib import Path

import pytest

from vortex.agents import TeamManager


async def _await_kind(queue: asyncio.Queue, kind: str) -> dict:
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=2)
        if event.get("kind") == kind:
            return event


@pytest.mark.asyncio
async def test_cross_repo_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = base64.urlsafe_b64encode(b"2" * 32).decode("utf-8")
    monkeypatch.setenv("VORTEX_AGENT_KEY", key)
    host = TeamManager(root=tmp_path / "host")
    await host.join(None, capabilities={"repos": True}, team_id="gamma")
    peer = TeamManager(root=tmp_path / "peer")
    await peer.join(host.broker_uri, capabilities={"repos": True})
    queue = host.subscribe()
    await peer.attach_repo("repo-alpha", path=str(tmp_path / "repo-alpha"))
    event = await _await_kind(queue, "attach")
    assert event["repo"] == "repo-alpha"
    await peer.handoff("repo-alpha", "run integration tests", target=host.node_id)
    handoff_event = await _await_kind(queue, "handoff")
    assert handoff_event["repo"] == "repo-alpha"
    await peer.leave()
    await host.leave()
