"""Conversation context management."""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from statistics import mean
from typing import Deque, Iterable, List

from vortex.core.memory import UnifiedMemorySystem
from vortex.core.model import UnifiedModelManager
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ContextItem:
    """Represents a single conversational exchange."""

    role: str
    content: str
    tokens: int


class ContextManager:
    """Maintain rolling conversational context with adaptive summarisation."""

    def __init__(
        self,
        model_manager: UnifiedModelManager,
        memory: UnifiedMemorySystem,
        *,
        max_items: int = 50,
    ) -> None:
        self._model_manager = model_manager
        self._memory = memory
        self._items: Deque[ContextItem] = deque(maxlen=max_items)
        self._lock = asyncio.Lock()

    @property
    def items(self) -> List[ContextItem]:
        return list(self._items)

    async def add_exchange(self, role: str, content: str) -> ContextItem:
        """Record a conversation exchange and persist summary to memory."""

        item = ContextItem(role=role, content=content, tokens=len(content.split()))
        async with self._lock:
            self._items.append(item)
            if role == "user":
                await self._memory.add("conversation", content)
        return item

    async def summarise(self, *, target_tokens: int = 300) -> str:
        """Generate a compressed summary using the model manager."""

        async with self._lock:
            snapshot = list(self._items)

        if not snapshot:
            return ""

        prompt = "\n".join(f"{item.role}: {item.content}" for item in snapshot)
        logger.debug("summarising context", extra={"items": len(snapshot), "target": target_tokens})
        response = await self._model_manager.generate(prompt)
        summary = response.get("text", "")
        await self._memory.add("summary", summary)
        return summary

    async def average_tokens(self) -> float:
        async with self._lock:
            if not self._items:
                return 0.0
            return mean(item.tokens for item in self._items)

    async def trim_until(self, max_total_tokens: int) -> Iterable[ContextItem]:
        """Trim context until the token budget is satisfied."""

        async with self._lock:
            total = sum(item.tokens for item in self._items)
            trimmed: List[ContextItem] = []
            while self._items and total > max_total_tokens:
                removed = self._items.popleft()
                total -= removed.tokens
                trimmed.append(removed)
            return list(trimmed)
