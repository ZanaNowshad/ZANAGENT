"""Typer-based CLI wiring."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import typer

from vortex.core.config import UnifiedConfigManager, VortexSettings
from vortex.core.memory import UnifiedMemorySystem
from vortex.core.model import UnifiedModelManager
from vortex.core.planner import TaskSpec, UnifiedAdvancedPlanner
from vortex.core.plugin import UnifiedPluginSystem
from vortex.core.ui import UnifiedRichUI
from vortex.intelligence import (
    UnifiedAudioSystem,
    UnifiedCodeIntelligence,
    UnifiedDataAnalyst,
    UnifiedVisionPro,
)
from vortex.security.manager import UnifiedSecurityManager
from vortex.utils.errors import MemoryError, ProviderError, SecurityError
from vortex.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)

app = typer.Typer(help="Vortex AI agent framework")
plugin_app = typer.Typer(help="Manage plugins")
config_app = typer.Typer(help="Inspect and reload configuration")
memory_app = typer.Typer(help="Manage memory store")
app.add_typer(plugin_app, name="plugin")
app.add_typer(config_app, name="config")
app.add_typer(memory_app, name="memory")


@dataclass
class RuntimeContext:
    settings: VortexSettings
    config_manager: UnifiedConfigManager
    model_manager: UnifiedModelManager
    memory: UnifiedMemorySystem
    planner: UnifiedAdvancedPlanner
    plugins: UnifiedPluginSystem
    security: UnifiedSecurityManager
    ui: UnifiedRichUI
    data_analyst: UnifiedDataAnalyst
    vision: UnifiedVisionPro
    audio: UnifiedAudioSystem
    code: UnifiedCodeIntelligence


runtime: Optional[RuntimeContext] = None


def set_runtime(value: RuntimeContext) -> None:
    global runtime
    runtime = value


def _require_runtime() -> RuntimeContext:
    if runtime is None:  # pragma: no cover - runtime is always set during CLI usage
        raise RuntimeError("Runtime not initialised")
    return runtime


@app.command()
def run(prompt: str = typer.Option(..., help="Prompt to send to the model")) -> None:
    """Execute a one-off prompt using the orchestrated providers."""

    ctx = _require_runtime()

    async def _run() -> None:
        try:
            result = await ctx.model_manager.generate(prompt)
            ctx.ui.print_header("Vortex Response")
            ctx.ui.info(result["text"])
        except ProviderError as exc:
            ctx.ui.error(str(exc))

    asyncio.run(_run())


@app.command()
def plan(file: Path = typer.Option(..., help="Path to JSON plan definition")) -> None:
    """Execute a plan defined in JSON format."""

    ctx = _require_runtime()
    tasks_data = json.loads(file.read_text())
    for item in tasks_data:
        async def _action(message: str = item.get("message", "task complete")) -> None:
            ctx.ui.info(message)
            await asyncio.sleep(0)

        task = TaskSpec(
            name=item["name"],
            description=item.get("description", ""),
            action=_action,
            depends_on=set(item.get("depends_on", [])),
            retries=item.get("retries", 0),
        )
        ctx.planner.add_task(task)

    async def _run() -> None:
        results = await ctx.planner.execute()
        table = ctx.ui.table(
            "Plan Results",
            ["Task", "Success"],
            [[r.name, "✅" if r.success else "❌"] for r in results],
        )
        ctx.ui.console.print(table)

    asyncio.run(_run())


@app.command()
def analyze(file: Path = typer.Option(..., help="JSON file mapping column to list of numbers")) -> None:
    ctx = _require_runtime()
    data = json.loads(file.read_text())
    summaries = ctx.data_analyst.summarise(data)
    rows = [[s.column, str(s.count), f"{s.mean:.2f}", f"{s.median:.2f}"] for s in summaries]
    table = ctx.ui.table("Data Summary", ["Column", "Count", "Mean", "Median"], rows)
    ctx.ui.console.print(table)


@plugin_app.command("list")
def plugin_list() -> None:
    ctx = _require_runtime()
    discovered = ctx.plugins.discover()
    rows = [[name, str(path)] for name, path in discovered.items()]
    table = ctx.ui.table("Plugins", ["Name", "Path"], rows)
    ctx.ui.console.print(table)


@plugin_app.command("run")
def plugin_run(name: str, payload: str = typer.Argument(..., help="JSON payload")) -> None:
    ctx = _require_runtime()
    data = json.loads(payload)

    async def _run() -> None:
        try:
            result = await ctx.plugins.execute(name, data)
            ctx.ui.info(f"Plugin result: {result}")
        except SecurityError as exc:
            ctx.ui.error(f"Security violation: {exc}")
        except Exception as exc:  # pragma: no cover - plugin errors environment specific
            ctx.ui.error(f"Plugin failed: {exc}")

    asyncio.run(_run())


@config_app.command("show")
def config_show() -> None:
    ctx = _require_runtime()
    settings = ctx.settings
    ctx.ui.console.print(settings.model_dump())


@config_app.command("reload")
def config_reload() -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        settings = await ctx.config_manager.reload()
        ctx.ui.info("Configuration reloaded")
        ctx.ui.console.print(settings.model_dump())

    asyncio.run(_run())


@memory_app.command("add")
def memory_add(kind: str, content: str) -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        try:
            record = await ctx.memory.add(kind, content)
            ctx.ui.info(f"Stored memory {record.id}")
        except MemoryError as exc:
            ctx.ui.error(str(exc))

    asyncio.run(_run())


@memory_app.command("list")
def memory_list() -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        records = await ctx.memory.list()
        rows = [[str(r.id), r.kind, r.content] for r in records]
        table = ctx.ui.table("Memories", ["ID", "Kind", "Content"], rows)
        ctx.ui.console.print(table)

    asyncio.run(_run())


@memory_app.command("search")
def memory_search(query: str) -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        records = await ctx.memory.search(query)
        rows = [[str(r.id), r.kind, r.content] for r in records]
        table = ctx.ui.table("Search Results", ["ID", "Kind", "Content"], rows)
        ctx.ui.console.print(table)

    asyncio.run(_run())


@app.command()
def shell() -> None:
    """Launch a simple interactive loop."""

    ctx = _require_runtime()
    ctx.ui.print_header("Vortex Shell (type 'exit' to quit)")
    while True:
        prompt = input("> ")
        if prompt.strip().lower() in {"exit", "quit"}:
            break
        result = asyncio.run(ctx.model_manager.generate(prompt))
        ctx.ui.info(result["text"])


__all__ = ["app", "set_runtime", "RuntimeContext"]
