"""Pipeline orchestration and CI/CD integrations."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from rich.table import Table

from vortex.performance.monitor import PerformanceMonitor
from vortex.security.audit_system import AuditSystem
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PipelineStageResult:
    """Structured response from an individual pipeline stage."""

    name: str
    status: str
    logs: List[str]
    duration: float
    environment: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "logs": self.logs,
            "duration": self.duration,
            "environment": self.environment,
        }


@dataclass
class PipelineRun:
    """Aggregate view of a pipeline execution."""

    project_id: str
    pipeline: str
    stages: List[PipelineStageResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    summary: str = "pending"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "pipeline": self.pipeline,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": self.summary,
            "stages": [stage.to_dict() for stage in self.stages],
        }

    def rich_table(self) -> Table:
        table = Table(title=f"Pipeline {self.pipeline}", show_header=True, header_style="bold magenta")
        table.add_column("Stage")
        table.add_column("Status")
        table.add_column("Duration (s)")
        table.add_column("Environment")
        for stage in self.stages:
            table.add_row(stage.name, stage.status, f"{stage.duration:.2f}", stage.environment)
        table.caption = self.summary
        return table


class _BaseConnector:
    async def execute(self, stage: str, config: Dict[str, Any]) -> List[str]:  # pragma: no cover - overridden
        raise NotImplementedError


class _GitHubActionsConnector(_BaseConnector):
    async def execute(self, stage: str, config: Dict[str, Any]) -> List[str]:
        workflow = config.get("workflow") or f"{stage}.yml"
        return [f"GitHub Actions workflow {workflow} triggered", "Status: success"]


class _GitLabCIConnector(_BaseConnector):
    async def execute(self, stage: str, config: Dict[str, Any]) -> List[str]:
        job = config.get("job", stage)
        return [f"GitLab CI job {job} scheduled", "Status: success"]


class _CircleCIConnector(_BaseConnector):
    async def execute(self, stage: str, config: Dict[str, Any]) -> List[str]:
        workflow = config.get("workflow", stage)
        return [f"CircleCI workflow {workflow} enqueued", "Status: success"]


class _DockerConnector(_BaseConnector):
    async def execute(self, stage: str, config: Dict[str, Any]) -> List[str]:
        image = config.get("image", "local/build")
        return [f"Docker image {image} built", f"Command: {config.get('command', 'N/A')}"]


class _KubernetesConnector(_BaseConnector):
    async def execute(self, stage: str, config: Dict[str, Any]) -> List[str]:
        deployment = config.get("deployment", stage)
        namespace = config.get("namespace", "default")
        return [
            f"Kubernetes deployment {deployment} applied",
            f"Namespace: {namespace}",
            "Status: healthy",
        ]


_CONNECTORS = {
    "github_actions": _GitHubActionsConnector,
    "gitlab": _GitLabCIConnector,
    "circleci": _CircleCIConnector,
    "docker": _DockerConnector,
    "kubernetes": _KubernetesConnector,
}


class PipelineManager:
    """Coordinate build/test/deploy pipelines across providers."""

    def __init__(
        self,
        *,
        root: Optional[Path] = None,
        monitor: Optional[PerformanceMonitor] = None,
        audit: Optional[AuditSystem] = None,
    ) -> None:
        self._root = root or Path.home() / ".vortex" / "pipelines"
        self._root.mkdir(parents=True, exist_ok=True)
        self._monitor = monitor or PerformanceMonitor()
        audit_path = self._root / "pipeline.audit.jsonl"
        self._audit = audit or AuditSystem(audit_path)
        self._pipelines: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Registration & configuration
    # ------------------------------------------------------------------
    async def register_project(self, project_id: str, config: Dict[str, Any]) -> None:
        async with self._lock:
            self._pipelines[project_id] = config
            logger.debug("pipelines registered", extra={"project": project_id, "count": len(config)})

    async def list_pipelines(self, project_id: str) -> List[str]:
        async with self._lock:
            config = self._pipelines.get(project_id, {})
        return sorted(config.keys())

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------
    async def run(
        self,
        project_id: str,
        pipeline_name: str,
        stage_name: Optional[str] = None,
        *,
        environment: Optional[str] = None,
    ) -> PipelineRun:
        config = await self._pipeline_config(project_id, pipeline_name)
        stages = config.get("stages", [])
        if not stages:
            raise ValueError(f"Pipeline {pipeline_name} has no stages")
        selected = stages
        if stage_name:
            selected = [stage for stage in stages if stage.get("name") == stage_name]
            if not selected:
                raise ValueError(f"Stage {stage_name} not found in pipeline {pipeline_name}")
        run = PipelineRun(project_id=project_id, pipeline=pipeline_name)
        for stage in selected:
            name = stage.get("name", stage_name or pipeline_name)
            connector = self._connector(stage)
            env = environment or stage.get("environment") or config.get("environment", "default")
            async with self._monitor.track("pipeline_stage", pipeline=pipeline_name, stage=name):
                start = time.perf_counter()
                logs = await connector.execute(name, stage.get("config", {}))
                duration = time.perf_counter() - start
            status = stage.get("status", "success")
            result = PipelineStageResult(name=name, status=status, logs=logs, duration=duration, environment=env)
            run.stages.append(result)
            await self._audit.log(
                actor="pipeline",
                action="stage",
                metadata={
                    "project": project_id,
                    "pipeline": pipeline_name,
                    "stage": name,
                    "status": status,
                    "duration": f"{duration:.3f}",
                },
            )
        run.finished_at = time.time()
        failures = [stage for stage in run.stages if stage.status != "success"]
        run.summary = "success" if not failures else f"failed: {[stage.name for stage in failures]}"
        await asyncio.to_thread(self._persist_history, project_id, run)
        logger.info(
            "pipeline run recorded",
            extra={"project_id": project_id, "pipeline": pipeline_name, "summary": run.summary},
        )
        return run

    async def run_pipeline(self, project_id: str, pipeline_name: str) -> PipelineRun:
        return await self.run(project_id, pipeline_name)

    async def status(self, project_id: str, pipeline_name: str) -> Optional[PipelineRun]:
        history = await asyncio.to_thread(self._read_history, project_id)
        for entry in reversed(history):
            if entry["pipeline"] == pipeline_name:
                return self._from_dict(entry)
        return None

    async def logs(self, project_id: str, pipeline_name: str) -> List[str]:
        history = await asyncio.to_thread(self._read_history, project_id)
        logs: List[str] = []
        for entry in history:
            if entry["pipeline"] != pipeline_name:
                continue
            for stage in entry.get("stages", []):
                logs.extend(stage.get("logs", []))
        return logs

    async def dashboard(self, project_id: str) -> Table:
        history = await asyncio.to_thread(self._read_history, project_id)
        table = Table(title=f"Pipeline dashboard for {project_id}")
        table.add_column("Pipeline")
        table.add_column("Summary")
        table.add_column("Last Duration (s)")
        table.add_column("Runs")
        aggregates: Dict[str, Dict[str, Any]] = {}
        for entry in history:
            summary = aggregates.setdefault(
                entry["pipeline"], {"runs": 0, "summary": entry.get("summary", ""), "duration": 0.0}
            )
            summary["runs"] += 1
            durations = [stage.get("duration", 0.0) for stage in entry.get("stages", [])]
            summary["duration"] = max(summary["duration"], max(durations) if durations else 0.0)
            summary["summary"] = entry.get("summary", summary["summary"])
        for pipeline, data in sorted(aggregates.items()):
            table.add_row(pipeline, data["summary"], f"{data['duration']:.2f}", str(data["runs"]))
        return table

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _pipeline_config(self, project_id: str, pipeline: str) -> Dict[str, Any]:
        async with self._lock:
            config = self._pipelines.get(project_id)
        if not config or pipeline not in config:
            raise KeyError(f"Pipeline {pipeline} not registered for project {project_id}")
        return config[pipeline]

    def _connector(self, stage: Dict[str, Any]) -> _BaseConnector:
        name = stage.get("connector", "docker")
        connector_cls = _CONNECTORS.get(name)
        if not connector_cls:
            raise ValueError(f"Unsupported connector {name}")
        return connector_cls()

    def _persist_history(self, project_id: str, run: PipelineRun) -> None:
        history_path = self._root / f"{project_id}.history.jsonl"
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(run.to_dict()) + "\n")

    def _read_history(self, project_id: str) -> List[Dict[str, Any]]:
        history_path = self._root / f"{project_id}.history.jsonl"
        if not history_path.exists():
            return []
        entries = []
        for line in history_path.read_text(encoding="utf-8").splitlines():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    def _from_dict(self, payload: Dict[str, Any]) -> PipelineRun:
        run = PipelineRun(project_id=payload["project_id"], pipeline=payload["pipeline"], started_at=payload.get("started_at", 0.0))
        run.finished_at = payload.get("finished_at")
        run.summary = payload.get("summary", "unknown")
        for stage in payload.get("stages", []):
            run.stages.append(
                PipelineStageResult(
                    name=stage.get("name", "stage"),
                    status=stage.get("status", "success"),
                    logs=list(stage.get("logs", [])),
                    duration=float(stage.get("duration", 0.0)),
                    environment=stage.get("environment", "default"),
                )
            )
        return run


__all__ = ["PipelineManager", "PipelineRun", "PipelineStageResult"]
