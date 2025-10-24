import asyncio
import base64
from pathlib import Path

import pytest

from vortex.agents import TeamManager


@pytest.mark.asyncio
async def test_team_budget_tracking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = base64.urlsafe_b64encode(b"1" * 32).decode("utf-8")
    monkeypatch.setenv("VORTEX_AGENT_KEY", key)
    manager = TeamManager(root=tmp_path / "team")
    await manager.join(None, capabilities={"budget": True}, team_id="beta")
    await manager.record_budget(tokens=120.0, minutes=45.0, reason="plan", actor="node-a")
    await manager.record_budget(tokens=30.0, minutes=15.0, reason="tests", actor="node-b")
    summary = await manager.ledger_summary()
    assert summary["total_tokens"] == pytest.approx(150.0)
    assert summary["total_minutes"] == pytest.approx(60.0)
    metrics = await manager.team_metrics()
    assert metrics["total_tokens"] >= 150.0
    insights = await manager.insights()
    assert insights
    await manager.leave()


@pytest.mark.asyncio
async def test_team_manager_offline_operations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VORTEX_AGENT_KEY", raising=False)
    manager = TeamManager(root=tmp_path / "offline")
    assert manager.state() is None
    queue = manager.subscribe()
    await manager.attach_repo("docs", path=str(tmp_path / "docs"))
    attach_event = await asyncio.wait_for(queue.get(), timeout=1)
    assert attach_event["repo"] == "docs"
    await manager.record_budget(tokens=5.0, minutes=2.0, reason="offline", actor="solo")
    ledger = await manager.ledger_summary()
    assert ledger["entries"]
