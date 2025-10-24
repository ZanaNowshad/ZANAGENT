"""Dynamic plugin management."""
from __future__ import annotations

import asyncio
import importlib
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable, Optional, Type

from vortex.security.sandbox import Sandbox
from vortex.utils.errors import PluginError
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class BasePlugin:
    """Plugins extend the agent with domain-specific skills."""

    name: str = "unnamed"

    async def setup(self) -> None:
        """Initialise the plugin."""

    async def teardown(self) -> None:
        """Release resources when unloading."""

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute plugin logic synchronously.

        Running synchronously simplifies sandboxing because the callable can be
        executed inside a dedicated thread with restricted builtins. Plugins can
        still perform asynchronous work internally by managing their own event
        loops if required.
        """

        raise NotImplementedError


@dataclass
class PluginState:
    module: ModuleType
    instance: BasePlugin
    sandbox: Sandbox


class UnifiedPluginSystem:
    """Locate, load, and execute plugins safely."""

    def __init__(self, plugin_paths: Iterable[Path], *, sandbox: Optional[Sandbox] = None) -> None:
        self.plugin_paths = list(plugin_paths)
        self._plugins: Dict[str, PluginState] = {}
        self._sandbox = sandbox or Sandbox()
        self._lock = asyncio.Lock()

    def discover(self) -> Dict[str, Path]:
        """Return a mapping of plugin name to module path."""

        discovered: Dict[str, Path] = {}
        for path in self.plugin_paths:
            if not path.exists():
                continue
            for file in path.glob("*.py"):
                name = file.stem
                discovered[name] = file
        return discovered

    async def load(self, name: str) -> BasePlugin:
        """Load a plugin by name."""

        async with self._lock:
            discovered = self.discover()
            if name not in discovered:
                raise PluginError(f"Plugin {name} not found")
            module = self._import(discovered[name])
            plugin_cls = self._resolve_plugin(module)
            instance = plugin_cls()
            sandbox = self._sandbox.clone()
            await instance.setup()
            self._plugins[name] = PluginState(module=module, instance=instance, sandbox=sandbox)
            return instance

    async def unload(self, name: str) -> None:
        async with self._lock:
            state = self._plugins.pop(name, None)
            if not state:
                return
            await state.instance.teardown()
            self._unimport(state.module)

    async def execute(self, name: str, *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            state = self._plugins.get(name)
            if not state:
                await self.load(name)
                state = self._plugins[name]
            return await state.sandbox.run(state.instance.execute, *args, **kwargs)

    def _import(self, path: Path) -> ModuleType:
        sys.path.insert(0, str(path.parent))
        module_name = path.stem
        try:
            return importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - import errors rare in tests
            raise PluginError(f"Failed to import plugin {module_name}: {exc}") from exc
        finally:
            sys.path.pop(0)

    def _unimport(self, module: ModuleType) -> None:
        sys.modules.pop(module.__name__, None)

    def _resolve_plugin(self, module: ModuleType) -> Type[BasePlugin]:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                return obj
        raise PluginError("No plugin class found")


__all__ = ["UnifiedPluginSystem", "BasePlugin"]
