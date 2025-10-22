"""Self-improvement experimentation."""
from __future__ import annotations

import asyncio
from typing import Callable, List

from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class SelfImprovementLoop:
    """Run evaluation cycles with retry-based improvements."""

    def __init__(self, evaluator: Callable[[str], float]) -> None:
        self._evaluator = evaluator
        self._history: List[float] = []

    async def iterate(self, idea: str, attempts: int = 3) -> float:
        best = float("-inf")
        for attempt in range(attempts):
            score = await asyncio.to_thread(self._evaluator, idea)
            self._history.append(score)
            best = max(best, score)
            logger.debug("self improvement", extra={"attempt": attempt, "score": score})
        return best

    @property
    def history(self) -> List[float]:
        return list(self._history)
