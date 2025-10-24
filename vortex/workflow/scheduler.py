"""Workflow scheduler."""
from __future__ import annotations

import asyncio
import contextlib
import heapq
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List

from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(order=True)
class ScheduledJob:
    run_at: float
    name: str = field(compare=False)
    callback: Callable[[], Awaitable[None]] = field(compare=False)


class WorkflowScheduler:
    """Lightweight timed job scheduler used for periodic tasks."""

    def __init__(self) -> None:
        self._jobs: List[ScheduledJob] = []
        self._lock = asyncio.Lock()
        self._runner: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def schedule(self, name: str, delay: float, callback: Callable[[], Awaitable[None]]) -> None:
        async with self._lock:
            heapq.heappush(self._jobs, ScheduledJob(run_at=time.time() + delay, name=name, callback=callback))
            if self._runner is None:
                self._runner = asyncio.create_task(self._run())
            self._stop_event.set()

    async def _run(self) -> None:
        while True:
            await self._stop_event.wait()
            self._stop_event.clear()
            while True:
                async with self._lock:
                    if not self._jobs:
                        break
                    job = self._jobs[0]
                    delay = job.run_at - time.time()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    heapq.heappop(self._jobs)
                logger.debug("executing scheduled job", extra={"name": job.name})
                await job.callback()
            if not self._jobs:
                break
        self._runner = None

    async def shutdown(self) -> None:
        if self._runner:
            self._runner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner
