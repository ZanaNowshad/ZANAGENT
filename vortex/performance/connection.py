"""Async connection pooling."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable

from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class ConnectionPool:
    """Semaphore-backed connection pool for async clients."""

    def __init__(self, *, size: int = 10) -> None:
        if size <= 0:
            raise ValueError("size must be positive")
        self._semaphore = asyncio.Semaphore(size)

    @asynccontextmanager
    async def acquire(self, creator: Callable[[], AsyncIterator[object]]) -> AsyncIterator[object]:
        await self._semaphore.acquire()
        try:
            async with creator() as resource:
                yield resource
        finally:
            self._semaphore.release()
            logger.debug("connection released", extra={"available": self._semaphore._value})
