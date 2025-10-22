"""Runtime performance monitoring."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from statistics import mean
from typing import AsyncIterator, Deque, Dict

from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TimingSample:
    """Represents a timed operation."""

    name: str
    duration: float
    metadata: Dict[str, str]


class PerformanceMonitor:
    """Simple high-resolution timing collector."""

    def __init__(self, *, window: int = 100) -> None:
        self._samples: Deque[TimingSample] = deque(maxlen=window)
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def track(self, name: str, **metadata: str) -> AsyncIterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            async with self._lock:
                self._samples.append(TimingSample(name=name, duration=duration, metadata=metadata))
                logger.debug("timing sample", extra={"name": name, "duration": duration})

    async def average(self, name: str) -> float:
        async with self._lock:
            durations = [sample.duration for sample in self._samples if sample.name == name]
            return mean(durations) if durations else 0.0

    async def percentile(self, name: str, percentile: float) -> float:
        async with self._lock:
            durations = sorted(sample.duration for sample in self._samples if sample.name == name)
            if not durations:
                return 0.0
            index = min(int(len(durations) * percentile), len(durations) - 1)
            return durations[index]
