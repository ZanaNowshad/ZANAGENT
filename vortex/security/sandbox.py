"""Restricted execution sandbox."""
from __future__ import annotations

import asyncio
import builtins
import importlib
import inspect
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Dict, Iterable, Optional, Set

from vortex.utils.errors import SecurityError
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SandboxPolicy:
    allowed_modules: Set[str] = field(default_factory=lambda: {"math", "json"})
    forbidden_builtins: Set[str] = field(default_factory=lambda: {"open", "exec", "eval", "compile"})


class Sandbox:
    """A lightweight sandbox that enforces module and builtin restrictions."""

    def __init__(self, policy: Optional[SandboxPolicy] = None) -> None:
        self.policy = policy or SandboxPolicy()

    def clone(self) -> "Sandbox":
        return Sandbox(policy=SandboxPolicy(
            allowed_modules=set(self.policy.allowed_modules),
            forbidden_builtins=set(self.policy.forbidden_builtins),
        ))

    async def run(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute ``func`` in a constrained environment."""

        module = inspect.getmodule(func)
        if module and module.__name__ not in self.policy.allowed_modules:
            raise SecurityError(f"Module {module.__name__} is not allowed")
        for name in self.policy.forbidden_builtins:
            if getattr(builtins, name, None):
                setattr(builtins, name, self._blocked_builtin(name))
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        finally:
            # Restore builtins to their original implementations
            for name in self.policy.forbidden_builtins:
                setattr(builtins, name, getattr(__builtins__, name, None))

    @staticmethod
    def _blocked_builtin(name: str) -> Callable[..., Any]:
        def _blocked(*_: Any, **__: Any) -> None:
            raise SecurityError(f"Use of builtin {name} is forbidden in sandbox")

        return _blocked


__all__ = ["Sandbox", "SandboxPolicy"]
