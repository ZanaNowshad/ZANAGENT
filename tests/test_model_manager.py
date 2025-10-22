import asyncio

import pytest

from vortex.core.model import ProviderError, UnifiedModelManager


class FailingProvider:
    name = "failing"

    def __init__(self, *, settings):
        pass

    async def generate(self, prompt: str, **kwargs):
        raise ProviderError("failure")


class SuccessProvider:
    name = "success"

    def __init__(self, *, settings):
        pass

    async def generate(self, prompt: str, **kwargs):
        return {"text": prompt.upper(), "usage": {"prompt_tokens": 1, "completion_tokens": 1}}


def test_failover(monkeypatch):
    async def _run():
        from vortex.core import model

        monkeypatch.setitem(model.PROVIDER_REGISTRY, "failing", FailingProvider)
        monkeypatch.setitem(model.PROVIDER_REGISTRY, "success", SuccessProvider)
        manager = UnifiedModelManager(
            [
                {"name": "fail", "type": "failing"},
                {"name": "success", "type": "success"},
            ]
        )
        result = await manager.generate("hi")
        assert result["text"] == "HI"

    asyncio.run(_run())
