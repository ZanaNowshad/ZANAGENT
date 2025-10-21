"""Typer-based CLI wiring."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import typer

from vortex.ai import AdvancedCodeIntelligence, ContextManager, ContinuousLearningSystem, NLPEngine
from vortex.core.config import UnifiedConfigManager, VortexSettings
from vortex.core.memory import UnifiedMemorySystem
from vortex.core.model import UnifiedModelManager
from vortex.core.planner import TaskSpec, UnifiedAdvancedPlanner
from vortex.core.plugin import UnifiedPluginSystem
from vortex.core.ui import UnifiedRichUI
from vortex.devtools import Debugger, DevOpsHelper, DevToolsSuite, TestFramework
from vortex.education import CodeExplainer, LearningMode
from vortex.experimental import MultiAgentCoordinator, Predictor, SelfImprovementLoop
from vortex.integration import APIHub, CloudIntegration, DatabaseManager, GitManager
from vortex.intelligence import (
    UnifiedAudioSystem,
    UnifiedCodeIntelligence,
    UnifiedDataAnalyst,
    UnifiedVisionPro,
)
from vortex.performance import (
    CacheManager,
    ConnectionPool,
    CostTracker,
    LazyLoader,
    ParallelProcessor,
    PerformanceAnalytics,
    PerformanceMonitor,
)
from vortex.security.manager import UnifiedSecurityManager
from vortex.ui import DesktopGUI, MobileAPI, RichUIBridge, WebUI
from vortex.utils.errors import MemoryError, ProviderError, SecurityError, WorkflowError
from vortex.utils.logging import configure_logging, get_logger
from vortex.workflow import MacroSystem, WorkflowEngine, WorkflowScheduler

logger = get_logger(__name__)

app = typer.Typer(help="Vortex AI agent framework")
plugin_app = typer.Typer(help="Manage plugins")
config_app = typer.Typer(help="Inspect and reload configuration")
memory_app = typer.Typer(help="Manage memory store")
ai_app = typer.Typer(help="AI utilities")
workflow_app = typer.Typer(help="Workflow orchestration")
perf_app = typer.Typer(help="Performance metrics")
integration_app = typer.Typer(help="External integrations")
dev_app = typer.Typer(help="Developer tooling")
experimental_app = typer.Typer(help="Experimental features")
education_app = typer.Typer(help="Educational helpers")
app.add_typer(plugin_app, name="plugin")
app.add_typer(config_app, name="config")
app.add_typer(memory_app, name="memory")
app.add_typer(ai_app, name="ai")
app.add_typer(workflow_app, name="workflow")
app.add_typer(perf_app, name="perf")
app.add_typer(integration_app, name="integration")
app.add_typer(dev_app, name="dev")
app.add_typer(experimental_app, name="experimental")
app.add_typer(education_app, name="education")


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
    api_hub: APIHub
    database: DatabaseManager
    cloud: CloudIntegration
    git: GitManager
    ai_context: ContextManager
    ai_learning: ContinuousLearningSystem
    ai_nlp: NLPEngine
    ai_code: AdvancedCodeIntelligence
    perf_monitor: PerformanceMonitor
    perf_analytics: PerformanceAnalytics
    cost_tracker: CostTracker
    cache_manager: CacheManager
    connection_pool: ConnectionPool
    lazy_loader: LazyLoader
    parallel_processor: ParallelProcessor
    workflow_engine: WorkflowEngine
    macro_system: MacroSystem
    scheduler: WorkflowScheduler
    web_ui: WebUI
    desktop_gui: DesktopGUI
    mobile_api: MobileAPI
    rich_bridge: RichUIBridge
    devtools: DevToolsSuite
    test_framework: TestFramework
    debugger: Debugger
    devops: DevOpsHelper
    learning_mode: LearningMode
    code_explainer: CodeExplainer
    multiagent: MultiAgentCoordinator
    self_improvement: SelfImprovementLoop
    predictor: Predictor


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
def tui(
    resume: bool = typer.Option(False, "--resume/--no-resume", help="Resume the previous session"),
    theme: str = typer.Option("auto", "--theme", "-t", help="Theme: auto, dark, or light"),
    no_color: bool = typer.Option(False, "--no-color", help="Disable colour output"),
    screen_reader: bool = typer.Option(
        False,
        "--screen-reader/--no-screen-reader",
        help="Enable announcements for assistive technologies",
    ),
) -> None:
    """Launch the Textual TUI shell."""

    ctx = _require_runtime()
    from vortex.ui_tui import TUIOptions, launch_tui

    if theme not in {"auto", "dark", "light"}:
        raise typer.BadParameter("Theme must be auto, dark, or light")

    options = TUIOptions(
        resume=resume,
        color_scheme=theme,
        no_color=no_color,
        screen_reader=screen_reader,
    )
    asyncio.run(launch_tui(ctx, options))


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


@ai_app.command("summary")
def ai_summary() -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        summary = await ctx.ai_context.summarise()
        ctx.ui.info(summary or "No context captured yet")

    asyncio.run(_run())


@ai_app.command("sentiment")
def ai_sentiment(text: str) -> None:
    ctx = _require_runtime()
    score = ctx.ai_nlp.sentiment(text)
    ctx.ui.info(f"Sentiment score: {score:.2f}")


@ai_app.command("feedback")
def ai_feedback(category: str, score: int) -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        await ctx.ai_learning.record_feedback(category, score)
        average = await ctx.ai_learning.average_score(category)
        ctx.ui.info(f"Average score for {category}: {average:.2f}")

    asyncio.run(_run())


@workflow_app.command("run")
def workflow_run(file: Path) -> None:
    ctx = _require_runtime()
    steps = json.loads(file.read_text())
    ctx.workflow_engine = WorkflowEngine(ctx.perf_monitor)

    for spec in steps:
        step_name = spec["name"]

        async def _action(payload: Dict[str, Any], message: str = spec.get("message", "done"), name: str = step_name) -> Dict[str, Any]:
            await asyncio.sleep(0)
            ctx.ui.info(message)
            return {name: message}

        ctx.workflow_engine.register(
            step_name,
            _action,
            depends_on=spec.get("depends_on", []),
        )

    async def _run() -> None:
        try:
            result = await ctx.workflow_engine.execute({})
            ctx.ui.console.print(result)
        except WorkflowError as exc:
            ctx.ui.error(str(exc))

    asyncio.run(_run())


@workflow_app.command("macros")
def workflow_macros() -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        macros = await ctx.macro_system.list_macros()
        rows = [[macro.name, macro.description, str(len(macro.steps))] for macro in macros]
        table = ctx.ui.table("Macros", ["Name", "Description", "Steps"], rows)
        ctx.ui.console.print(table)

    asyncio.run(_run())


@perf_app.command("metrics")
def perf_metrics() -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        snapshot = await ctx.perf_analytics.snapshot()
        ctx.ui.console.print(snapshot)

    asyncio.run(_run())


@perf_app.command("costs")
def perf_costs() -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        total = await ctx.cost_tracker.total_cost()
        ctx.ui.info(f"Estimated spend: ${total:.4f}")

    asyncio.run(_run())


@integration_app.command("git-status")
def integration_git_status() -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        result = await ctx.git.status()
        ctx.ui.console.print(result.stdout or result.stderr)

    asyncio.run(_run())


@integration_app.command("apis")
def integration_list_apis() -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        names = await ctx.api_hub.list_apis()
        ctx.ui.console.print({"apis": names})

    asyncio.run(_run())


@integration_app.command("cloud")
def integration_list_cloud() -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        names = await ctx.cloud.list_accounts()
        ctx.ui.console.print({"accounts": names})

    asyncio.run(_run())


@dev_app.command("tests")
def dev_run_tests() -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        report = await ctx.devtools.run_tests("tests")
        ctx.ui.console.print(report)

    asyncio.run(_run())


@dev_app.command("health")
def dev_health() -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        info = await ctx.devtools.health_check()
        ctx.ui.console.print(info)

    asyncio.run(_run())


@experimental_app.command("broadcast")
def experimental_broadcast(message: str) -> None:
    ctx = _require_runtime()

    async def _run() -> None:
        result = await ctx.multiagent.broadcast(message)
        ctx.ui.console.print(result)

    asyncio.run(_run())


@education_app.command("explain")
def education_explain(description: str, file: Path) -> None:
    ctx = _require_runtime()
    source = file.read_text()

    async def _run() -> None:
        report = await ctx.code_explainer.explain(description, source)
        ctx.ui.console.print(report)

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


def main() -> None:
    """Console script entry point used by setuptools."""

    if runtime is None:
        # Import lazily to avoid circular imports when bootstrapping the CLI.
        from vortex.main import main as bootstrap_main

        bootstrap_main()
    else:
        app()


__all__ = ["app", "set_runtime", "RuntimeContext", "main"]
