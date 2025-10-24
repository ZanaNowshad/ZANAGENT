from pathlib import Path

import pytest

from vortex.orchestration import PipelineManager, ProjectManager, RoadmapPlanner
from vortex.performance.monitor import PerformanceMonitor


@pytest.mark.asyncio
async def test_governance_audit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "project.yml").write_text(
        """
name: Compliance
vision: Ensure policies
settings:
  policies:
    coverage: 0.8
    license: MIT
metrics:
  coverage: 0.85
license: MIT
""",
        encoding="utf-8",
    )
    monitor = PerformanceMonitor()
    pipeline_manager = PipelineManager(root=tmp_path / "pipelines", monitor=monitor)
    roadmap = RoadmapPlanner(root=tmp_path / "projects", planner=None)
    manager = ProjectManager(pipeline_manager, roadmap, monitor=monitor, root=tmp_path / "projects")
    state = await manager.init_project(repo, owner="auditor")
    report = await manager.governance_audit(state.project_id)
    assert report["status"] in {"pass", "warn"}
    assert report["checks"]
