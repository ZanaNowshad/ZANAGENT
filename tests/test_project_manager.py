from pathlib import Path

import pytest

from vortex.orchestration import PipelineManager, ProjectManager, RoadmapPlanner
from vortex.performance.monitor import PerformanceMonitor


@pytest.mark.asyncio
async def test_project_init_status_and_plan(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "project.yml").write_text(
        """
name: Alpha
vision: Build resilient pipelines
milestones:
  - id: ms-1
    name: Foundation
    description: Setup CI
    due: 2024-01-01
pipelines:
  build:
    stages:
      - name: lint
        connector: docker
        config:
          image: lint
      - name: tests
        connector: docker
        config:
          image: tests
""",
        encoding="utf-8",
    )
    team_root = tmp_path / "teams"
    team_root.mkdir()
    (team_root / "teamA").mkdir()
    (team_root / "teamA" / "ledger.json").write_text(
        "[{\"tokens\": 10, \"minutes\": 5}]", encoding="utf-8"
    )
    monitor = PerformanceMonitor()
    pipeline_manager = PipelineManager(root=tmp_path / "pipelines", monitor=monitor)
    roadmap = RoadmapPlanner(root=tmp_path / "projects", planner=None)
    manager = ProjectManager(
        pipeline_manager,
        roadmap,
        monitor=monitor,
        root=tmp_path / "projects",
        team_root=team_root,
    )
    state = await manager.init_project(repo, owner="alice", team_id="teamA")
    assert state.metadata["name"] == "Alpha"
    status = await manager.status(state.project_id)
    assert status.ledger_totals["tokens"] == 10
    summary = await manager.plan_roadmap(state.project_id, [repo / "project.yml"])
    assert summary.backlog_size >= 1
    release = await manager.record_release(state.project_id, "1.0.0", summary="Initial", author="alice")
    assert release.version == "1.0.0"


@pytest.mark.asyncio
async def test_project_governance_and_milestones(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "project.yml").write_text(
        """
name: Beta
milestones:
  - id: core
    name: Core Platform
    description: Ship MVP
settings:
  policies:
    coverage: 0.95
    license: Apache-2.0
license: GPL-3.0
metrics:
  coverage: 0.80
pipelines:
  deploy:
    stages:
      - name: build
        connector: gitlab
        config:
          job: build
      - name: release
        connector: circleci
        config:
          workflow: release
""",
        encoding="utf-8",
    )
    team_root = tmp_path / "teams"
    team_root.mkdir()
    (team_root / "beta-team").mkdir()
    (team_root / "beta-team" / "ledger.json").write_text("not-json", encoding="utf-8")

    monitor = PerformanceMonitor()
    pipeline_manager = PipelineManager(root=tmp_path / "pipelines", monitor=monitor)
    roadmap = RoadmapPlanner(root=tmp_path / "projects", planner=None)
    manager = ProjectManager(
        pipeline_manager,
        roadmap,
        monitor=monitor,
        root=tmp_path / "projects",
        team_root=team_root,
    )

    state = await manager.init_project(repo, owner="bob", team_id="beta-team")
    assert state.metadata["owner"] == "bob"

    projects = await manager.list_projects()
    assert state.project_id in projects

    await manager.record_release(state.project_id, "0.1.0", summary="preview", author="bob")
    rolled = await manager.rollback_release(state.project_id, "0.1.0", reason="bug", actor="ops")
    assert rolled.status == "rolled_back"

    progress = await manager.milestone_progress(state.project_id, "core", status="in_progress", tokens=5.0, minutes=30.0)
    assert progress.tokens_spent >= 5.0
    new_milestone = await manager.milestone_progress(state.project_id, "ops", status="planned", tokens=2.0, minutes=10.0)
    assert new_milestone.identifier == "ops"

    audit = await manager.governance_audit(state.project_id)
    assert audit["project"] == state.project_id
    assert audit["checks"]

    status = await manager.status(state.project_id)
    assert any(m.identifier == "ops" for m in status.milestones)
