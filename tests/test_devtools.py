import asyncio
from pathlib import Path

import pytest

from vortex.devtools import (
    Debugger,
    DevOpsHelper,
    DevToolsSuite,
    TestFramework as VortexTestFramework,
)


@pytest.mark.asyncio
async def test_devtools_run_tests(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("vortex.devtools.framework.pytest.main", lambda args, plugins=None: 0)
    framework = VortexTestFramework(root=tmp_path)
    tools = DevToolsSuite(framework)
    report = await tools.run_tests("tests")
    assert "pytest" in report
    health = await tools.health_check()
    assert "tests_found" in health


@pytest.mark.asyncio
async def test_debugger_and_devops(monkeypatch, tmp_path: Path) -> None:
    helper = DevOpsHelper(workdir=tmp_path)
    result = await helper.run_command("echo", "hello")
    assert "hello" in result["stdout"]

    debugger = Debugger()
    outcome = await debugger.run_with_debug(lambda: asyncio.sleep(0, result="ok"))
    assert outcome == "ok"
    timed = await debugger.timeout(asyncio.sleep(0, result="done"), 1)
    assert timed == "done"
