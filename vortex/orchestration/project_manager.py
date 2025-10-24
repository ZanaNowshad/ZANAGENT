"""Project lifecycle management primitives."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from vortex.orchestration.pipeline_manager import PipelineManager
from vortex.orchestration.roadmap_planner import (
    RoadmapItem,
    RoadmapMilestone,
    RoadmapPlanner,
    RoadmapSummary,
)
from vortex.performance.monitor import PerformanceMonitor
from vortex.security.audit_system import AuditSystem
from vortex.utils.logging import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path.home() / ".vortex" / "projects"
TEAM_ROOT = Path.home() / ".vortex" / "teams"


@dataclass
class ProjectMilestone:
    identifier: str
    name: str
    description: str
    due: Optional[str]
    status: str = "planned"
    budget_minutes: float = 0.0
    tokens_spent: float = 0.0


@dataclass
class ReleaseRecord:
    version: str
    summary: str
    created_at: float
    author: str
    status: str = "draft"


@dataclass
class ProjectState:
    project_id: str
    root: Path
    metadata: Dict[str, Any]
    milestones: List[ProjectMilestone] = field(default_factory=list)
    releases: List[ReleaseRecord] = field(default_factory=list)
    roadmap: Optional[RoadmapSummary] = None
    ledger_totals: Dict[str, float] = field(default_factory=dict)


class ProjectManager:
    """Coordinate project milestones, roadmap planning, and releases."""

    def __init__(
        self,
        pipeline_manager: PipelineManager,
        roadmap_planner: RoadmapPlanner,
        *,
        monitor: Optional[PerformanceMonitor] = None,
        root: Optional[Path] = None,
        team_root: Optional[Path] = None,
        audit: Optional[AuditSystem] = None,
    ) -> None:
        self._pipeline_manager = pipeline_manager
        self._roadmap_planner = roadmap_planner
        self._root = root or PROJECT_ROOT
        self._root.mkdir(parents=True, exist_ok=True)
        self._team_root = team_root or TEAM_ROOT
        self._team_root.mkdir(parents=True, exist_ok=True)
        self._monitor = monitor or PerformanceMonitor()
        self._lock = asyncio.Lock()
        audit_path = self._root / "project.audit.jsonl"
        self._audit = audit or AuditSystem(audit_path)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def init_project(
        self,
        repository: Path,
        *,
        owner: str,
        name: Optional[str] = None,
        vision: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> ProjectState:
        """Register a repository as a managed project."""

        project_id = self._slugify(name or repository.name)
        project_dir = self._root / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        async with self._lock:
            config = self._load_project_config(repository)
            metadata = {
                "name": name or config.get("name") or repository.name,
                "vision": vision or config.get("vision", ""),
                "owner": owner,
                "repository": str(repository),
                "team_id": team_id,
                "pipelines": config.get("pipelines", {}),
                "milestones": config.get("milestones", []),
                "settings": config.get("settings", {}),
            }
            self._persist_metadata(project_dir, metadata)
            await self._pipeline_manager.register_project(project_id, metadata["pipelines"])
            await self._audit.log(
                actor=owner,
                action="project-init",
                metadata={"project": project_id, "repo": str(repository)},
            )
            state = await self.status(project_id)
            logger.info("project registered", extra={"project_id": project_id})
            return state

    async def list_projects(self) -> List[str]:
        async with self._lock:
            return sorted(item.name for item in self._root.iterdir() if item.is_dir())

    async def status(self, project_id: str) -> ProjectState:
        project_dir = self._root / project_id
        metadata = self._read_metadata(project_dir)
        milestones = [
            ProjectMilestone(
                identifier=entry.get("id", f"ms-{index+1}"),
                name=entry.get("name", "Untitled"),
                description=entry.get("description", ""),
                due=entry.get("due"),
                status=entry.get("status", "planned"),
                budget_minutes=float(entry.get("budget_minutes", 0.0)),
                tokens_spent=float(entry.get("tokens", 0.0)),
            )
            for index, entry in enumerate(metadata.get("milestones", []))
        ]
        releases = self._load_releases(project_dir)
        roadmap = self._load_roadmap(project_dir)
        ledger = self._load_team_ledger(metadata.get("team_id"))
        state = ProjectState(
            project_id=project_id,
            root=project_dir,
            metadata=metadata,
            milestones=milestones,
            releases=releases,
            roadmap=roadmap,
            ledger_totals=ledger,
        )
        return state

    async def plan_roadmap(
        self,
        project_id: str,
        sources: Iterable[str | Path],
        *,
        title: Optional[str] = None,
    ) -> RoadmapSummary:
        logger.debug("planning roadmap", extra={"project_id": project_id})
        async with self._monitor.track("roadmap_generate", project=project_id):
            summary = await self._roadmap_planner.generate(project_id, sources, title=title)
        await self._audit.log(
            actor="planner",
            action="roadmap",
            metadata={"project": project_id, "milestones": len(summary.milestones)},
        )
        return summary

    async def record_release(
        self,
        project_id: str,
        version: str,
        *,
        summary: str,
        author: str,
        status: str = "pending",
    ) -> ReleaseRecord:
        project_dir = self._root / project_id
        release = ReleaseRecord(
            version=version,
            summary=summary,
            created_at=time.time(),
            author=author,
            status=status,
        )
        await asyncio.to_thread(self._persist_release, project_dir, release)
        await self._audit.log(
            actor=author,
            action="release",
            metadata={"project": project_id, "version": version, "status": status},
        )
        logger.info("release recorded", extra={"project_id": project_id, "version": version})
        return release

    async def rollback_release(
        self, project_id: str, version: str, *, reason: str, actor: str
    ) -> ReleaseRecord:
        project_dir = self._root / project_id
        releases = self._load_releases(project_dir)
        for release in releases:
            if release.version == version:
                release.status = "rolled_back"
                await asyncio.to_thread(self._persist_release_history, project_dir, releases)
                await self._audit.log(
                    actor=actor,
                    action="rollback",
                    metadata={"project": project_id, "version": version, "reason": reason},
                )
                return release
        raise ValueError(f"Release {version} not found for project {project_id}")

    async def governance_audit(self, project_id: str) -> Dict[str, Any]:
        state = await self.status(project_id)
        policies = state.metadata.get("settings", {}).get("policies", {})
        coverage_target = float(policies.get("coverage", 0.9))
        license_policy = policies.get("license", "MIT")
        audit_result = {
            "project": project_id,
            "coverage_target": coverage_target,
            "license": license_policy,
            "checks": [],
            "status": "pass",
        }
        coverage = float(state.metadata.get("metrics", {}).get("coverage", coverage_target))
        if coverage < coverage_target:
            audit_result["checks"].append({"name": "coverage", "status": "fail", "value": coverage})
            audit_result["status"] = "fail"
        else:
            audit_result["checks"].append({"name": "coverage", "status": "pass", "value": coverage})
        license_value = state.metadata.get("license", license_policy)
        if license_value != license_policy:
            audit_result["checks"].append({"name": "license", "status": "warn", "value": license_value})
            audit_result["status"] = "warn"
        await self._audit.log(
            actor="governance",
            action="audit",
            metadata={"project": project_id, "status": audit_result["status"]},
        )
        return audit_result

    async def milestone_progress(
        self,
        project_id: str,
        identifier: str,
        *,
        status: str,
        tokens: float,
        minutes: float,
    ) -> ProjectMilestone:
        project_dir = self._root / project_id
        metadata = self._read_metadata(project_dir)
        milestones = metadata.setdefault("milestones", [])
        for entry in milestones:
            if entry.get("id") == identifier:
                entry["status"] = status
                entry["tokens"] = float(entry.get("tokens", 0.0)) + tokens
                entry["budget_minutes"] = float(entry.get("budget_minutes", 0.0)) + minutes
                break
        else:
            entry = {
                "id": identifier,
                "name": identifier,
                "description": "",
                "status": status,
                "tokens": tokens,
                "budget_minutes": minutes,
            }
            milestones.append(entry)
        self._persist_metadata(project_dir, metadata)
        milestone = ProjectMilestone(
            identifier=entry["id"],
            name=entry.get("name", entry["id"]),
            description=entry.get("description", ""),
            due=entry.get("due"),
            status=entry.get("status", "planned"),
            budget_minutes=float(entry.get("budget_minutes", 0.0)),
            tokens_spent=float(entry.get("tokens", 0.0)),
        )
        await self._audit.log(
            actor="milestone",
            action="update",
            metadata={"project": project_id, "milestone": identifier, "status": status},
        )
        return milestone

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_project_config(self, repository: Path) -> Dict[str, Any]:
        config_path = repository / "project.yml"
        if config_path.exists():
            try:
                return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            except Exception:
                logger.debug("failed to read project.yml", exc_info=True)
        return {}

    def _persist_metadata(self, project_dir: Path, metadata: Dict[str, Any]) -> None:
        meta_path = project_dir / "project.yml"
        meta_path.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")

    def _read_metadata(self, project_dir: Path) -> Dict[str, Any]:
        meta_path = project_dir / "project.yml"
        if not meta_path.exists():
            return {}
        return yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}

    def _persist_release(self, project_dir: Path, release: ReleaseRecord) -> None:
        history = self._load_releases(project_dir)
        history.append(release)
        self._persist_release_history(project_dir, history)

    def _persist_release_history(self, project_dir: Path, releases: List[ReleaseRecord]) -> None:
        history_path = project_dir / "releases.json"
        history_path.write_text(
            json.dumps([
                {
                    "version": item.version,
                    "summary": item.summary,
                    "created_at": item.created_at,
                    "author": item.author,
                    "status": item.status,
                }
                for item in releases
            ], indent=2),
            encoding="utf-8",
        )

    def _load_releases(self, project_dir: Path) -> List[ReleaseRecord]:
        history_path = project_dir / "releases.json"
        if not history_path.exists():
            return []
        payload = json.loads(history_path.read_text(encoding="utf-8"))
        releases = [
            ReleaseRecord(
                version=item.get("version", "0.0.0"),
                summary=item.get("summary", ""),
                created_at=float(item.get("created_at", time.time())),
                author=item.get("author", "unknown"),
                status=item.get("status", "draft"),
            )
            for item in payload
        ]
        return releases

    def _load_roadmap(self, project_dir: Path) -> Optional[RoadmapSummary]:
        path = project_dir / "roadmap.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        summary = RoadmapSummary(
            project_id=payload.get("project_id", project_dir.name),
            generated_at=float(payload.get("generated_at", time.time())),
            milestones=[],
            backlog_size=int(payload.get("backlog_size", 0)),
        )
        milestones: List[RoadmapMilestone] = []
        for entry in payload.get("milestones", []):
            tasks: List[RoadmapItem] = []
            for task in entry.get("tasks", []):
                tasks.append(
                    RoadmapItem(
                        title=str(task.get("title", "")),
                        description=str(task.get("description", "")),
                        owner=task.get("owner"),
                        estimate_hours=float(task.get("estimate_hours", 0.0)),
                        tags=tuple(task.get("tags", []) or []),
                    )
                )
            milestones.append(
                RoadmapMilestone(
                    name=str(entry.get("name", "Milestone")),
                    due=entry.get("due"),
                    tasks=tasks,
                )
            )
        summary.milestones = milestones
        return summary

    def _load_team_ledger(self, team_id: Optional[str]) -> Dict[str, float]:
        if not team_id:
            return {"tokens": 0.0, "minutes": 0.0}
        ledger_path = self._team_root / team_id / "ledger.json"
        if not ledger_path.exists():
            return {"tokens": 0.0, "minutes": 0.0}
        try:
            entries = json.loads(ledger_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"tokens": 0.0, "minutes": 0.0}
        tokens = sum(float(entry.get("tokens", 0.0)) for entry in entries)
        minutes = sum(float(entry.get("minutes", 0.0)) for entry in entries)
        return {"tokens": tokens, "minutes": minutes}

    @staticmethod
    def _slugify(name: str) -> str:
        slug = "".join(ch for ch in name.lower() if ch.isalnum() or ch in {"-", "_"})
        return slug or "project"


__all__ = ["ProjectManager", "ProjectState", "ProjectMilestone", "ReleaseRecord"]
