from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("textual")

from vortex.ui_tui.actions import TUIActionCenter
from vortex.ui_tui.command_parser import parse_slash_command
from vortex.ui_tui.context import TUISessionState
from vortex.ui_tui.status import StatusAggregator


class DummySecurity:
    async def ensure_permission(self, principal: str, action: str) -> None:
        return None


class DummyCostTracker:
    async def total_cost(self) -> float:
        return 1.25


class DummyPlanner:
    def plan(self) -> list[str]:
        return ["bootstrap", "execute"]


class DummyTestFramework:
    async def run(self, *args: str) -> list[str]:
        return ["exit_code=0", "args=" + " ".join(args)]


class DummyMemory:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    async def add(self, kind: str, content: str, metadata: dict | None = None) -> None:
        self.records.append((kind, content))


class DummyPlugins:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def discover(self) -> dict[str, Path]:
        return {"echo": Path("plugins/echo.py")}

    async def execute(self, name: str, **payload: str) -> str:
        self.calls.append((name, payload))
        return f"{name}:{payload}"


class DummyWorkflowEngine:
    async def execute(self, payload: dict) -> dict:
        return {"status": "ok", **payload}


class DummyRuntime:
    def __init__(self) -> None:
        self.security = DummySecurity()
        self.cost_tracker = DummyCostTracker()
        self.planner = DummyPlanner()
        self.test_framework = DummyTestFramework()
        self.memory = DummyMemory()
        self.plugins = DummyPlugins()
        self.workflow_engine = DummyWorkflowEngine()
        self.settings = SimpleNamespace(ui=SimpleNamespace(theme="dark"))


@pytest.fixture()
def runtime() -> DummyRuntime:
    return DummyRuntime()


@pytest.mark.asyncio
async def test_plan_apply_undo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runtime: DummyRuntime
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=repo, check=True)
    (repo / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    monkeypatch.chdir(repo)
    state = TUISessionState()
    status = StatusAggregator(runtime)
    actions = TUIActionCenter(runtime, state, status)

    plan_cmd = parse_slash_command("/plan")
    assert plan_cmd is not None
    plan_result = await actions.handle(plan_cmd)
    assert "Plan" in plan_result.message

    # Modify the file to generate a diff
    (repo / "README.md").write_text("hello world\n")
    diff_cmd = parse_slash_command("/diff")
    diff_result = await actions.handle(diff_cmd)  # type: ignore[arg-type]
    assert "diff" in diff_result.message.lower()

    apply_cmd = parse_slash_command("/apply")
    assert apply_cmd is not None
    apply_result = await actions.handle(apply_cmd)
    assert state.checkpoints
    assert apply_result.checkpoint is not None

    undo_cmd = parse_slash_command("/undo")
    assert undo_cmd is not None
    undo_result = await actions.handle(undo_cmd)
    assert "reverted" in undo_result.message
    assert not state.checkpoints
    assert (repo / "README.md").read_text() == "hello\n"

    status_snapshot = await status.gather(mode=state.mode, budget_minutes=None, checkpoint=None)
    assert status_snapshot.branch


@pytest.mark.asyncio
async def test_tool_and_memory_commands(
    runtime: DummyRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    monkeypatch.chdir(repo)

    state = TUISessionState()
    status = StatusAggregator(runtime)
    actions = TUIActionCenter(runtime, state, status)

    path = repo / "note.txt"
    path.write_text("context")
    ctx_cmd = parse_slash_command(f"/ctx add {path}")
    assert ctx_cmd is not None
    ctx_result = await actions.handle(ctx_cmd)
    assert "Context added" in ctx_result.message
    assert runtime.memory.records

    tool_cmd = parse_slash_command('/tool echo "{\\"value\\": 1}"')
    assert tool_cmd is not None
    tool_result = await actions.handle(tool_cmd)
    assert "Tool echo" in tool_result.message
    assert runtime.plugins.calls


@pytest.mark.asyncio
async def test_accessibility_and_theme_commands(
    tmp_path: Path, runtime: DummyRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    monkeypatch.chdir(repo)

    state = TUISessionState()
    status = StatusAggregator(runtime)
    actions = TUIActionCenter(runtime, state, status)

    accessibility_cmd = parse_slash_command("/accessibility narration on")
    assert accessibility_cmd is not None
    accessibility_result = await actions.handle(accessibility_cmd)
    assert accessibility_result.metadata["accessibility"]["narration"] is True

    contrast_cmd = parse_slash_command("/accessibility contrast on")
    contrast_result = await actions.handle(contrast_cmd)
    assert contrast_result.metadata["accessibility"]["contrast"] is True

    theme_file = tmp_path / "theme.yaml"
    theme_file.write_text("palette:\n  screen:\n    background: '#000000'\n")
    theme_cmd = parse_slash_command(f"/theme custom {theme_file}")
    assert theme_cmd is not None
    theme_result = await actions.handle(theme_cmd)
    assert theme_result.metadata["theme"]["custom_path"] == str(theme_file)

    quit_cmd = parse_slash_command("/quit")
    assert quit_cmd is not None
    quit_result = await actions.handle(quit_cmd)
    assert quit_result.metadata["quit"] is True

    doctor_cmd = parse_slash_command("/doctor")
    assert doctor_cmd is not None
    doctor_result = await actions.handle(doctor_cmd)
    assert "Platform" in (doctor_result.plain_text or "")

    help_cmd = parse_slash_command("/help")
    assert help_cmd is not None
    help_result = await actions.handle(help_cmd)
    assert "Help" in help_result.message
