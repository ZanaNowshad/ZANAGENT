import json
from pathlib import Path

import pytest

from vortex.orchestration.roadmap_planner import RoadmapPlanner


class _StubPlanner:
    def __init__(self) -> None:
        self.added: list[dict[str, str]] = []

    def add_task(self, payload: dict[str, str]) -> None:
        self.added.append(payload)


class _StubNLP:
    def summarise(self, text: str) -> str:
        return text.upper()[:32]


@pytest.mark.asyncio
async def test_roadmap_planner_parses_sources(tmp_path: Path) -> None:
    planner_stub = _StubPlanner()
    nlp_stub = _StubNLP()
    planner = RoadmapPlanner(root=tmp_path, planner=planner_stub, nlp_engine=nlp_stub)

    yaml_source = """
milestones:
  - id: ms1
    name: Core
    description: build core
    tasks:
      - title: Provision
        description: provision infrastructure
backlog:
  - Fix login
  - title: Improve docs
    description: write better documentation
pipelines:
  ship:
    stages:
      - name: plan
        connector: docker
        config:
          image: plan
      - name: deploy
        connector: docker
        config:
          image: deploy
"""
    bullets = "- integrate API\n# Finish polish\n"
    json_issues = json.dumps({"issues": [{"title": "Bug", "body": "Fix bug", "labels": ["bug"]}]})

    yaml_path = tmp_path / "backlog.yml"
    yaml_path.write_text(yaml_source, encoding="utf-8")

    summary_yaml = await planner.generate("demo", [yaml_path])
    summary_mix = await planner.generate("demo-mix", [bullets])
    summary_json = await planner.generate("demo-json", [json_issues])
    summary_headings = await planner.generate("demo-head", ["# Follow up\n- Review code"])

    assert summary_yaml.backlog_size >= 4
    assert summary_yaml.milestones
    assert summary_mix.backlog_size >= 1
    assert summary_json.backlog_size >= 1
    assert summary_headings.backlog_size >= 1
    assert planner_stub.added  # planner stub collected tasks

    roadmap_path = tmp_path / "demo" / "roadmap.json"
    assert roadmap_path.exists()
    persisted = json.loads(roadmap_path.read_text(encoding="utf-8"))
    assert persisted["backlog_size"] == summary_yaml.backlog_size
