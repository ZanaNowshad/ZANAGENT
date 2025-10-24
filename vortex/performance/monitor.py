"""Runtime performance monitoring."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from statistics import mean
from typing import AsyncIterator, Deque, Dict, Tuple

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
        self._service_latency: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=window))
        self._service_errors: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=window))
        self._service_environment: Dict[str, str] = {}

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

    async def record_service_health(
        self,
        service: str,
        latency: float,
        *,
        error_rate: float = 0.0,
        environment: str = "default",
    ) -> None:
        """Capture deploy health metrics for dashboards."""

        async with self._lock:
            self._service_latency[service].append(latency)
            self._service_errors[service].append(error_rate)
            self._service_environment[service] = environment
            logger.debug(
                "service health recorded",
                extra={"service": service, "latency": latency, "error_rate": error_rate},
            )

    async def service_summary(self, service: str) -> Dict[str, float | str]:
        async with self._lock:
            latencies = list(self._service_latency.get(service, []))
            errors = list(self._service_errors.get(service, []))
            environment = self._service_environment.get(service, "default")
        if not latencies:
            return {"service": service, "latency_p95": 0.0, "error_rate": 0.0, "environment": environment}
        latencies_sorted = sorted(latencies)
        index = min(int(len(latencies_sorted) * 0.95), len(latencies_sorted) - 1)
        p95 = latencies_sorted[index]
        error_rate = sum(errors) / len(errors) if errors else 0.0
        return {
            "service": service,
            "latency_p95": p95,
            "latency_avg": sum(latencies) / len(latencies),
            "error_rate": error_rate,
            "environment": environment,
        }

    async def environment_overview(self) -> Dict[str, Dict[str, float]]:
        async with self._lock:
            snapshot: Dict[str, Tuple[float, float, int]] = {}
            for service, latencies in self._service_latency.items():
                if not latencies:
                    continue
                env = self._service_environment.get(service, "default")
                total_latency, total_errors, count = snapshot.get(env, (0.0, 0.0, 0))
                total_latency += sum(latencies)
                total_errors += sum(self._service_errors.get(service, []))
                count += len(latencies)
                snapshot[env] = (total_latency, total_errors, count)
        overview: Dict[str, Dict[str, float]] = {}
        for env, (latency_sum, error_sum, count) in snapshot.items():
            overview[env] = {
                "latency_avg": latency_sum / count if count else 0.0,
                "error_rate": error_sum / count if count else 0.0,
            }
        return overview
