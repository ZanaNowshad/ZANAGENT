"""Cloud provider integrations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

import httpx

from vortex.security.manager import UnifiedSecurityManager
from vortex.utils.async_cache import AsyncTTLCache
from vortex.utils.errors import IntegrationError
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CloudAccount:
    """Metadata describing a cloud account."""

    name: str
    base_url: str
    credential_key: str
    region: Optional[str] = None


class CloudIntegration:
    """Interact with cloud control planes via signed requests."""

    def __init__(self, security: UnifiedSecurityManager, *, ttl: float = 60.0) -> None:
        self._security = security
        self._accounts: Dict[str, CloudAccount] = {}
        self._cache = AsyncTTLCache(ttl=ttl)
        self._lock = asyncio.Lock()

    async def add_account(
        self, name: str, base_url: str, credential: str, *, region: Optional[str] = None
    ) -> None:
        """Register a new cloud account and persist its credential securely."""

        async with self._lock:
            secret_name = f"cloud:{name}"
            await self._security.store_secret(secret_name, credential)
            self._accounts[name] = CloudAccount(
                name=name, base_url=base_url, credential_key=secret_name, region=region
            )

    async def list_accounts(self) -> list[str]:
        async with self._lock:
            return list(self._accounts)

    async def _client(self, account: CloudAccount) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=account.base_url, timeout=15.0)

    async def request(
        self,
        account_name: str,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        payload: Optional[Mapping[str, Any]] = None,
        cache: bool = False,
    ) -> Any:
        """Issue a signed request to the cloud provider."""

        account = self._accounts.get(account_name)
        if account is None:
            raise IntegrationError(f"Unknown account {account_name}")

        async def _perform() -> Any:
            token = await self._security.retrieve_secret(account.credential_key)
            headers = {"Authorization": f"Bearer {token}"}
            async with await self._client(account) as client:
                response = await client.request(
                    method, path, params=params, json=payload, headers=headers
                )
                response.raise_for_status()
                return response.json()

        if not cache:
            return await _perform()

        cache_key = (
            account_name,
            method,
            path,
            frozenset(params.items()) if params else None,
            frozenset(payload.items()) if payload else None,
        )
        return await self._cache.get_or_set(cache_key, _perform)
