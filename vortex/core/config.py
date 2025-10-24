"""Configuration management for Vortex.

The :class:`UnifiedConfigManager` coordinates configuration loading, validation,
and live reloading. Configurations are expressed as YAML (or TOML) to give
operators a declarative way to customise provider credentials, security
policies, and runtime limits. Internally the configuration is validated using
Pydantic models to guarantee type safety throughout the codebase.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from vortex.utils.errors import ConfigurationError
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class ProviderSettings(BaseModel):
    """Configuration describing an AI provider."""

    name: str
    type: str = Field(..., description="Provider implementation identifier")
    api_key: Optional[str] = Field(default=None, repr=False)
    base_url: Optional[str] = None
    max_tokens: int = 4096
    cost_per_1k_tokens: float = 0.0
    streaming: bool = True


class MemorySettings(BaseModel):
    """Configuration for persistent memory backends."""

    database: str = Field(default="sqlite:///vortex_memory.db")
    vector_backend: str = Field(default="simple", description="Vector store type")
    embedding_model: str = Field(default="openai:text-embedding-ada-002")
    persist_path: Path = Field(default=Path(".vortex/memory"))


class SecuritySettings(BaseModel):
    """Security knobs exposed to operators."""

    sandbox_enabled: bool = True
    allowed_modules: List[str] = Field(default_factory=lambda: ["math", "json"])
    forbidden_modules: List[str] = Field(default_factory=lambda: ["os", "sys"])
    credential_store: Path = Field(default=Path(".vortex/credentials"))
    key_rotation_interval: int = Field(default=7 * 24 * 3600, description="Seconds")


class PlannerSettings(BaseModel):
    """Tuning options for the advanced planner."""

    max_parallel_tasks: int = 4
    recovery_retries: int = 3


class UISettings(BaseModel):
    """Settings for the terminal UI."""

    enable_progress: bool = True
    theme: str = "default"


class VortexSettings(BaseModel):
    """Root configuration schema."""

    providers: List[ProviderSettings]
    memory: MemorySettings = Field(default_factory=MemorySettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    planner: PlannerSettings = Field(default_factory=PlannerSettings)
    ui: UISettings = Field(default_factory=UISettings)

    @field_validator("providers")
    @classmethod
    def validate_providers(cls, value: List[ProviderSettings]) -> List[ProviderSettings]:
        if not value:
            raise ValueError("At least one provider must be configured")
        return value


class UnifiedConfigManager:
    """Load and monitor configuration files for the runtime.

    The manager is intentionally implemented as a singleton-like component so it
    can be initialised once in :mod:`vortex.main` and then injected into other
    subsystems. Live reload is achieved via a background thread that polls the
    configuration file modification timestamp; the approach avoids extra
    dependencies while still providing near-real-time updates in development.
    """

    def __init__(self, config_path: Optional[Path] = None, *, poll_interval: float = 2.0) -> None:
        self.config_path = config_path or Path(os.environ.get("VORTEX_CONFIG", "config/default.yml"))
        self.poll_interval = poll_interval
        self._settings: Optional[VortexSettings] = None
        self._callbacks: List[Callable[[VortexSettings], Awaitable[None]]] = []
        self._stop_event = threading.Event()
        self._watch_task: Optional[threading.Thread] = None
        self._lock = asyncio.Lock()

    async def load(self) -> VortexSettings:
        """Load configuration from disk and validate it."""

        async with self._lock:
            try:
                logger.debug("loading configuration", extra={"path": str(self.config_path)})
                data = self._read_file(self.config_path)
                settings = VortexSettings(**data)
                self._settings = settings
                return settings
            except Exception as exc:  # pragma: no cover - defensive
                raise ConfigurationError(str(exc)) from exc

    async def reload(self) -> VortexSettings:
        """Reload configuration explicitly."""

        settings = await self.load()
        await self._notify(settings)
        return settings

    def start_watching(self) -> None:
        """Begin polling the configuration file for changes."""

        if self._watch_task and self._watch_task.is_alive():  # pragma: no cover - simple guard
            return

        def _watch() -> None:
            last_mtime = 0.0
            while not self._stop_event.is_set():
                try:
                    mtime = self.config_path.stat().st_mtime
                    if mtime != last_mtime:
                        last_mtime = mtime
                        asyncio.run(self.reload())
                except FileNotFoundError:
                    logger.warning("configuration file missing", extra={"path": str(self.config_path)})
                time.sleep(self.poll_interval)

        self._stop_event.clear()
        self._watch_task = threading.Thread(target=_watch, name="config-watcher", daemon=True)
        self._watch_task.start()

    def stop_watching(self) -> None:
        """Stop polling the configuration file."""

        self._stop_event.set()
        if self._watch_task and self._watch_task.is_alive():  # pragma: no cover - thread cleanup
            self._watch_task.join(timeout=1)

    def register_callback(self, callback: Callable[[VortexSettings], Awaitable[None]]) -> None:
        """Register a coroutine callback executed after reloads."""

        self._callbacks.append(callback)

    async def get_settings(self) -> VortexSettings:
        """Return the last loaded settings, loading them if necessary."""

        if self._settings is None:
            return await self.load()
        return self._settings

    async def _notify(self, settings: VortexSettings) -> None:
        for callback in self._callbacks:
            try:
                await callback(settings)
            except Exception as exc:  # pragma: no cover - logging side effects only
                logger.exception("configuration callback failed", exc_info=exc)

    @staticmethod
    def _read_file(path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise ConfigurationError(f"Configuration file {path} does not exist")
        if path.suffix in {".yml", ".yaml"}:
            with path.open("r", encoding="utf-8") as handle:
                return yaml.safe_load(handle) or {}
        if path.suffix == ".toml":
            import tomllib  # Python 3.11+ built-in

            with path.open("rb") as handle:
                return tomllib.load(handle)
        raise ConfigurationError(f"Unsupported configuration format: {path.suffix}")


__all__ = [
    "UnifiedConfigManager",
    "VortexSettings",
    "ProviderSettings",
    "MemorySettings",
    "SecuritySettings",
    "PlannerSettings",
    "UISettings",
]
