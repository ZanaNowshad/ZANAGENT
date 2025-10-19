"""Asynchronous caching helpers.

The asynchronous agent orchestrator routinely calls provider APIs that can be
slow or rate limited. A lightweight cache with time-to-live semantics reduces
unnecessary calls while keeping implementation simple and dependency-free.
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Hashable, Optional, Tuple


@dataclass
class CacheEntry:
    """Stored cache entry metadata."""

    value: Any
    expires_at: float


class AsyncTTLCache:
    """A minimal asynchronous TTL cache with LRU eviction.

    The cache is intentionally straightforward. Production systems often rely on
    Redis or Memcached, but including a local cache improves resiliency during
    transient network hiccups and keeps unit tests deterministic.
    """

    def __init__(self, maxsize: int = 128, ttl: float = 60.0) -> None:
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: "OrderedDict[Hashable, CacheEntry]" = OrderedDict()
        self._lock = asyncio.Lock()

    def _purge(self) -> None:
        now = time.time()
        keys_to_delete = [key for key, entry in self._data.items() if entry.expires_at <= now]
        for key in keys_to_delete:
            self._data.pop(key, None)
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    async def get_or_set(self, key: Hashable, producer: Callable[[], Awaitable[Any]]) -> Any:
        """Return cached value or compute and cache it.

        ``producer`` is only executed when the key is missing or stale, keeping
        the interface easy to consume from asyncio tasks.
        """

        async with self._lock:
            self._purge()
            entry = self._data.get(key)
            if entry is not None:
                return entry.value
            value = await producer()
            self._data[key] = CacheEntry(value=value, expires_at=time.time() + self.ttl)
            return value

    async def invalidate(self, key: Hashable) -> None:
        """Invalidate a cached entry if it exists."""

        async with self._lock:
            self._data.pop(key, None)

    async def clear(self) -> None:
        """Remove all entries from the cache."""

        async with self._lock:
            self._data.clear()


__all__ = ["AsyncTTLCache"]
