import asyncio
from pathlib import Path

import httpx
import pytest

from vortex.integration import APIHub, CloudIntegration
from vortex.security.manager import UnifiedSecurityManager


@pytest.mark.asyncio
async def test_api_hub_register_and_call(tmp_path: Path) -> None:
    security = UnifiedSecurityManager(
        credential_dir=tmp_path,
        allowed_modules=["json"],
        forbidden_modules=[],
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"url": str(request.url)})
    )
    client = httpx.AsyncClient(transport=transport, base_url="https://example.test")
    hub = APIHub(security, client=client)

    await hub.register_api("example", "https://example.test", secret="token")
    response = await hub.call("example", "/data", use_cache=True)
    assert "example.test/data" in response["url"]
    apis = await hub.list_apis()
    assert apis == ["example"]
    await client.aclose()


@pytest.mark.asyncio
async def test_cloud_integration_cache(tmp_path: Path) -> None:
    security = UnifiedSecurityManager(
        credential_dir=tmp_path,
        allowed_modules=["json"],
        forbidden_modules=[],
    )
    cloud = CloudIntegration(security)
    await cloud.add_account("default", "https://cloud.test", credential="secret")

    async def _client(account) -> httpx.AsyncClient:  # type: ignore[no-untyped-def]
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"path": request.url.path})
        )
        return httpx.AsyncClient(transport=transport, base_url=account.base_url)

    cloud._client = _client  # type: ignore[assignment]
    result = await cloud.request("default", "GET", "/status", cache=True)
    assert result["path"] == "/status"
    accounts = await cloud.list_accounts()
    assert accounts == ["default"]
