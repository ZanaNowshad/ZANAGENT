"""Performance analytics aggregation."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Dict

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
