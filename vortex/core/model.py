"""Model orchestration for Vortex."""
from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, Iterable, List, Optional, Tuple, Type

import httpx

from vortex.utils.async_cache import AsyncTTLCache
from vortex.utils.errors import ProviderError
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class BaseProvider:
    """Interface implemented by all provider backends."""

    name: str

    def __init__(self, *, settings: Dict[str, Any]) -> None:
        self.settings = settings
        self.api_key = settings.get("api_key")
        self.base_url = settings.get("base_url")

    async def generate(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        """Return a text completion for ``prompt``.

        Subclasses override this method. Implementations should raise
        :class:`ProviderError` for recoverable issues so the manager can trigger
        failover.
        """

        raise NotImplementedError

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncGenerator[str, None]:
        """Stream tokens for ``prompt``.

        Providers that do not support streaming can simply yield the final
        completion once, which keeps the API ergonomic and avoids nested
        conditionals across the codebase.
        """

        result = await self.generate(prompt, **kwargs)
        yield result.get("text", "")


class EchoProvider(BaseProvider):
    """Deterministic provider returning the prompt.

    This provider is primarily used during testing and as a safe fallback when
    external credentials are not available.
    """

    name = "echo"

    async def generate(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        await asyncio.sleep(0)
        return {"text": prompt, "usage": {"prompt_tokens": len(prompt.split()), "completion_tokens": len(prompt.split())}}


class OpenAIProvider(BaseProvider):
    """Minimal OpenAI-compatible provider using HTTPX.

    The implementation intentionally uses an HTTP client rather than the
    official SDK to keep dependencies light. Only features required by the
    framework are implemented. The class is resilient to missing credentials so
    the system can still boot in development environments.
    """

    name = "openai"
    default_model = "gpt-3.5-turbo"

    async def generate(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        if not self.api_key:
            raise ProviderError("OpenAI API key missing")
        model = kwargs.get("model", self.default_model)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self.base_url or "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
            )
            if response.status_code >= 400:
                raise ProviderError(f"OpenAI error: {response.text}")
            payload = response.json()
            choice = payload["choices"][0]
            usage = payload.get("usage", {})
            return {"text": choice["message"]["content"], "usage": usage}

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncGenerator[str, None]:  # pragma: no cover - network heavy
        if not self.api_key:
            raise ProviderError("OpenAI API key missing")
        model = kwargs.get("model", self.default_model)
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                self.base_url or "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                },
            ) as response:
                if response.status_code >= 400:
                    raise ProviderError(f"OpenAI error: {await response.aread()}")
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    yield chunk


PROVIDER_REGISTRY: Dict[str, Type[BaseProvider]] = {
    EchoProvider.name: EchoProvider,
    OpenAIProvider.name: OpenAIProvider,
}


@dataclass
class ProviderMetrics:
    """Track usage metrics for providers."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0

    def update(self, usage: Dict[str, Any], *, rate: float = 0.0) -> None:
        self.prompt_tokens += int(usage.get("prompt_tokens", 0))
        self.completion_tokens += int(usage.get("completion_tokens", 0))
        total_tokens = self.prompt_tokens + self.completion_tokens
        self.cost = total_tokens / 1000.0 * rate


@dataclass
class ProviderState:
    """Internal representation of a provider instance."""

    settings: Dict[str, Any]
    instance: BaseProvider
    metrics: ProviderMetrics = field(default_factory=ProviderMetrics)


class UnifiedModelManager:
    """Coordinate multiple providers with failover and metrics."""

    def __init__(self, providers: Iterable[Dict[str, Any]]) -> None:
        self.providers: List[ProviderState] = [self._create_provider(conf) for conf in providers]
        if not self.providers:
            raise ProviderError("No providers configured")
        self._cache = AsyncTTLCache(ttl=5.0)
        self._lock = asyncio.Lock()

    def _create_provider(self, conf: Dict[str, Any]) -> ProviderState:
        provider_type = conf.get("type")
        if provider_type not in PROVIDER_REGISTRY:
            raise ProviderError(f"Unknown provider type: {provider_type}")
        provider_cls = PROVIDER_REGISTRY[provider_type]
        instance = provider_cls(settings=conf)
        return ProviderState(settings=conf, instance=instance)

    async def generate(self, prompt: str, *, model: Optional[str] = None, streaming: bool = False) -> Any:
        """Generate a completion using configured providers.

        The manager iterates through providers until one succeeds. Failures are
        logged and the next provider is tried automatically. Token accounting and
        cost calculation happen per provider.
        """

        async with self._lock:
            for state in self.providers:
                try:
                    if streaming:
                        return state.instance.stream(prompt, model=model)
                    result = await state.instance.generate(prompt, model=model)
                    self._update_metrics(state, result)
                    return result
                except ProviderError as exc:
                    logger.warning("provider failed", extra={"provider": state.instance.name, "error": str(exc)})
                    continue
        raise ProviderError("All providers failed")

    async def cached_generate(self, cache_key: str, prompt: str, **kwargs: Any) -> Any:
        """Return completions using an in-memory cache to reduce API usage."""

        return await self._cache.get_or_set(cache_key, lambda: self.generate(prompt, **kwargs))

    def _update_metrics(self, state: ProviderState, result: Dict[str, Any]) -> None:
        usage = result.get("usage", {})
        state.metrics.update(usage, rate=float(state.settings.get("cost_per_1k_tokens", 0.0)))

    def token_usage(self) -> Dict[str, ProviderMetrics]:
        """Return aggregated usage metrics per provider."""

        return {state.instance.name: state.metrics for state in self.providers}


__all__ = [
    "UnifiedModelManager",
    "BaseProvider",
    "ProviderError",
    "PROVIDER_REGISTRY",
]
