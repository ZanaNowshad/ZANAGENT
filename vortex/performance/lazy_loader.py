"""Lazy module loading utilities."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Dict

from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class LazyLoader:
    """Cache module imports to avoid repeated import overhead."""

    def __init__(self) -> None:
        self._modules: Dict[str, ModuleType] = {}

    def get(self, module_name: str) -> ModuleType:
        module = self._modules.get(module_name)
        if module is None:
            logger.debug("lazy importing module", extra={"module": module_name})
            module = importlib.import_module(module_name)
            self._modules[module_name] = module
        return module

    def clear(self) -> None:
        self._modules.clear()
