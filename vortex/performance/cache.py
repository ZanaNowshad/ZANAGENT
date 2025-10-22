"""Cache management facade."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Hashable

from vortex.utils.async_cache import AsyncTTLCache
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class CacheManager:
    """Coordinate shared caches for expensive operations."""

    def __init__(self, *, ttl: float = 30.0, maxsize: int = 256) -> None:
        self._cache = AsyncTTLCache(ttl=ttl, maxsize=maxsize)
        self._lock = asyncio.Lock()

    async def get_or_compute(self, key: Hashable, producer: Callable[[], Awaitable[Any]]) -> Any:
        return await self._cache.get_or_set(key, producer)

    async def warm(self, items: dict[Hashable, Any]) -> None:
        async with self._lock:
            for key, value in items.items():
                await self._cache.get_or_set(
                    key, lambda value=value: asyncio.sleep(0, result=value)
                )

    async def invalidate(self, key: Hashable) -> None:
        await self._cache.invalidate(key)

    async def clear(self) -> None:
        await self._cache.clear()
