"""Git integration helpers."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from vortex.security.manager import UnifiedSecurityManager
from vortex.utils.errors import IntegrationError
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GitCommandResult:
    """Result of executing a git command."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


class GitManager:
    """Execute git commands with permission checks and safe environments."""

    def __init__(self, security: UnifiedSecurityManager, *, workdir: Optional[Path] = None) -> None:
        self._security = security
        self._workdir = workdir or Path.cwd()

    async def _run(self, args: Iterable[str]) -> GitCommandResult:
        await self._security.ensure_permission("cli", "git:run")
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(self._workdir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        result = GitCommandResult(returncode=process.returncode, stdout=stdout.decode(), stderr=stderr.decode())
        if not result.success:
            logger.error("git command failed", extra={"args": list(args), "stderr": result.stderr})
            raise IntegrationError(result.stderr)
        return result

    async def clone(self, repo: str, *, destination: Optional[Path] = None, depth: Optional[int] = None) -> GitCommandResult:
        args: List[str] = ["clone", repo]
        if destination:
            args.append(str(destination))
        if depth:
            args.extend(["--depth", str(depth)])
        return await self._run(args)

    async def status(self) -> GitCommandResult:
        return await self._run(["status", "--short"])

    async def pull(self) -> GitCommandResult:
        return await self._run(["pull", "--ff-only"])
