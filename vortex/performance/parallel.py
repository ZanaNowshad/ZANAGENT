"""Parallel task execution utilities."""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Iterable, List, TypeVar

T = TypeVar("T")


class ParallelProcessor:
    """Execute coroutines with bounded concurrency."""

    def __init__(self, *, concurrency: int = 5) -> None:
        if concurrency <= 0:
            raise ValueError("concurrency must be positive")
        self._semaphore = asyncio.Semaphore(concurrency)

    async def run(self, tasks: Iterable[Callable[[], Awaitable[T]]]) -> List[T]:
        async def _run_task(factory: Callable[[], Awaitable[T]]) -> T:
            async with self._semaphore:
                return await factory()

        return await asyncio.gather(*[_run_task(task) for task in tasks])
