"""Async debugger utilities."""
from __future__ import annotations

import asyncio
import traceback
from typing import Awaitable, Callable

from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class Debugger:
    """Wrap coroutine execution with exception tracing."""

    async def run_with_debug(self, coro_factory: Callable[[], Awaitable[object]]) -> object:
        try:
            return await coro_factory()
        except Exception as exc:  # pragma: no cover - debugging path
            logger.error("debug failure", extra={"trace": traceback.format_exc()})
            raise exc

    async def timeout(self, coro: Awaitable[object], timeout: float) -> object:
        return await asyncio.wait_for(coro, timeout)
