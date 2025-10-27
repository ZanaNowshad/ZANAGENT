import asyncio
from pathlib import Path

from vortex.performance.analytics import OrgAnalyticsEngine, SessionAnalyticsStore, TeamAnalyticsStore


def test_org_analytics_snapshot(tmp_path: Path) -> None:
    session_store = SessionAnalyticsStore(database=tmp_path / "sessions.sqlite")
    team_store = TeamAnalyticsStore(database=tmp_path / "teams.sqlite")
    engine = OrgAnalyticsEngine(session_store, team_store)
    snapshot = asyncio.run(engine.snapshot())
    assert snapshot.to_dict()["teams"] >= 0
