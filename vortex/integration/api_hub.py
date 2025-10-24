"""HTTP API orchestration utilities."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping, Optional, Tuple

import httpx

from vortex.security.manager import UnifiedSecurityManager
from vortex.utils.async_cache import AsyncTTLCache
from vortex.utils.errors import IntegrationError
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class APIClientConfig:
    """Configuration describing a registered API endpoint."""

    base_url: str
    default_headers: Mapping[str, str]
    secret_name: Optional[str] = None


class APIHub:
    """Manage outbound API calls with caching and security checks.

    The hub centralises outbound HTTP interactions so that credentials are
    uniformly encrypted, caching is consistently applied, and retries obey
    global back-off policies. Consumers inject a :class:`UnifiedSecurityManager`
    which is used to store and retrieve API secrets.
    """

    def __init__(
        self,
        security: UnifiedSecurityManager,
        *,
        timeout: float = 10.0,
        cache_ttl: float = 30.0,
        cache_size: int = 128,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._security = security
        self._clients: MutableMapping[str, APIClientConfig] = {}
        self._timeout = timeout
        self._cache = AsyncTTLCache(maxsize=cache_size, ttl=cache_ttl)
        self._shared_client = client
        self._sessions: Dict[str, httpx.AsyncClient] = {}
        self._lock = asyncio.Lock()

    async def register_api(
        self,
        name: str,
        base_url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        secret: Optional[str] = None,
    ) -> None:
        """Register a remote API configuration.

        Secrets are stored via :class:`UnifiedSecurityManager` to enforce
        encryption at rest. Registration is idempotent and thread-safe.
        """

        async with self._lock:
            logger.debug("registering api", extra={"name": name, "base_url": base_url})
            if secret is not None:
                await self._security.store_secret(f"api:{name}", secret)
            config = APIClientConfig(
                base_url=base_url,
                default_headers=headers or {},
                secret_name=f"api:{name}" if secret else None,
            )
            self._clients[name] = config
            await self._cache.invalidate(("client", name))

    async def list_apis(self) -> list[str]:
        async with self._lock:
            return list(self._clients)

    async def _get_client(self, name: str) -> Tuple[APIClientConfig, httpx.AsyncClient]:
        config = self._clients.get(name)
        if config is None:
            raise IntegrationError(f"API {name} not registered")

        if self._shared_client is not None:
            return config, self._shared_client

        async with self._lock:
            session = self._sessions.get(name)
            if session is None:
                session = httpx.AsyncClient(base_url=config.base_url, timeout=self._timeout)
                self._sessions[name] = session
            return config, session

    async def call(
        self,
        name: str,
        endpoint: str,
        *,
        method: str = "GET",
        params: Optional[Mapping[str, Any]] = None,
        json: Optional[Mapping[str, Any]] = None,
        use_cache: bool = False,
    ) -> Any:
        """Execute an HTTP request and optionally cache the response body."""

        config, client = await self._get_client(name)

        async def _perform_request() -> Any:
            logger.debug(
                "api call",
                extra={"name": name, "endpoint": endpoint, "method": method, "use_cache": use_cache},
            )
            headers = dict(config.default_headers)
            if config.secret_name:
                token = await self._security.retrieve_secret(config.secret_name)
                headers.setdefault("Authorization", f"Bearer {token}")
            response = await client.request(method, endpoint, params=params, json=json, headers=headers)
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:  # pragma: no cover - defensive if API returns non JSON
                return response.text

        if not use_cache:
            return await _perform_request()

        cache_key = (
            name,
            endpoint,
            method,
            frozenset(params.items()) if params else None,
            frozenset(json.items()) if json else None,
        )
        return await self._cache.get_or_set(cache_key, _perform_request)

    async def close(self) -> None:
        """Close any underlying HTTP clients to free sockets."""

        async with self._lock:
            for session in self._sessions.values():  # pragma: no cover - trivial cleanup
                await session.aclose()
            self._sessions.clear()
