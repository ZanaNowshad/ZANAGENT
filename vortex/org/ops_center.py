"""Organisation-wide operational monitoring."""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List

from rich.table import Table

from vortex.performance import PerformanceAnalytics
from vortex.performance.analytics import TeamAnalyticsStore
from vortex.utils.logging import get_logger

from .knowledge_graph import OrgKnowledgeGraph

logger = get_logger(__name__)


@dataclass
class OpsAlert:
    """Represents a critical signal surfaced by the ops centre."""

    level: str
    message: str
    created_at: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> Dict[str, Any]:
        return {"level": self.level, "message": self.message, "created_at": self.created_at}


@dataclass
class OpsSnapshot:
    """Aggregated metrics view."""

    nodes: int
    pipelines: int
    incidents: int
    avg_latency_ms: float
    token_cost: float
    alerts: List[OpsAlert]

    def to_table(self) -> Table:
        table = Table(title="Org Operations", caption="Aggregated metrics across teams")
        table.add_column("Metric")
        table.add_column("Value")
        table.add_row("Nodes", str(self.nodes))
        table.add_row("Pipelines", str(self.pipelines))
        table.add_row("Incidents", str(self.incidents))
        table.add_row("Latency (ms)", f"{self.avg_latency_ms:.2f}")
        table.add_row("Token Cost", f"${self.token_cost:.2f}")
        table.add_row("Active Alerts", str(len(self.alerts)))
        return table


class OrgOpsCenter:
    """Collect metrics, surface alerts, and drive organisation-wide visibility."""

    def __init__(
        self,
        analytics: PerformanceAnalytics,
        team_store: TeamAnalyticsStore,
        knowledge_graph: OrgKnowledgeGraph,
        storage_dir: Path | None = None,
    ) -> None:
        self._analytics = analytics
        self._team_store = team_store
        self._graph = knowledge_graph
        self._storage = storage_dir or Path.home() / ".vortex" / "org"
        self._storage.mkdir(parents=True, exist_ok=True)
        self._events_file = self._storage / "ops_metrics.jsonl"
        self._alerts: List[OpsAlert] = []
        self._load_existing_alerts()

    # -- persistence -------------------------------------------------------------
    def _load_existing_alerts(self) -> None:
        if not self._events_file.exists():
            return
        for line in self._events_file.read_text().splitlines():
            try:
                payload = json.loads(line)
                if payload.get("type") == "alert":
                    self._alerts.append(
                        OpsAlert(
                            level=payload["data"]["level"],
                            message=payload["data"]["message"],
                            created_at=payload["data"].get("created_at", time.time()),
                        )
                    )
            except json.JSONDecodeError:
                logger.warning("Failed to parse stored ops alert", extra={"line": line})

    def _append_event(self, event: Dict[str, Any]) -> None:
        with self._events_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

    # -- recording ---------------------------------------------------------------
    def record_pipeline_run(self, project_id: str, pipeline_id: str, success: bool, latency_ms: float) -> None:
        level = "warning" if not success else "info"
        event = {
            "type": "pipeline_run",
            "project_id": project_id,
            "pipeline_id": pipeline_id,
            "success": success,
            "latency_ms": latency_ms,
            "timestamp": time.time(),
        }
        self._append_event(event)
        if not success:
            self._alerts.append(OpsAlert(level="critical", message=f"Pipeline {pipeline_id} failed"))
        self._graph.index_pipeline_run(pipeline_id, project_id, {"latency_ms": latency_ms, "success": success})

    def record_alert(self, level: str, message: str) -> None:
        alert = OpsAlert(level=level, message=message)
        self._alerts.append(alert)
        self._append_event({"type": "alert", "data": alert.to_dict(), "timestamp": time.time()})

    def active_alerts(self) -> List[OpsAlert]:
        return list(self._alerts)

    # -- aggregation -------------------------------------------------------------
    def aggregate(self) -> OpsSnapshot:
        pipeline_events = [event for event in self.iter_events() if event.get("type") == "pipeline_run"]
        nodes = self._count_nodes()
        pipelines = len(pipeline_events)
        incidents = sum(1 for alert in self._alerts if alert.level in {"critical", "error"})
        latencies = [float(event.get("latency_ms", 0.0)) for event in pipeline_events]
        avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0
        token_cost = self._team_totals()["cost"]
        return OpsSnapshot(nodes, pipelines, incidents, avg_latency_ms, token_cost, self.active_alerts())

    def alerts_table(self) -> Table:
        table = Table(title="Alerts")
        table.add_column("Level")
        table.add_column("Message")
        table.add_column("When")
        for alert in self._alerts:
            table.add_row(alert.level.upper(), alert.message, time.strftime("%H:%M:%S", time.localtime(alert.created_at)))
        return table

    def broadcast_health(self) -> Dict[str, Any]:
        snapshot = self.aggregate()
        return {
            "nodes": snapshot.nodes,
            "pipelines": snapshot.pipelines,
            "incidents": snapshot.incidents,
            "avg_latency_ms": snapshot.avg_latency_ms,
            "token_cost": snapshot.token_cost,
            "alerts": [alert.to_dict() for alert in snapshot.alerts],
        }

    def iter_events(self) -> Iterable[Dict[str, Any]]:
        if not self._events_file.exists():
            return []
        with self._events_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    # -- helpers -----------------------------------------------------------------
    def _count_nodes(self) -> int:
        conn = sqlite3.connect(self._team_store._db_path)
        try:
            cursor = conn.execute("SELECT COUNT(DISTINCT actor) FROM team_entries")
            value = cursor.fetchone()[0] or 0
            conn.commit()
            return int(value)
        finally:
            conn.close()

    def _team_totals(self) -> Dict[str, float]:
        conn = sqlite3.connect(self._team_store._db_path)
        try:
            cursor = conn.execute("SELECT SUM(cost), SUM(minutes) FROM team_entries")
            cost, minutes = cursor.fetchone()
            conn.commit()
            return {"cost": float(cost or 0.0), "minutes": float(minutes or 0.0)}
        finally:
            conn.close()

