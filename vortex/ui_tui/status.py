"""Runtime status aggregation for the TUI."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from rich.table import Table

from vortex.utils.profiling import profile

try:  # pragma: no cover - optional dependency in CI
    import psutil
except Exception:  # pragma: no cover
    psutil = None  # type: ignore[assignment]


@dataclass
class StatusSnapshot:
    branch: str
    pending_changes: int
    last_checkpoint: Optional[str]
    total_cost: float
    mode: str
    tests_status: str
    budget_minutes: Optional[int]
    cpu_percent: float
    memory_percent: float


class StatusAggregator:
    """Collects runtime metadata for the status panel."""

    def __init__(self, runtime: object) -> None:
        self._runtime = runtime
        self.last_tests_status: str = "idle"

    async def _run_git(self, *args: str) -> str:
        security = getattr(self._runtime, "security", None)
        if security is not None:
            await security.ensure_permission("cli", "git:run")
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            return stderr.decode().strip()
        return stdout.decode().strip()

    async def gather(
        self, *, mode: str, budget_minutes: Optional[int], checkpoint: Optional[str]
    ) -> StatusSnapshot:
        with profile("status_gather"):
            branch = await self._safe_git("rev-parse", "--abbrev-ref", "HEAD")
            pending = await self._count_pending()
            total_cost = await self._total_cost()
            cpu_usage, memory_usage = _system_usage()
            snapshot = StatusSnapshot(
                branch=branch or "-",
                pending_changes=pending,
                last_checkpoint=checkpoint,
                total_cost=round(total_cost, 2),
                mode=mode,
                tests_status=self.last_tests_status,
                budget_minutes=budget_minutes,
                cpu_percent=cpu_usage,
                memory_percent=memory_usage,
            )
            return snapshot

    async def _safe_git(self, *args: str) -> str:
        try:
            return await self._run_git(*args)
        except Exception:
            return "-"

    async def _count_pending(self) -> int:
        try:
            status_raw = await self._run_git("status", "--short")
            return len([line for line in status_raw.splitlines() if line.strip()])
        except Exception:
            return 0

    async def _total_cost(self) -> float:
        cost_tracker = getattr(self._runtime, "cost_tracker", None)
        if cost_tracker is None:
            return 0.0
        try:
            return float(await cost_tracker.total_cost())
        except Exception:
            return 0.0

    @staticmethod
    def render(snapshot: StatusSnapshot) -> Table:
        table = Table.grid(padding=(0, 2))
        table.add_column(justify="left")
        table.add_column(justify="left")
        table.add_row("Branch", snapshot.branch)
        table.add_row("Mode", snapshot.mode)
        table.add_row("Pending", str(snapshot.pending_changes))
        table.add_row("Checkpoint", snapshot.last_checkpoint or "—")
        table.add_row("Tests", snapshot.tests_status)
        table.add_row("Budget", f"{snapshot.budget_minutes}m" if snapshot.budget_minutes else "—")
        table.add_row("Cost", f"${snapshot.total_cost:.2f}")
        table.add_row("CPU", f"{snapshot.cpu_percent:4.1f}%")
        table.add_row("Memory", f"{snapshot.memory_percent:4.1f}%")
        return table


def _system_usage() -> tuple[float, float]:
    if psutil is None:  # pragma: no cover - dependency optional
        return 0.0, 0.0
    try:
        cpu = psutil.cpu_percent(interval=0.0)
        memory = psutil.virtual_memory().percent
        return cpu, memory
    except Exception:  # pragma: no cover - guard for unsupported environments
        return 0.0, 0.0


__all__ = ["StatusAggregator", "StatusSnapshot"]
