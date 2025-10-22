"""DevOps helper routines."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict

from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class DevOpsHelper:
    """Execute shell commands used in deployment workflows."""

    def __init__(self, *, workdir: Path | None = None) -> None:
        self._workdir = workdir or Path.cwd()

    async def run_command(self, *args: str) -> Dict[str, str]:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(self._workdir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        logger.debug("devops command", extra={"args": args, "returncode": process.returncode})
        return {"stdout": stdout.decode(), "stderr": stderr.decode(), "returncode": str(process.returncode)}
