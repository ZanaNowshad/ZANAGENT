"""Continuous learning subsystem."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Dict, List

from vortex.core.memory import UnifiedMemorySystem
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class ContinuousLearningSystem:
    """Aggregate feedback signals and persist refined insights."""

    def __init__(self, memory: UnifiedMemorySystem) -> None:
        self._memory = memory
        self._feedback: Dict[str, List[int]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def record_feedback(self, category: str, score: int) -> None:
        """Record a bounded feedback score and persist to memory."""

        if not 0 <= score <= 5:
            raise ValueError("score must be between 0 and 5")
        async with self._lock:
            self._feedback[category].append(score)
            await self._memory.add("feedback", f"{category}:{score}")
            logger.debug("feedback recorded", extra={"category": category, "score": score})

    async def average_score(self, category: str) -> float:
        async with self._lock:
            scores = self._feedback.get(category, [])
            if not scores:
                return 0.0
            return sum(scores) / len(scores)

    async def trending_categories(self) -> List[str]:
        async with self._lock:
            ranked = sorted(
                (
                    (category, sum(scores) / len(scores))
                    for category, scores in self._feedback.items()
                    if scores
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            return [category for category, _ in ranked]

    async def bootstrap_from_memory(self) -> None:
        """Load prior feedback entries from the persistent memory store."""

        records = await self._memory.list(limit=500, kind="feedback")
        async with self._lock:
            for record in records:
                try:
                    category, raw_score = record.content.split(":", 1)
                    self._feedback[category].append(int(raw_score))
                except ValueError:  # pragma: no cover - corrupt record handling
                    logger.warning("invalid feedback record", extra={"content": record.content})
