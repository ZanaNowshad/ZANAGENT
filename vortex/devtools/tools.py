"""Developer tools coordination."""
from __future__ import annotations

from typing import Dict, Iterable

from vortex.devtools.framework import TestFramework
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class DevToolsSuite:
    """Execute developer workflows like tests and linting."""

    def __init__(self, test_framework: TestFramework) -> None:
        self._test_framework = test_framework

    async def run_tests(self, *paths: str) -> Dict[str, Iterable[str]]:
        results = await self._test_framework.run(*paths)
        return {"pytest": results}

    async def health_check(self) -> Dict[str, str]:
        logger.info("running health check")
        tests = list(self._test_framework.discover())
        return {"tests_found": str(len(tests))}
