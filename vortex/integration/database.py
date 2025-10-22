"""Async database management for integration workflows."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterable, Optional

import aiosqlite

from vortex.security.encryption import DataEncryptor
from vortex.security.manager import UnifiedSecurityManager
from vortex.utils.async_cache import AsyncTTLCache
from vortex.utils.errors import IntegrationError
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class QueryResult:
    """Structure describing a database query outcome."""

    rows: list[Dict[str, Any]]
    rowcount: int


class DatabaseManager:
    """Provide encrypted async access to SQLite databases."""

    def __init__(
        self,
        database_url: str,
        security: UnifiedSecurityManager,
        *,
        cache_ttl: float = 5.0,
    ) -> None:
        if database_url.startswith("sqlite:///"):
            path = Path(database_url.split("sqlite:///")[-1])
            path.parent.mkdir(parents=True, exist_ok=True)
            self._connect_target = str(path)
            self._use_uri = False
        else:
            self._connect_target = database_url
            self._use_uri = database_url.startswith("file:")
        self._security = security
        self._cache = AsyncTTLCache(ttl=cache_ttl)
        self._encryptor = DataEncryptor(security.credential_store)
        self._pool_lock = asyncio.Lock()
        self._pool: Optional[aiosqlite.Connection] = None

    async def _connect(self) -> aiosqlite.Connection:
        async with self._pool_lock:
            if self._pool is None:
                logger.debug("opening database", extra={"url": self._connect_target})
                self._pool = await aiosqlite.connect(self._connect_target, uri=self._use_uri)
                self._pool.row_factory = aiosqlite.Row
            return self._pool

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        conn = await self._connect()
        try:
            yield conn
        finally:
            await conn.commit()

    async def execute(self, sql: str, parameters: Iterable[Any] | None = None) -> QueryResult:
        """Execute a mutating query and return a structured result."""

        async with self.connection() as conn:
            cursor = await conn.execute(sql, tuple(parameters or ()))
            await conn.commit()
            rows = [dict(row) for row in await cursor.fetchall()] if cursor.description else []
            return QueryResult(rows=rows, rowcount=cursor.rowcount)

    async def fetch(self, sql: str, parameters: Iterable[Any] | None = None, *, use_cache: bool = False) -> QueryResult:
        """Execute a read-only query with optional caching."""

        async def _run_query() -> QueryResult:
            async with self.connection() as conn:
                cursor = await conn.execute(sql, tuple(parameters or ()))
                rows = [dict(row) for row in await cursor.fetchall()]
                return QueryResult(rows=rows, rowcount=len(rows))

        if not use_cache:
            return await _run_query()

        cache_key = (sql, tuple(parameters or ()))
        return await self._cache.get_or_set(cache_key, _run_query)

    async def store_secret_record(self, table: str, payload: Dict[str, Any]) -> None:
        """Persist a sensitive payload after encrypting it column-wise."""

        if not payload:
            raise IntegrationError("payload may not be empty")

        columns = ", ".join(payload.keys())
        placeholders = ", ".join(["?"] * len(payload))
        encrypted_values = [self._encryptor.encrypt_value(str(value)) for value in payload.values()]
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        await self.execute(sql, encrypted_values)

    async def close(self) -> None:
        """Close the underlying connection to free resources."""

        async with self._pool_lock:
            if self._pool is not None:
                await self._pool.close()
                self._pool = None
