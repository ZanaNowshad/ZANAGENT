"""Task planning and execution engine."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from graphlib import TopologicalSorter
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Set

from vortex.utils.errors import VortexError
from vortex.utils.logging import get_logger
from vortex.utils.profiling import profile

logger = get_logger(__name__)


@dataclass
class TaskSpec:
    """High level representation of a task."""

    name: str
    description: str
    action: Callable[[], Awaitable[Any]]
    depends_on: Set[str] = field(default_factory=set)
    retries: int = 0


@dataclass
class TaskResult:
    name: str
    success: bool
    result: Any = None
    error: Optional[Exception] = None


class UnifiedAdvancedPlanner:
    """Plan and execute tasks with dependency awareness."""

    def __init__(self, *, max_parallel_tasks: int = 4, recovery_retries: int = 2) -> None:
        self.max_parallel_tasks = max_parallel_tasks
        self.recovery_retries = recovery_retries
        self._tasks: Dict[str, TaskSpec] = {}

    def add_task(self, task: TaskSpec) -> None:
        if task.name in self._tasks:
            raise VortexError(f"Task {task.name} already registered")
        self._tasks[task.name] = task

    def plan(self) -> List[str]:
        sorter = TopologicalSorter({name: task.depends_on for name, task in self._tasks.items()})
        order = list(sorter.static_order())
        logger.debug("task plan", extra={"order": order})
        return order

    async def execute(self) -> List[TaskResult]:
        order = self.plan()
        pending_dependencies: Dict[str, Set[str]] = {name: set(self._tasks[name].depends_on) for name in order}
        completed: Dict[str, TaskResult] = {}
        in_progress: Set[str] = set()
        semaphore = asyncio.Semaphore(self.max_parallel_tasks)
        results: List[TaskResult] = []

        async def run_task(name: str) -> None:
            task = self._tasks[name]
            async with semaphore:
                with profile(f"task:{name}"):
                    attempt = 0
                    while attempt <= task.retries + self.recovery_retries:
                        try:
                            result = await task.action()
                            res = TaskResult(name=name, success=True, result=result)
                            completed[name] = res
                            results.append(res)
                            break
                        except Exception as exc:
                            attempt += 1
                            if attempt > task.retries + self.recovery_retries:
                                res = TaskResult(name=name, success=False, error=exc)
                                completed[name] = res
                                results.append(res)
                                logger.exception("task failed", extra={"task": name, "error": str(exc)})
                                break
                            await asyncio.sleep(0.1 * attempt)
                            logger.warning("retrying task", extra={"task": name, "attempt": attempt})

        async def scheduler() -> None:
            queue: asyncio.Queue[str] = asyncio.Queue()
            for name in order:
                if not pending_dependencies[name]:
                    await queue.put(name)
            while len(results) < len(order):
                name = await queue.get()
                if name in in_progress:
                    continue
                in_progress.add(name)
                asyncio.create_task(run_task(name))
                for downstream, deps in pending_dependencies.items():
                    deps.discard(name)
                    if not deps and downstream not in in_progress:
                        await queue.put(downstream)

        await scheduler()
        # Wait for all tasks to finish
        while len(results) < len(order):
            await asyncio.sleep(0.05)
        return results


__all__ = ["UnifiedAdvancedPlanner", "TaskSpec", "TaskResult"]
