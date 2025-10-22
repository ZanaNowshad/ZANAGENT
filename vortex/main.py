"""Main entrypoint initialising the Vortex runtime."""
from __future__ import annotations

import asyncio
from pathlib import Path

from vortex.ai import AdvancedCodeIntelligence, ContextManager, ContinuousLearningSystem, NLPEngine
from vortex.cli.app import RuntimeContext, app, set_runtime
from vortex.core.config import UnifiedConfigManager
from vortex.core.memory import UnifiedMemorySystem
from vortex.core.model import UnifiedModelManager
from vortex.core.planner import UnifiedAdvancedPlanner
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
from vortex.utils.logging import configure_logging, get_logger
from vortex.workflow import MacroSystem, WorkflowEngine, WorkflowScheduler

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
    await security.access_control.define_role("mobile", {"mobile:invoke"})
    await security.access_control.assign_role("cli", "mobile")

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

    api_hub = APIHub(security)
    database = DatabaseManager(settings.memory.database, security)
    cloud = CloudIntegration(security)
    git = GitManager(security)
    ai_context = ContextManager(model_manager, memory)
    ai_learning = ContinuousLearningSystem(memory)
    ai_nlp = NLPEngine()
    ai_code = AdvancedCodeIntelligence(model_manager)
    perf_monitor = PerformanceMonitor()
    perf_analytics = PerformanceAnalytics(perf_monitor)
    cost_tracker = CostTracker(model_manager)
    cache_manager = CacheManager()
    connection_pool = ConnectionPool()
    lazy_loader = LazyLoader()
    parallel_processor = ParallelProcessor()
    workflow_engine = WorkflowEngine(perf_monitor)
    macro_system = MacroSystem()
    scheduler = WorkflowScheduler()
    web_ui = WebUI()
    desktop_gui = DesktopGUI()
    mobile_api = MobileAPI(security)
    rich_bridge = RichUIBridge(ui)
    test_framework = TestFramework(root=Path("tests"))
    devtools = DevToolsSuite(test_framework)
    debugger = Debugger()
    devops = DevOpsHelper()
    learning_mode = LearningMode(ai_context)
    code_explainer = CodeExplainer(ai_code)
    multiagent = MultiAgentCoordinator(model_manager)

    async def _echo_agent(message: str) -> str:
        return f"echo:{message}"

    multiagent.register("echo", _echo_agent)
    self_improvement = SelfImprovementLoop(lambda idea: float(len(idea)))
    predictor = Predictor(ai_nlp)

    await ai_learning.bootstrap_from_memory()

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
        api_hub=api_hub,
        database=database,
        cloud=cloud,
        git=git,
        ai_context=ai_context,
        ai_learning=ai_learning,
        ai_nlp=ai_nlp,
        ai_code=ai_code,
        perf_monitor=perf_monitor,
        perf_analytics=perf_analytics,
        cost_tracker=cost_tracker,
        cache_manager=cache_manager,
        connection_pool=connection_pool,
        lazy_loader=lazy_loader,
        parallel_processor=parallel_processor,
        workflow_engine=workflow_engine,
        macro_system=macro_system,
        scheduler=scheduler,
        web_ui=web_ui,
        desktop_gui=desktop_gui,
        mobile_api=mobile_api,
        rich_bridge=rich_bridge,
        devtools=devtools,
        test_framework=test_framework,
        debugger=debugger,
        devops=devops,
        learning_mode=learning_mode,
        code_explainer=code_explainer,
        multiagent=multiagent,
        self_improvement=self_improvement,
        predictor=predictor,
    )
    set_runtime(context)
    config_manager.start_watching()
    logger.info("Runtime initialised")


def main() -> None:
    asyncio.run(_initialise_runtime())
    app()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
