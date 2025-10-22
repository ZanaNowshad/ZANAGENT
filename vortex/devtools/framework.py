"""Testing framework wrapper."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Iterable, List

import pytest

from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class TestFramework:
    """Programmatic interface over pytest for automated diagnostics."""

    def __init__(self, *, root: Path) -> None:
        self._root = root

    async def run(self, *args: str) -> List[str]:
        """Execute pytest asynchronously and collect report lines."""

        def _run_pytest() -> List[str]:
            logger.info("running pytest", extra={"args": args})
            result = pytest.main(["-q", *args], plugins=[])
            return [f"exit_code={result}"]

        return await asyncio.to_thread(_run_pytest)

    def discover(self, pattern: str = "test_*.py") -> Iterable[Path]:
        return self._root.glob(pattern)
