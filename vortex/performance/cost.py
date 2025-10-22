"""Provider cost tracking."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict

from vortex.core.model import UnifiedModelManager
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ProviderCost:
    provider: str
    total_tokens: int
    cost: float


class CostTracker:
    """Monitor provider token usage and compute spend estimates."""

    def __init__(self, model_manager: UnifiedModelManager) -> None:
        self._model_manager = model_manager
        self._lock = asyncio.Lock()

    async def snapshot(self) -> Dict[str, ProviderCost]:
        async with self._lock:
            usage = self._model_manager.token_usage()
            snapshot = {
                name: ProviderCost(
                    provider=name,
                    total_tokens=metrics.prompt_tokens + metrics.completion_tokens,
                    cost=metrics.cost,
                )
                for name, metrics in usage.items()
            }
            logger.debug("cost snapshot", extra={"snapshot": {k: v.cost for k, v in snapshot.items()}})
            return snapshot

    async def total_cost(self) -> float:
        data = await self.snapshot()
        return sum(item.cost for item in data.values())
