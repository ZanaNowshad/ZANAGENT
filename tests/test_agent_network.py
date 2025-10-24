import asyncio
import base64
from pathlib import Path

import pytest

from vortex.agents import TeamManager
from vortex.agents.protocol import AgentServer


async def _wait_for_kind(queue: asyncio.Queue, kind: str) -> dict:
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=2)
        if event.get("kind") == kind:
            return event


@pytest.mark.asyncio
async def test_agent_network_join_and_broadcast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = base64.urlsafe_b64encode(b"0" * 32).decode("utf-8")
    monkeypatch.setenv("VORTEX_AGENT_KEY", key)
    host = TeamManager(root=tmp_path / "host")
    state = await host.join(None, capabilities={"tests": True}, team_id="alpha")
    assert state.team_id
    peer = TeamManager(root=tmp_path / "peer")
    await peer.join(host.broker_uri, capabilities={"tests": True})
    queue = peer.subscribe()
    host_queue = host.subscribe()

    # Broadcast events flow to collaborators.
    await host.broadcast("message", {"text": "hello"})
    event = await _wait_for_kind(queue, "broadcast")
    assert event["payload"]["text"] == "hello"

    await host.attach_repo("repo-one", path=str(tmp_path / "repo-one"))
    attachments = host.state().attachments
    assert attachments.get("repo-one") == host.node_id
    attach_event = await _wait_for_kind(host_queue, "attach")
    assert attach_event["repo"] == "repo-one"

    await host.handoff("repo-one", "Verify plan", target=peer.node_id)
    handoff = await _wait_for_kind(host_queue, "handoff")
    assert handoff["repo"] == "repo-one"

    # Mode updates round-trip through the broker to all listeners.
    await host.set_mode("review")
    mode_event = await _wait_for_kind(host_queue, "mode")
    assert mode_event["mode"] == "review"

    # Exercise direct RPC paths for mode and heartbeat for coverage.
    raw = await host._connection.request("mode", {"mode": "sync"})
    assert isinstance(raw, dict)
    assert raw["result"]["status"] == "ok"
    await host._connection.request("heartbeat", {"node_id": host.node_id})

    # Recording budget entries persists to the ledger and analytics store.
    await host.record_budget(tokens=10.0, minutes=3.0, reason="setup", actor="host")
    ledger = await host.ledger_summary()
    assert ledger["total_tokens"] >= 10.0
    metrics = await host.team_metrics()
    assert metrics["total_tokens"] >= 10.0
    insights = await host.insights()
    assert insights  # at least one insight emitted

    # Direct protocol broadcasts reach all connections without raising.
    await host._protocol.broadcast("team.event", {"kind": "noop"})

    await peer.leave()
    await host.leave()


@pytest.mark.asyncio
async def test_agent_server_close_handles_awaitable() -> None:
    class _StubServer:
        def __init__(self) -> None:
            self.closed = False
            self.wait_closed = asyncio.get_event_loop().create_future()
            self.wait_closed.set_result(None)

        def close(self) -> None:
            self.closed = True

    server = _StubServer()
    agent_server = AgentServer(server)
    await agent_server.close()
    assert server.closed
