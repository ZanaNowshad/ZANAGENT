import asyncio

import pytest

from vortex.performance import PerformanceMonitor
from vortex.workflow import MacroSystem, WorkflowEngine, WorkflowScheduler


@pytest.mark.asyncio
async def test_workflow_engine_executes_steps() -> None:
    monitor = PerformanceMonitor()
    engine = WorkflowEngine(monitor)

    async def step_a(payload):
        await asyncio.sleep(0)
        return {"a": "done"}

    engine.register("a", step_a)
    result = await engine.execute({})
    assert result["a"] == "done"


@pytest.mark.asyncio
async def test_macro_system_records() -> None:
    system = MacroSystem()
    await system.register("build", "Run build", [lambda: "compile"])
    macros = await system.list_macros()
    assert macros and macros[0].name == "build"
    outputs = await system.run("build")
    assert outputs == ["compile"]


@pytest.mark.asyncio
async def test_scheduler_runs_job() -> None:
    scheduler = WorkflowScheduler()
    result = {}

    async def job():
        result["ran"] = True

    await scheduler.schedule("test", 0.01, job)
    await asyncio.sleep(0.05)
    assert result.get("ran")
    await scheduler.shutdown()
