import pytest

from vortex.performance.analytics import SessionAnalyticsStore


@pytest.mark.asyncio
async def test_analytics_reports_and_comparison(tmp_path):
    store = SessionAnalyticsStore(database=tmp_path / "analytics.sqlite")
    await store.register_session("s1", "Session 1", owner="alice")
    await store.record_session_event(
        "s1",
        "plan",
        metrics={"success": True, "duration": 1.2, "tokens": 120, "cost": 0.15},
        author="alice",
    )
    await store.record_session_event(
        "s1",
        "test",
        metrics={"success": False, "duration": 2.5, "tokens": 80, "cost": 0.2},
        author="alice",
    )
    summary = await store.session_summary("s1")
    assert summary["events"]
    report = await store.generate_report("s1")
    assert "timeline" in report

    await store.register_session("s2", "Session 2", owner="bob")
    await store.record_session_event("s2", "plan", metrics={"success": True}, author="bob")
    comparison = await store.compare_sessions("s1", "s2")
    assert "delta_success" in comparison

    insights = await store.insights("s1")
    assert any("Session" in item for item in insights)
