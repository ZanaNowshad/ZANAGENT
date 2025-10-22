"""Workflow engine for orchestrating tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

from vortex.performance.monitor import PerformanceMonitor
from vortex.utils.errors import WorkflowError
from vortex.utils.logging import get_logger

logger = get_logger(__name__)

WorkflowFunc = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


@dataclass
class WorkflowStep:
    """Represents a single workflow step."""

    name: str
    action: WorkflowFunc
    depends_on: List[str]


class WorkflowEngine:
    """Execute workflows respecting dependencies and collecting metrics."""

    def __init__(self, monitor: PerformanceMonitor) -> None:
        self._monitor = monitor
        self._steps: Dict[str, WorkflowStep] = {}

    def register(
        self, name: str, action: WorkflowFunc, *, depends_on: Optional[Iterable[str]] = None
    ) -> None:
        if name in self._steps:
            raise WorkflowError(f"Workflow step {name} already registered")
        self._steps[name] = WorkflowStep(
            name=name, action=action, depends_on=list(depends_on or [])
        )

    async def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the workflow, returning the combined payload."""

        completed: Dict[str, Dict[str, Any]] = {}

        async def _run_step(step: WorkflowStep) -> None:
            for dependency in step.depends_on:
                if dependency not in completed:
                    raise WorkflowError(f"Dependency {dependency} missing for {step.name}")
            async with self._monitor.track("workflow_step", step=step.name):
                result = await step.action({**payload, **completed.get(step.name, {})})
                completed[step.name] = result

        for step in self._ordered_steps():
            await _run_step(step)

        merged: Dict[str, Any] = dict(payload)
        for result in completed.values():
            merged.update(result)
        return merged

    def _ordered_steps(self) -> List[WorkflowStep]:
        visited: Dict[str, bool] = {}
        order: List[WorkflowStep] = []

        def visit(name: str) -> None:
            if visited.get(name) == True:
                return
            if visited.get(name) == False:
                raise WorkflowError("Circular workflow dependency detected")
            visited[name] = False
            step = self._steps[name]
            for dependency in step.depends_on:
                if dependency not in self._steps:
                    raise WorkflowError(f"Unknown dependency {dependency}")
                visit(dependency)
            visited[name] = True
            order.append(step)

        for name in self._steps:
            visit(name)
        return order
