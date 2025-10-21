"""Status aggregation for the TUI."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from rich.table import Table


@dataclass
class StatusSnapshot:
    branch: str
    pending_changes: int
    last_checkpoint: Optional[str]
    total_cost: float
    mode: str
    tests_status: str
    budget_minutes: Optional[int]


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

    async def gather(self, *, mode: str, budget_minutes: Optional[int], checkpoint: Optional[str]) -> StatusSnapshot:
        try:
            branch = await self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        except Exception:  # pragma: no cover - git optional in CI
            branch = "-"
        try:
            status_raw = await self._run_git("status", "--short")
            pending = len([line for line in status_raw.splitlines() if line.strip()])
        except Exception:
            pending = 0
        cost_tracker = getattr(self._runtime, "cost_tracker", None)
        total_cost = 0.0
        if cost_tracker is not None:
            try:
                total_cost = float(await cost_tracker.total_cost())
            except Exception:
                total_cost = 0.0
        snapshot = StatusSnapshot(
            branch=branch or "-",
            pending_changes=pending,
            last_checkpoint=checkpoint,
            total_cost=round(total_cost, 2),
            mode=mode,
            tests_status=self.last_tests_status,
            budget_minutes=budget_minutes,
        )
        return snapshot

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
        return table


__all__ = ["StatusAggregator", "StatusSnapshot"]
