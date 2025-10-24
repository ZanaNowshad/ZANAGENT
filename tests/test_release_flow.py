from pathlib import Path

import pytest

from vortex.orchestration import PipelineManager, ProjectManager, RoadmapPlanner
from vortex.performance.monitor import PerformanceMonitor


@pytest.mark.asyncio
async def test_release_and_rollback(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monitor = PerformanceMonitor()
    pipeline_manager = PipelineManager(root=tmp_path / "pipelines", monitor=monitor)
    roadmap = RoadmapPlanner(root=tmp_path / "projects", planner=None)
    manager = ProjectManager(pipeline_manager, roadmap, monitor=monitor, root=tmp_path / "projects")
    state = await manager.init_project(repo, owner="shipper")
    release = await manager.record_release(state.project_id, "2.0.0", summary="Major", author="shipper", status="ready")
    assert release.status == "ready"
    rolled = await manager.rollback_release(state.project_id, "2.0.0", reason="tests failed", actor="shipper")
    assert rolled.status == "rolled_back"
