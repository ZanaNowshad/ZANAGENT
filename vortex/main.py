"""Main entrypoint initialising the Vortex runtime."""
from __future__ import annotations

import asyncio
from pathlib import Path

from vortex.cli.app import RuntimeContext, app, set_runtime
from vortex.core.config import UnifiedConfigManager
from vortex.core.memory import UnifiedMemorySystem
from vortex.core.model import UnifiedModelManager
from vortex.core.planner import UnifiedAdvancedPlanner
from vortex.core.plugin import UnifiedPluginSystem
from vortex.core.ui import UnifiedRichUI
from vortex.intelligence import (
    UnifiedAudioSystem,
    UnifiedCodeIntelligence,
    UnifiedDataAnalyst,
    UnifiedVisionPro,
)
from vortex.security.manager import UnifiedSecurityManager
from vortex.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


async def _initialise_runtime() -> None:
    config_manager = UnifiedConfigManager()
    settings = await config_manager.load()
    configure_logging()

    security = UnifiedSecurityManager(
        credential_dir=settings.security.credential_store,
        allowed_modules=settings.security.allowed_modules,
        forbidden_modules=settings.security.forbidden_modules,
        key_rotation_interval=settings.security.key_rotation_interval,
    )
    security.permissions.grant("cli", {"*"})

    model_manager = UnifiedModelManager([provider.model_dump() for provider in settings.providers])
    memory = UnifiedMemorySystem(settings.memory.database)
    planner = UnifiedAdvancedPlanner(
        max_parallel_tasks=settings.planner.max_parallel_tasks,
        recovery_retries=settings.planner.recovery_retries,
    )
    plugin_paths = [Path("plugins"), Path.home() / ".vortex" / "plugins"]
    plugins = UnifiedPluginSystem(plugin_paths, sandbox=security.sandbox.clone())
    ui = UnifiedRichUI(theme=settings.ui.theme, enable_progress=settings.ui.enable_progress)

    data_analyst = UnifiedDataAnalyst(model_manager)
    vision = UnifiedVisionPro(model_manager)
    audio = UnifiedAudioSystem(model_manager)
    code = UnifiedCodeIntelligence(model_manager)

    context = RuntimeContext(
        settings=settings,
        config_manager=config_manager,
        model_manager=model_manager,
        memory=memory,
        planner=planner,
        plugins=plugins,
        security=security,
        ui=ui,
        data_analyst=data_analyst,
        vision=vision,
        audio=audio,
        code=code,
    )
    set_runtime(context)
    config_manager.start_watching()
    logger.info("Runtime initialised")


def main() -> None:
    asyncio.run(_initialise_runtime())
    app()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
