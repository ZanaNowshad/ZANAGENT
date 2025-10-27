from pathlib import Path

from vortex.org.knowledge_graph import OrgKnowledgeGraph
from vortex.org.ops_center import OrgOpsCenter
from vortex.performance import PerformanceMonitor
from vortex.performance.analytics import PerformanceAnalytics, TeamAnalyticsStore


def test_ops_center_aggregates(tmp_path: Path) -> None:
    monitor = PerformanceMonitor()
    analytics = PerformanceAnalytics(monitor)
    team_store = TeamAnalyticsStore(database=tmp_path / "teams.sqlite")
    graph = OrgKnowledgeGraph(database_path=tmp_path / "graph.sqlite")
    ops = OrgOpsCenter(analytics, team_store, graph, storage_dir=tmp_path)

    team_store._run_execute(  # type: ignore[attr-defined]
        "INSERT INTO team_entries(team_id, actor, event, tokens, minutes, cost, timestamp, metadata) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        ("team", "node", "build", 1200.0, 15.0, 0.42, 1.0, "{}"),
    )
    ops.record_pipeline_run("proj", "pipeline", True, 120.0)
    ops.record_pipeline_run("proj", "pipeline2", False, 150.0)
    snapshot = ops.aggregate()
    assert snapshot.pipelines == 2
    assert snapshot.nodes >= 1
    ops.record_alert("warning", "coverage low")
    alerts = ops.active_alerts()
    assert any(alert.message == "coverage low" for alert in alerts)
    table = ops.alerts_table()
    assert table.row_count >= 1
    health = ops.broadcast_health()
    assert "pipelines" in health
    assert list(ops.iter_events())

def test_ops_center_persistence(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    events = storage / "ops_metrics.jsonl"
    events.write_text(
        "\n".join(
            [
                '{"type": "alert", "data": {"level": "error", "message": "fail"}}',
                '{"type": "pipeline_run", "pipeline_id": "build", "project_id": "p", "success": false, "latency_ms": 10}',
            ]
        )
    )
    monitor = PerformanceMonitor()
    analytics = PerformanceAnalytics(monitor)
    team_store = TeamAnalyticsStore(database=tmp_path / "teams.sqlite")
    graph = OrgKnowledgeGraph(database_path=tmp_path / "graph.sqlite")
    ops = OrgOpsCenter(analytics, team_store, graph, storage_dir=storage)
    assert ops.active_alerts()
