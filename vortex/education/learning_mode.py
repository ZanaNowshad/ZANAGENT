"""Interactive learning mode."""

from __future__ import annotations

from typing import Callable, List

from vortex.ai.context_manager import ContextManager
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class LearningMode:
    """Guide users through educational prompts."""

    def __init__(self, context: ContextManager) -> None:
        self._context = context
        self._lessons: List[str] = []

    async def add_lesson(self, prompt: str) -> None:
        await self._context.add_exchange("system", prompt)
        self._lessons.append(prompt)

    async def run(self, responder: Callable[[str], str]) -> List[str]:
        outputs: List[str] = []
        for lesson in self._lessons:
            await self._context.add_exchange("assistant", lesson)
            reply = responder(lesson)
            outputs.append(reply)
            await self._context.add_exchange("user", reply)
        return outputs
