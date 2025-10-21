"""Command execution orchestrated by the TUI."""
from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from rich.console import RenderableType
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from .command_parser import SlashCommand
from .context import CheckpointSnapshot, TUISessionState
from .status import StatusAggregator


@dataclass
class CommandResult:
    """Represents the outcome of a slash command."""

    message: str
    renderable: Optional[RenderableType] = None
    checkpoint: Optional[CheckpointSnapshot] = None
    plain_text: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class TUIActionCenter:
    """Translate slash commands into runtime interactions."""

    def __init__(
        self,
        runtime: object,
        state: TUISessionState,
        status: StatusAggregator,
        *,
        syntax_theme: str = "ansi_dark",
    ) -> None:
        self._runtime = runtime
        self._state = state
        self._status = status
        self._git_root = Path.cwd()
        self._syntax_theme = syntax_theme

    async def _ensure_git_permission(self) -> None:
        security = getattr(self._runtime, "security", None)
        if security is not None:
            await security.ensure_permission("cli", "git:run")

    async def _run_git(self, *args: str) -> str:
        await self._ensure_git_permission()
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(self._git_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.decode().strip())
        return stdout.decode()

    async def handle(self, command: SlashCommand) -> CommandResult:
        name = command.name
        handler = getattr(self, f"_cmd_{name}", None)
        if handler is None:
            return CommandResult(message=f"Unknown command: {name}")
        result = await handler(command)
        self._state.palette_history.append(command.raw.strip())
        self._state.record_history(command.raw.strip())
        return result

    async def _cmd_plan(self, command: SlashCommand) -> CommandResult:
        planner = getattr(self._runtime, "planner", None)
        if planner is None:
            return CommandResult(message="Planner not available")
        order = planner.plan()
        table = Text("Execution order:\n" + "\n".join(f"• {item}" for item in order))
        self._state.mode = "plan"
        return CommandResult(message="Plan generated", renderable=table, plain_text=table.plain)

    async def _cmd_apply(self, command: SlashCommand) -> CommandResult:
        diff_text = await self._cmd_diff(command, capture_only=True)
        if not diff_text.strip():
            return CommandResult(message="Workspace clean; nothing to apply")
        files = sorted(self._extract_files_from_diff(diff_text))
        summary = files[0] if files else "workspace"
        checkpoint = self._state.add_checkpoint(summary=summary, diff=diff_text, files=files)
        return CommandResult(
            message=f"Checkpoint {checkpoint.identifier} captured",
            renderable=Syntax(diff_text, "diff", theme=self._syntax_theme),
            checkpoint=checkpoint,
            plain_text=diff_text,
        )

    async def _cmd_undo(self, command: SlashCommand) -> CommandResult:
        target_id = command.args[0] if command.args else None
        checkpoint = self._locate_checkpoint(target_id)
        if checkpoint is None:
            return CommandResult(message="No checkpoint available to undo")
        try:
            await self._ensure_git_permission()
            process = await asyncio.create_subprocess_exec(
                "git",
                "checkout",
                "--",
                *checkpoint.files,
                cwd=str(self._git_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
        except Exception:
            pass
        self._state.checkpoints = [c for c in self._state.checkpoints if c.identifier != checkpoint.identifier]
        return CommandResult(message=f"Checkpoint {checkpoint.identifier} reverted")

    async def _cmd_diff(self, command: SlashCommand, capture_only: bool = False) -> str | CommandResult:
        path = command.args[0] if command.args else None
        args = ["diff"]
        if path:
            args.append(path)
        diff = await self._run_git(*args)
        if capture_only:
            return diff
        self._state.mode = "diff"
        renderable = Syntax(diff or "No changes", "diff", theme=self._syntax_theme)
        return CommandResult(message="Workspace diff", renderable=renderable, plain_text=diff)

    async def _cmd_test(self, command: SlashCommand) -> CommandResult:
        test_framework = getattr(self._runtime, "test_framework", None)
        if test_framework is None:
            return CommandResult(message="Testing framework unavailable")
        args = []
        keyword = command.option("-k") or command.option("--keyword")
        if keyword:
            args.extend(["-k", keyword])
        result_lines = await test_framework.run(*args)
        output = "\n".join(result_lines)
        self._status.last_tests_status = "pass" if "exit_code=0" in output else "fail"
        renderable = Syntax(output, "text", theme=self._syntax_theme)
        return CommandResult(message="Tests executed", renderable=renderable, plain_text=output)

    async def _cmd_ctx(self, command: SlashCommand) -> CommandResult:
        if not command.args:
            return CommandResult(message="Usage: /ctx add <path>")
        action = command.args[0]
        if action != "add":
            return CommandResult(message=f"Unsupported ctx action: {action}")
        if len(command.args) < 2:
            return CommandResult(message="Missing path for ctx add")
        path = Path(command.args[1]).expanduser()
        if not path.exists():
            return CommandResult(message=f"Path not found: {path}")
        memory = getattr(self._runtime, "memory", None)
        if memory is None:
            return CommandResult(message="Memory system unavailable")
        content = path.read_text()
        await memory.add("context", content, metadata={"path": str(path)})
        return CommandResult(message=f"Context added from {path}")

    async def _cmd_tool(self, command: SlashCommand) -> CommandResult:
        if not command.args:
            return CommandResult(message="Usage: /tool <name> {json}")
        name = command.args[0]
        payload = command.args[1] if len(command.args) > 1 else "{}"
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            return CommandResult(message=f"Invalid JSON payload: {exc}")
        plugins = getattr(self._runtime, "plugins", None)
        if plugins is None:
            return CommandResult(message="Plugin system unavailable")
        result = await plugins.execute(name, **data)
        text = Text(f"Tool {name} result:\n{result}")
        return CommandResult(message=f"Tool {name} executed", renderable=text, plain_text=text.plain)

    async def _cmd_mode(self, command: SlashCommand) -> CommandResult:
        if not command.args:
            return CommandResult(message=f"Active mode: {self._state.mode}")
        mode = command.args[0].lower()
        allowed = {"chat", "fix", "gen", "review", "run", "plan", "diff"}
        if mode not in allowed:
            return CommandResult(message=f"Unknown mode {mode}")
        self._state.mode = mode
        return CommandResult(message=f"Switched to {mode} mode")

    async def _cmd_budget(self, command: SlashCommand) -> CommandResult:
        if not command.args:
            return CommandResult(message="Usage: /budget <minutes>")
        value = command.args[0]
        try:
            minutes = int(value.rstrip("m"))
        except ValueError:
            return CommandResult(message=f"Invalid budget value: {value}")
        self._state.budget_minutes = minutes
        return CommandResult(message=f"Budget set to {minutes} minutes")

    async def _cmd_auto(self, command: SlashCommand) -> CommandResult:
        if not command.args:
            return CommandResult(message=f"Autopilot steps: {self._state.autopilot_steps}")
        try:
            steps = int(command.args[0])
        except ValueError:
            return CommandResult(message="Autopilot value must be an integer")
        self._state.autopilot_steps = steps
        return CommandResult(message=f"Autopilot configured for {steps} steps")

    async def _cmd_help(self, command: SlashCommand) -> CommandResult:
        return CommandResult(message="Help panel toggled")

    async def _cmd_simulate(self, command: SlashCommand) -> CommandResult:
        workflow = getattr(self._runtime, "workflow_engine", None)
        if workflow is None:
            return CommandResult(message="Workflow engine unavailable")
        payload = {"mode": self._state.mode}
        result = await workflow.execute(payload)
        text = Text.from_markup("\n".join(f"{k}: {v}" for k, v in result.items()))
        return CommandResult(message="Simulation complete", renderable=text, plain_text=text.plain)

    async def _cmd_accessibility(self, command: SlashCommand) -> CommandResult:
        if not command.args:
            state = "on" if self._state.accessibility_enabled else "off"
            return CommandResult(message=f"Accessibility {state}")
        level = command.args[0].lower()
        metadata: Dict[str, Any]
        if level in {"on", "off"}:
            enabled = level == "on"
            self._state.accessibility_enabled = enabled
            metadata = {"accessibility": {"enabled": enabled}}
            return CommandResult(message=f"Accessibility {'enabled' if enabled else 'disabled'}", metadata=metadata)
        if level in {"minimal", "verbose", "normal"}:
            self._state.accessibility_verbosity = level
            metadata = {"accessibility": {"verbosity": level}}
            return CommandResult(message=f"Accessibility verbosity set to {level}", metadata=metadata)
        return CommandResult(message=f"Unknown accessibility option: {level}")

    async def _cmd_theme(self, command: SlashCommand) -> CommandResult:
        if not command.args:
            return CommandResult(message=f"Active theme: {self._state.theme}")
        requested = command.args[0].lower()
        high_contrast = requested == "high_contrast"
        theme = "dark" if high_contrast else requested
        if theme not in {"dark", "light"}:
            return CommandResult(message=f"Unknown theme {requested}")
        self._state.theme = theme
        self._state.high_contrast = high_contrast
        metadata = {"theme": {"name": theme, "high_contrast": high_contrast}}
        return CommandResult(message=f"Theme switched to {requested}", metadata=metadata)

    async def _cmd_settings(self, command: SlashCommand) -> CommandResult:
        return CommandResult(message="Opening settings", metadata={"open_settings": True})

    async def _cmd_quit(self, command: SlashCommand) -> CommandResult:
        return CommandResult(message="Quit requested", metadata={"quit": True})

    async def _cmd_reload(self, command: SlashCommand) -> CommandResult:
        if command.args and command.args[0] == "theme":
            return CommandResult(message="Reloading theme", metadata={"reload_theme": True})
        return CommandResult(message="Reload requires a target e.g. /reload theme")

    async def _cmd_lyra(self, command: SlashCommand) -> CommandResult:
        prompt = " ".join(command.args)
        metadata = {"lyra_prompt": prompt}
        return CommandResult(message="Lyra prompt submitted", metadata=metadata)

    async def _cmd_doctor(self, command: SlashCommand) -> CommandResult:
        columns = Table.grid(expand=True)
        columns.add_column(justify="left")
        columns.add_column(justify="left")
        columns.add_row("Platform", platform.platform())
        columns.add_row("Python", platform.python_version())
        columns.add_row("Terminal", os.environ.get("TERM", "unknown"))
        columns.add_row("ColsxRows", shutil.get_terminal_size((0, 0)).__repr__())
        columns.add_row("Git", shutil.which("git") or "missing")
        return CommandResult(message="Diagnostics complete", renderable=columns)

    def _locate_checkpoint(self, identifier: Optional[str]) -> Optional[CheckpointSnapshot]:
        if not self._state.checkpoints:
            return None
        if identifier is None:
            return self._state.checkpoints[-1]
        for checkpoint in reversed(self._state.checkpoints):
            if checkpoint.identifier == identifier:
                return checkpoint
        return None

    @staticmethod
    def _extract_files_from_diff(diff: str) -> Iterable[str]:
        files = set()
        for line in diff.splitlines():
            if line.startswith("+++") and line != "+++ b/dev/null":
                files.add(line.split(" b/")[-1])
            elif line.startswith("---") and line != "--- a/dev/null":
                files.add(line.split(" a/")[-1])
        return files


__all__ = ["CommandResult", "TUIActionCenter"]
