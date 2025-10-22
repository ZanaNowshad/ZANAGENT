import time

from vortex.ui_tui.analytics_panel import analytics_dashboard, analytics_trend_panel, sessions_table


def test_analytics_renderables() -> None:
    summary = {
        "kpis": {"events": 3, "cost": 1.2, "tokens": 400, "avg_duration": 0.5},
        "events": [
            {
                "kind": "plan",
                "count": 2,
                "successes": 2,
                "avg_duration": 1.0,
                "tokens": 100,
                "cost": 0.2,
            }
        ],
        "success_rate": 0.75,
        "timeline": {"plan": [(0.0, 1.0), (1.0, 2.0)]},
    }
    panel = analytics_dashboard(summary, ["All systems nominal."])
    assert hasattr(panel, "render")
    trend = analytics_trend_panel(summary["timeline"])
    assert hasattr(trend, "render")


def test_sessions_table_render() -> None:
    table = sessions_table(
        {
            "alice@host": {
                "user": "alice",
                "host": "host",
                "role": "owner",
                "read_only": False,
                "last_seen": time.time(),
            }
        },
        lock_holder=None,
    )
    assert table.row_count == 1
