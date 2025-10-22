"""Performance and collaboration analytics for Vortex."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Tuple

from vortex.performance.monitor import PerformanceMonitor
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class PerformanceAnalytics:
    """Aggregate metrics emitted by :class:`PerformanceMonitor`."""

    def __init__(self, monitor: PerformanceMonitor) -> None:
        self._monitor = monitor
        self._counters: Dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def record_event(self, name: str) -> None:
        async with self._lock:
            self._counters[name] += 1

    async def snapshot(self) -> Dict[str, float]:
        async with self._lock:
            counters = dict(self._counters)
        snapshot: Dict[str, float] = {}
        for name in counters:
            snapshot[f"avg_{name}"] = await self._monitor.average(name)
            snapshot[f"p95_{name}"] = await self._monitor.percentile(name, 0.95)
            snapshot[f"count_{name}"] = float(counters[name])
        logger.debug("performance snapshot", extra={"metrics": snapshot})
        return snapshot

    async def reset(self) -> None:
        async with self._lock:
            self._counters.clear()


SESSION_DB = Path.home() / ".vortex" / "sessions" / "analytics.sqlite"


class SessionAnalyticsStore:
    """Persist session analytics and compute collaboration insights."""

    def __init__(self, database: Path | None = None) -> None:
        self._db_path = database or SESSION_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._initialise()

    async def register_session(self, session_id: str, title: str, *, owner: str) -> None:
        await self._execute(
            "INSERT OR IGNORE INTO sessions(session_id, title, owner, created_at) VALUES(?, ?, ?, ?)",
            (session_id, title, owner, time.time()),
        )

    async def record_session_event(
        self,
        session_id: str,
        kind: str,
        *,
        metrics: Dict[str, Any],
        author: str,
    ) -> None:
        payload = json.dumps(metrics, default=str)
        success = 1 if metrics.get("success", True) else 0
        duration = float(metrics.get("duration", 0.0) or 0.0)
        tokens = float(metrics.get("tokens", 0.0) or 0.0)
        cost = float(metrics.get("cost", 0.0) or 0.0)
        timestamp = float(metrics.get("timestamp", time.time()))
        await self._execute(
            """
            INSERT INTO events(session_id, kind, author, success, duration, tokens, cost, timestamp, metadata)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, kind, author, success, duration, tokens, cost, timestamp, payload),
        )

    async def session_summary(self, session_id: str) -> Dict[str, Any]:
        rows = await self._fetch(
            """
            SELECT kind, COUNT(*), AVG(duration), SUM(tokens), SUM(cost), SUM(success)
            FROM events WHERE session_id=? GROUP BY kind ORDER BY kind
            """,
            (session_id,),
        )
        totals = await self._fetch(
            "SELECT MIN(timestamp), MAX(timestamp) FROM events WHERE session_id=?",
            (session_id,),
        )
        duration = 0.0
        if totals and totals[0][0] is not None and totals[0][1] is not None:
            duration = max(0.0, float(totals[0][1]) - float(totals[0][0]))
        summary: Dict[str, Any] = {
            "session_id": session_id,
            "duration": duration,
            "events": [],
            "success_rate": 0.0,
        }
        success_count = 0.0
        total_count = 0.0
        for kind, count, avg_duration, tokens, cost, successes in rows:
            summary["events"].append(
                {
                    "kind": kind,
                    "count": int(count),
                    "avg_duration": float(avg_duration or 0.0),
                    "tokens": float(tokens or 0.0),
                    "cost": float(cost or 0.0),
                    "successes": int(successes or 0),
                }
            )
            success_count += float(successes or 0.0)
            total_count += float(count or 0.0)
        summary["success_rate"] = success_count / total_count if total_count else 0.0
        summary["kpis"] = self._aggregate_kpis(summary["events"])
        return summary

    async def generate_report(self, session_id: str) -> Dict[str, Any]:
        summary = await self.session_summary(session_id)
        timeline = await self._fetch(
            "SELECT timestamp, kind FROM events WHERE session_id=? ORDER BY timestamp",
            (session_id,),
        )
        series: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
        base = timeline[0][0] if timeline else time.time()
        for index, (timestamp, kind) in enumerate(timeline, start=1):
            series[kind].append((timestamp - base, float(index)))
        summary["timeline"] = {name: points for name, points in series.items()}
        return summary

    async def compare_sessions(self, first: str, second: str) -> Dict[str, Any]:
        a = await self.session_summary(first)
        b = await self.session_summary(second)
        comparison = {
            "first": a,
            "second": b,
            "delta_success": a["success_rate"] - b["success_rate"],
            "delta_cost": self._total_cost(a) - self._total_cost(b),
        }
        return comparison

    async def insights(self, session_id: str) -> List[str]:
        summary = await self.session_summary(session_id)
        insights: List[str] = []
        if summary["duration"] > 0:
            insights.append(
                f"Session ran for {summary['duration'] / 60:.1f} minutes with {len(summary['events'])} activity types."
            )
        highest = max(summary["events"], key=lambda item: item["count"], default=None)
        if highest:
            insights.append(
                f"Most frequent action: {highest['kind']} ({highest['count']} times, success {highest['successes']})."
            )
        slow = max(summary["events"], key=lambda item: item["avg_duration"], default=None)
        if slow and slow["avg_duration"] > 0:
            insights.append(f"Slowest step: {slow['kind']} averaging {slow['avg_duration']:.2f}s.")
        if summary["success_rate"] < 0.6:
            insights.append("Consider reviewing failing steps; success rate below 60%.")
        return insights

    async def _execute(self, query: str, params: Tuple[Any, ...]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._run_execute, query, params)

    async def _fetch(self, query: str, params: Tuple[Any, ...]) -> List[Tuple[Any, ...]]:
        async with self._lock:
            return await asyncio.to_thread(self._run_fetch, query, params)

    def _initialise(self) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions(
                    session_id TEXT PRIMARY KEY,
                    title TEXT,
                    owner TEXT,
                    created_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    author TEXT,
                    success INTEGER,
                    duration REAL,
                    tokens REAL,
                    cost REAL,
                    timestamp REAL,
                    metadata TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _run_execute(self, query: str, params: Tuple[Any, ...]) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(query, params)
            conn.commit()
        finally:
            conn.close()

    def _run_fetch(self, query: str, params: Tuple[Any, ...]) -> List[Tuple[Any, ...]]:
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()

    @staticmethod
    def _aggregate_kpis(events: Iterable[Dict[str, Any]]) -> Dict[str, float]:
        totals = {
            "events": 0.0,
            "cost": 0.0,
            "tokens": 0.0,
            "avg_duration": 0.0,
        }
        durations: List[float] = []
        for entry in events:
            totals["events"] += entry.get("count", 0.0)
            totals["cost"] += entry.get("cost", 0.0)
            totals["tokens"] += entry.get("tokens", 0.0)
            durations.append(entry.get("avg_duration", 0.0))
        totals["avg_duration"] = mean(durations) if durations else 0.0
        return totals

    @staticmethod
    def _total_cost(summary: Dict[str, Any]) -> float:
        return sum(event.get("cost", 0.0) for event in summary.get("events", []))


__all__ = ["PerformanceAnalytics", "SessionAnalyticsStore"]

