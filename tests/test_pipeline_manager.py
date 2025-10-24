from pathlib import Path

import pytest

from vortex.orchestration import PipelineManager
from vortex.performance.monitor import PerformanceMonitor


@pytest.mark.asyncio
async def test_pipeline_run_and_logs(tmp_path: Path) -> None:
    monitor = PerformanceMonitor()
    manager = PipelineManager(root=tmp_path / "pipelines", monitor=monitor)
    config = {
        "build": {
            "stages": [
                {"name": "lint", "connector": "docker", "config": {"image": "lint"}},
                {"name": "tests", "connector": "docker", "config": {"image": "tests"}},
            ]
        }
    }
    await manager.register_project("alpha", config)
    run = await manager.run("alpha", "build")
    assert run.summary == "success"
    assert len(run.stages) == 2
    history = await manager.logs("alpha", "build")
    assert "Docker" in "\n".join(history)
    status = await manager.status("alpha", "build")
    assert status is not None


@pytest.mark.asyncio
async def test_pipeline_stage_filter_and_dashboard(tmp_path: Path) -> None:
    monitor = PerformanceMonitor()
    manager = PipelineManager(root=tmp_path / "pipelines", monitor=monitor)
    config = {
        "deploy": {
            "environment": "staging",
            "stages": [
                {"name": "plan", "connector": "github_actions", "config": {"workflow": "plan.yml"}},
                {"name": "apply", "connector": "kubernetes", "config": {"deployment": "web", "namespace": "prod"}},
            ],
        }
    }
    await manager.register_project("beta", config)

    run_single = await manager.run("beta", "deploy", stage_name="apply", environment="production")
    assert run_single.stages[0].environment == "production"
    assert run_single.stages[0].logs

    run_full = await manager.run_pipeline("beta", "deploy")
    assert len(run_full.stages) == 2
    table_view = run_full.rich_table()
    assert len(table_view.rows) == 2

    table = await manager.dashboard("beta")
    assert table.title and "beta" in table.title

    logs = await manager.logs("beta", "deploy")
    assert any("Kubernetes" in line for line in logs)

    status = await manager.status("beta", "deploy")
    assert status is not None and status.summary

    pipelines = await manager.list_pipelines("beta")
    assert pipelines == ["deploy"]

    with pytest.raises(ValueError):
        await manager.run("beta", "deploy", stage_name="unknown")
    with pytest.raises(KeyError):
        await manager.run("gamma", "deploy")
    with pytest.raises(ValueError):
        manager._connector({"connector": "unknown"})  # type: ignore[attr-defined]
