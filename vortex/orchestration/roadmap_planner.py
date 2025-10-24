"""Roadmap planning utilities for project orchestration."""
from __future__ import annotations

import asyncio
import json
import re
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import yaml

from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RoadmapItem:
    """Represents an individual task extracted from a backlog."""

    title: str
    description: str
    owner: Optional[str] = None
    estimate_hours: float = 0.0
    tags: Sequence[str] = field(default_factory=tuple)


@dataclass
class RoadmapMilestone:
    """Milestone grouping related roadmap items."""

    name: str
    due: Optional[str]
    tasks: List[RoadmapItem] = field(default_factory=list)


@dataclass
class RoadmapSummary:
    """Structured summary persisted to disk for reuse by the CLI/TUI."""

    project_id: str
    generated_at: float
    milestones: List[RoadmapMilestone]
    backlog_size: int

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "generated_at": self.generated_at,
            "backlog_size": self.backlog_size,
            "milestones": [
                {
                    "name": milestone.name,
                    "due": milestone.due,
                    "tasks": [
                        {
                            "title": task.title,
                            "description": task.description,
                            "owner": task.owner,
                            "estimate_hours": task.estimate_hours,
                            "tags": list(task.tags),
                        }
                        for task in milestone.tasks
                    ],
                }
                for milestone in self.milestones
            ],
        }


