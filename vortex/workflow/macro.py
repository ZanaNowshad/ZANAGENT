"""Macro recording system."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from vortex.utils.logging import get_logger

logger = get_logger(__name__)

MacroCallable = Callable[..., Any]


@dataclass
class Macro:
    name: str
    description: str
    steps: List[MacroCallable]


class MacroSystem:
    """Allow operators to compose reusable workflow macros."""

    def __init__(self) -> None:
        self._macros: Dict[str, Macro] = {}
        self._lock = asyncio.Lock()

    async def register(self, name: str, description: str, steps: List[MacroCallable]) -> None:
        async with self._lock:
            if name in self._macros:
                raise ValueError(f"Macro {name} already exists")
            self._macros[name] = Macro(name=name, description=description, steps=steps)
            logger.info("macro registered", extra={"name": name})

    async def run(self, name: str, *args: Any, **kwargs: Any) -> List[Any]:
        async with self._lock:
            macro = self._macros.get(name)
            if macro is None:
                raise KeyError(name)
        results: List[Any] = []
        for step in macro.steps:
            result = step(*args, **kwargs)
            results.append(result)
        return results

    async def list_macros(self) -> List[Macro]:
        async with self._lock:
            return list(self._macros.values())
