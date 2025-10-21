import asyncio
from contextlib import asynccontextmanager

import pytest

from vortex.core.model import UnifiedModelManager
from vortex.performance import (
    CacheManager,
    ConnectionPool,
    CostTracker,
    LazyLoader,
    ParallelProcessor,
    PerformanceAnalytics,
    PerformanceMonitor,
)


@pytest.fixture()
def model_manager() -> UnifiedModelManager:
    return UnifiedModelManager([
        {"name": "echo", "type": "echo", "cost_per_1k_tokens": 0.01},
    ])


@pytest.mark.asyncio
async def test_performance_monitor_and_analytics(model_manager) -> None:
    monitor = PerformanceMonitor()
    analytics = PerformanceAnalytics(monitor)

    async with monitor.track("op", detail="test"):
        await asyncio.sleep(0)
    await analytics.record_event("op")
    snapshot = await analytics.snapshot()
    assert "avg_op" in snapshot

    tracker = CostTracker(model_manager)
    await model_manager.generate("hello world")
    total = await tracker.total_cost()
    assert total >= 0


@pytest.mark.asyncio
async def test_cache_and_parallel_tools() -> None:
    cache = CacheManager()
    called = 0

    async def producer() -> int:
        nonlocal called
        called += 1
        await asyncio.sleep(0)
        return called

    value = await cache.get_or_compute("key", producer)
    assert value == 1
    value = await cache.get_or_compute("key", producer)
    assert value == 1

    pool = ConnectionPool(size=1)

    @asynccontextmanager
    async def fake_resource():
        await asyncio.sleep(0)
        yield "resource"

    async with pool.acquire(fake_resource):
        pass

    loader = LazyLoader()
    module = loader.get("math")
    assert module.sqrt(4) == 2

    processor = ParallelProcessor(concurrency=2)
    results = await processor.run([lambda value=i: asyncio.sleep(0.01, result=value) for i in range(3)])
    assert sorted(results) == [0, 1, 2]