class RoadmapPlanner:
    """Generate actionable project roadmaps from heterogeneous backlogs."""

    def __init__(
        self,
        *,
        nlp_engine: Optional[object] = None,
        planner: Optional[object] = None,
        root: Optional[Path] = None,
    ) -> None:
        # We intentionally accept ``object`` to avoid importing heavy optional
        # dependencies at import time; the runtime wires concrete instances.
        self._nlp = nlp_engine
        self._planner = planner
        self._root = root or Path.home() / ".vortex" / "projects"
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def generate(
        self,
        project_id: str,
        sources: Iterable[str | Path],
        *,
        title: Optional[str] = None,
    ) -> RoadmapSummary:
        """Create a roadmap from issue trackers, markdown files, or JSON dumps."""

        async with self._lock:
            text = await asyncio.to_thread(self._load_sources, sources)
            items = self._parse_backlog(text)
            milestones = self._group_items(items, title or project_id)
            summary = RoadmapSummary(
                project_id=project_id,
                generated_at=datetime.now(timezone.utc).timestamp(),
                milestones=milestones,
                backlog_size=len(items),
            )
            await asyncio.to_thread(self._persist, project_id, summary)
            logger.info(
                "roadmap generated",
                extra={"project_id": project_id, "tasks": len(items)},
            )
            return summary

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_sources(self, sources: Iterable[str | Path]) -> str:
        chunks: List[str] = []
        for source in sources:
            path = Path(source)
            try:
                if path.exists():
                    chunks.append(path.read_text(encoding="utf-8"))
                    continue
            except OSError:
                logger.debug("source treated as inline text", extra={"source": str(source)[:40]})
            chunks.append(str(source))
        return "\n".join(chunks)

    def _parse_backlog(self, text: str) -> List[RoadmapItem]:
        """Extract bullet lists, markdown headings, and JSON issue dumps."""

        items: List[RoadmapItem] = []
        bullet_pattern = re.compile(r"^[\-\*]\s+(.*)$", re.MULTILINE)
        for match in bullet_pattern.finditer(text):
            title = match.group(1).strip()
            if not title:
                continue
            items.append(self._make_item(title, title))
        # rudimentary markdown issue extraction
        heading_pattern = re.compile(r"^#+\s+(.*)$", re.MULTILINE)
        for match in heading_pattern.finditer(text):
            title = match.group(1).strip()
            if title and not any(item.title == title for item in items):
                items.append(self._make_item(title, title))
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                payload = payload.get("issues") or payload.get("tickets") or payload
            if isinstance(payload, list):
                for issue in payload:
                    if not isinstance(issue, dict):
                        continue
                    title = str(issue.get("title") or issue.get("summary") or "Untitled")
                    description = str(issue.get("body") or issue.get("description") or title)
                    owner = issue.get("assignee") or issue.get("owner")
                    estimate = float(issue.get("estimate_hours") or 0.0)
                    tags = issue.get("labels") or issue.get("tags") or []
                    items.append(
                        RoadmapItem(
                            title=title,
                            description=description,
                            owner=str(owner) if owner else None,
                            estimate_hours=estimate,
                            tags=tuple(str(tag) for tag in tags),
                        )
                    )
        except json.JSONDecodeError:
            # Not JSON content, ignore.
            pass
        try:
            yaml_doc = yaml.safe_load(text)
            items.extend(self._extract_yaml_items(yaml_doc))
        except yaml.YAMLError:
            logger.debug("failed to parse yaml backlog", exc_info=True)
        return items

    def _make_item(self, title: str, description: str) -> RoadmapItem:
        description = self._summarise(description)
        return RoadmapItem(title=title, description=description, estimate_hours=4.0)

    def _summarise(self, text: str) -> str:
        if hasattr(self._nlp, "summarise"):
            try:
                summary = self._nlp.summarise(text)
                if isinstance(summary, str):
                    return summary
            except Exception:  # pragma: no cover - NLP backends are optional
                logger.debug("nlp summarise failed", exc_info=True)
        return textwrap.shorten(text, width=160, placeholder="…")

    def _group_items(self, items: Sequence[RoadmapItem], title: str) -> List[RoadmapMilestone]:
        if not items:
            return []
        bucket_size = max(1, len(items) // 3)
        milestones: List[RoadmapMilestone] = []
        for index, start in enumerate(range(0, len(items), bucket_size), start=1):
            bucket = list(items[start : start + bucket_size])
            due = datetime.now(timezone.utc) + timedelta(days=14 * index)
            milestone = RoadmapMilestone(
                name=f"Milestone {index}: {title}",
                due=due.astimezone(timezone.utc).strftime("%Y-%m-%d"),
                tasks=list(bucket),
            )
            milestones.append(milestone)
        if hasattr(self._planner, "add_task"):
            for milestone in milestones:
                for task in milestone.tasks:
                    try:
                        self._planner.add_task(
                            {
                                "name": task.title,
                                "description": task.description,
                                "due": milestone.due,
                            }
                        )
                    except Exception:  # pragma: no cover - planner optional
                        logger.debug("planner rejected task", exc_info=True)
        return milestones

    def _extract_yaml_items(self, document: object) -> List[RoadmapItem]:
        items: List[RoadmapItem] = []
        if not isinstance(document, dict):
            return items
        milestones = document.get("milestones") or []
        if isinstance(milestones, list):
            for milestone in milestones:
                if not isinstance(milestone, dict):
                    continue
                title = str(milestone.get("name") or milestone.get("id") or "Milestone")
                description = str(milestone.get("description") or title)
                items.append(self._make_item(title, description))
                tasks = milestone.get("tasks") or milestone.get("stories") or []
                if isinstance(tasks, list):
                    for task in tasks:
                        if isinstance(task, dict):
                            task_title = str(task.get("title") or task.get("name") or title)
                            task_desc = str(task.get("description") or task_title)
                            items.append(self._make_item(task_title, task_desc))
                        elif isinstance(task, str):
                            items.append(self._make_item(task, task))
        pipelines = document.get("pipelines") or {}
        if isinstance(pipelines, dict):
            for pipeline_name, pipeline in pipelines.items():
                if not isinstance(pipeline, dict):
                    continue
                stages = pipeline.get("stages") or []
                for stage in stages:
                    if not isinstance(stage, dict):
                        continue
                    stage_name = str(stage.get("name") or "stage")
                    description = json.dumps(stage.get("config", {}), ensure_ascii=False)
                    items.append(
                        RoadmapItem(
                            title=f"{pipeline_name}:{stage_name}",
                            description=self._summarise(description),
                            estimate_hours=float(stage.get("estimate_hours", 2.0)),
                            tags=("pipeline", pipeline_name),
                        )
                    )
        backlog = document.get("backlog") or []
        if isinstance(backlog, list):
            for entry in backlog:
                if isinstance(entry, dict):
                    title = str(entry.get("title") or entry.get("name") or "Backlog item")
                    description = str(entry.get("description") or title)
                    owner = entry.get("owner")
                    estimate = float(entry.get("estimate_hours") or entry.get("estimate", 0.0) or 0.0)
                    tags = entry.get("tags") or entry.get("labels") or []
                    items.append(
                        RoadmapItem(
                            title=title,
                            description=self._summarise(description),
                            owner=str(owner) if owner else None,
                            estimate_hours=estimate or 4.0,
                            tags=tuple(str(tag) for tag in tags),
                        )
                    )
                elif isinstance(entry, str):
                    items.append(self._make_item(entry, entry))
        return items

    def _persist(self, project_id: str, summary: RoadmapSummary) -> None:
        project_dir = self._root / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        path = project_dir / "roadmap.json"
        path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
        yaml_path = project_dir / "roadmap.yml"
        yaml_path.write_text(yaml.safe_dump(summary.to_dict(), sort_keys=False), encoding="utf-8")


__all__ = ["RoadmapPlanner", "RoadmapSummary", "RoadmapMilestone", "RoadmapItem"]
