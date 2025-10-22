"""Command execution orchestrated by the TUI."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from rich.console import RenderableType
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from vortex.performance.analytics import SessionAnalyticsStore

from .analytics_panel import analytics_event_table, analytics_kpi_table
from .command_parser import SlashCommand
from .context import CheckpointSnapshot, TUISessionState
from .session_manager import SessionManager
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
        session_manager: Optional[SessionManager] = None,
        analytics: Optional[SessionAnalyticsStore] = None,
    ) -> None:
        self._runtime = runtime
        self._state = state
        self._status = status
        self._git_root = Path.cwd()
        self._syntax_theme = syntax_theme
        self._session_manager = session_manager
        self._analytics = analytics
        self._user = os.getenv("USER", "operator")
        self._identity = f"{self._user}@{socket.gethostname()}"

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

    def _active_session(self) -> Optional[str]:
        return self._state.session_id

    async def _record_event(
        self,
        kind: str,
        payload: Dict[str, Any],
        *,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._session_manager:
            return
        session_id = self._active_session()
        if not session_id:
            return
        await self._session_manager.broadcast(
            session_id,
            kind,
            payload,
            author=self._identity,
            metrics=metrics,
        )

    async def _ensure_session_registered(self) -> None:
        session_id = self._active_session()
        if session_id and self._session_manager:
            await self._session_manager.record_presence(session_id, self._identity)

    async def _cmd_plan(self, command: SlashCommand) -> CommandResult:
        planner = getattr(self._runtime, "planner", None)
        if planner is None:
            return CommandResult(message="Planner not available")
        order = planner.plan()
        table = Text("Execution order:\n" + "\n".join(f"• {item}" for item in order))
        self._state.mode = "plan"
        await self._record_event(
            "plan", {"summary": "Plan generated", "steps": order}, metrics={"success": True}
        )
        return CommandResult(message="Plan generated", renderable=table, plain_text=table.plain)

    async def _cmd_apply(self, command: SlashCommand) -> CommandResult:
        diff_text = await self._cmd_diff(command, capture_only=True)
        if not diff_text.strip():
            return CommandResult(message="Workspace clean; nothing to apply")
        files = sorted(self._extract_files_from_diff(diff_text))
        summary = files[0] if files else "workspace"
        checkpoint = self._state.add_checkpoint(summary=summary, diff=diff_text, files=files)
        await self._record_event(
            "apply",
            {
                "summary": checkpoint.identifier,
                "files": files,
                "checkpoint": checkpoint.identifier,
            },
            metrics={"success": True},
        )
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
        self._state.checkpoints = [
            c for c in self._state.checkpoints if c.identifier != checkpoint.identifier
        ]
        await self._record_event(
            "undo",
            {"summary": checkpoint.identifier, "files": checkpoint.files},
            metrics={"success": True},
        )
        return CommandResult(message=f"Checkpoint {checkpoint.identifier} reverted")

    async def _cmd_diff(
        self, command: SlashCommand, capture_only: bool = False
    ) -> str | CommandResult:
        path = command.args[0] if command.args else None
        args = ["diff"]
        if path:
            args.append(path)
        diff = await self._run_git(*args)
        if capture_only:
            return diff
        self._state.mode = "diff"
        renderable = Syntax(diff or "No changes", "diff", theme=self._syntax_theme)
        await self._record_event(
            "diff",
            {"summary": "Diff viewed", "path": path or "workspace"},
            metrics={"success": True},
        )
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
        success = "exit_code=0" in output
        await self._record_event(
            "test",
            {"summary": "Tests executed", "arguments": args},
            metrics={"success": success},
        )
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
        await self._record_event(
            "context-add",
            {"summary": str(path), "size": len(content)},
            metrics={"success": True},
        )
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
        await self._record_event(
            "tool",
            {"summary": name, "payload": data},
            metrics={"success": True},
        )
        return CommandResult(
            message=f"Tool {name} executed", renderable=text, plain_text=text.plain
        )

    async def _cmd_mode(self, command: SlashCommand) -> CommandResult:
        if not command.args:
            return CommandResult(message=f"Active mode: {self._state.mode}")
        mode = command.args[0].lower()
        allowed = {"chat", "fix", "gen", "review", "run", "plan", "diff"}
        if mode not in allowed:
            return CommandResult(message=f"Unknown mode {mode}")
        self._state.mode = mode
        await self._record_event("mode", {"summary": mode}, metrics={"success": True})
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
        await self._record_event(
            "budget",
            {"summary": f"{minutes} minutes"},
            metrics={"success": True},
        )
        return CommandResult(message=f"Budget set to {minutes} minutes")

    async def _cmd_auto(self, command: SlashCommand) -> CommandResult:
        if not command.args:
            return CommandResult(message=f"Autopilot steps: {self._state.autopilot_steps}")
        try:
            steps = int(command.args[0])
        except ValueError:
            return CommandResult(message="Autopilot value must be an integer")
        self._state.autopilot_steps = steps
        await self._record_event(
            "autopilot",
            {"summary": f"{steps} steps"},
            metrics={"success": True},
        )
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
        await self._record_event(
            "simulate",
            {"summary": "Simulation complete", "mode": self._state.mode},
            metrics={"success": True},
        )
        return CommandResult(message="Simulation complete", renderable=text, plain_text=text.plain)

    async def _cmd_accessibility(self, command: SlashCommand) -> CommandResult:
        if not command.args:
            state = "on" if self._state.accessibility_enabled else "off"
            return CommandResult(message=f"Accessibility {state}")
        level = command.args[0].lower()
        metadata: Dict[str, Any] = {"accessibility": {}}
        if level in {"on", "off"}:
            enabled = level == "on"
            self._state.accessibility_enabled = enabled
            metadata["accessibility"]["enabled"] = enabled
            await self._record_event(
                "accessibility",
                {"summary": f"enabled={enabled}"},
                metrics={"success": True},
            )
            return CommandResult(
                message=f"Accessibility {'enabled' if enabled else 'disabled'}",
                metadata=metadata,
            )
        if level in {"minimal", "verbose", "normal"}:
            self._state.accessibility_verbosity = level
            metadata["accessibility"]["verbosity"] = level
            await self._record_event(
                "accessibility",
                {"summary": f"verbosity={level}"},
                metrics={"success": True},
            )
            return CommandResult(
                message=f"Accessibility verbosity set to {level}", metadata=metadata
            )
        if level == "narration" and len(command.args) > 1:
            toggle = command.args[1].lower() in {"on", "true", "1"}
            self._state.narration_enabled = toggle
            metadata["accessibility"]["narration"] = toggle
            await self._record_event(
                "accessibility",
                {"summary": f"narration={toggle}"},
                metrics={"success": True},
            )
            return CommandResult(
                message=f"Narration {'enabled' if toggle else 'disabled'}",
                metadata=metadata,
            )
        if level == "contrast" and len(command.args) > 1:
            toggle = command.args[1].lower() in {"on", "true", "1"}
            self._state.high_contrast = toggle
            metadata["accessibility"]["contrast"] = toggle
            await self._record_event(
                "accessibility",
                {"summary": f"contrast={toggle}"},
                metrics={"success": True},
            )
            return CommandResult(
                message=f"High contrast {'enabled' if toggle else 'disabled'}",
                metadata=metadata,
            )
        if level == "verbosity" and len(command.args) > 1:
            verbosity = command.args[1].lower()
            if verbosity not in {"minimal", "normal", "verbose"}:
                return CommandResult(message=f"Unknown verbosity level: {verbosity}")
            self._state.accessibility_verbosity = verbosity
            metadata["accessibility"]["verbosity"] = verbosity
            await self._record_event(
                "accessibility",
                {"summary": f"verbosity={verbosity}"},
                metrics={"success": True},
            )
            return CommandResult(
                message=f"Accessibility verbosity set to {verbosity}", metadata=metadata
            )
        return CommandResult(message=f"Unknown accessibility option: {' '.join(command.args)}")

    async def _cmd_theme(self, command: SlashCommand) -> CommandResult:
        if not command.args:
            return CommandResult(message=f"Active theme: {self._state.theme}")
        requested = command.args[0].lower()
        metadata: Dict[str, Any] = {"theme": {}}
        if requested == "custom":
            if len(command.args) < 2:
                return CommandResult(message="Usage: /theme custom <path>")
            path = Path(command.args[1]).expanduser()
            if not path.exists():
                return CommandResult(message=f"Custom theme not found: {path}")
            metadata["theme"].update({"name": "custom", "custom_path": str(path)})
            self._state.theme = "custom"
            self._state.high_contrast = False
            await self._record_event(
                "theme",
                {"summary": "custom", "path": str(path)},
                metrics={"success": True},
            )
            return CommandResult(message=f"Custom theme loaded from {path}", metadata=metadata)
        high_contrast = requested == "high_contrast"
        theme = "dark" if high_contrast else requested
        if theme not in {"dark", "light"}:
            return CommandResult(message=f"Unknown theme {requested}")
        self._state.theme = theme
        self._state.high_contrast = high_contrast
        metadata["theme"].update({"name": theme, "high_contrast": high_contrast})
        await self._record_event(
            "theme",
            {"summary": theme, "high_contrast": high_contrast},
            metrics={"success": True},
        )
        return CommandResult(message=f"Theme switched to {requested}", metadata=metadata)

    async def _cmd_settings(self, command: SlashCommand) -> CommandResult:
        await self._record_event("settings", {"summary": "open"}, metrics={"success": True})
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
        await self._record_event(
            "lyra",
            {"summary": prompt[:80]},
            metrics={"success": True},
        )
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
        plain = "\n".join(
            f"{row[0]}: {row[1]}"
            for row in [
                ("Platform", platform.platform()),
                ("Python", platform.python_version()),
                ("Terminal", os.environ.get("TERM", "unknown")),
                ("ColsxRows", shutil.get_terminal_size((0, 0)).__repr__()),
                ("Git", shutil.which("git") or "missing"),
            ]
        )
        return CommandResult(message="Diagnostics complete", renderable=columns, plain_text=plain)

    async def _cmd_session(self, command: SlashCommand) -> CommandResult:
        if self._session_manager is None:
            return CommandResult(message="Collaboration engine unavailable")
        if not command.args:
            active = self._active_session() or "none"
            return CommandResult(message=f"Active session: {active}")
        action = command.args[0]
        if action == "new":
            title = " ".join(command.args[1:]).strip() or "Vortex Session"
            metadata = await self._session_manager.create_session(title, self._user)
            self._state.session_id = metadata.session_id
            self._state.session_role = "owner"
            self._state.collaborators = metadata.collaborators
            self._state.transcript_path = str(metadata.path / "transcript.md")
            details = await self._session_manager.session_details(metadata.session_id)
            await self._record_event(
                "session-new", {"summary": metadata.session_id}, metrics={"success": True}
            )
            return CommandResult(
                message=f"Session {metadata.session_id} created",
                metadata={"session": details, "refresh_sessions": True},
            )
        if action == "list":
            sessions = await self._session_manager.list_sessions()
            table = Table(title="Sessions", expand=True)
            table.add_column("ID")
            table.add_column("Title")
            table.add_column("Owner")
            table.add_column("Collaborators", justify="right")
            for item in sessions:
                table.add_row(
                    item.session_id,
                    item.title,
                    item.created_by,
                    str(len(item.collaborators)),
                )
            return CommandResult(message="Sessions listed", renderable=table)
        if action == "join":
            if len(command.args) < 2:
                return CommandResult(message="Usage: /session join <id|token>")
            target = command.args[1]
            role = "collaborator"
            read_only = False
            metadata = None
            try:
                session_id, role, read_only = self._session_manager.parse_share_token(target)
                metadata = await self._session_manager.join_session(
                    session_id, self._user, role=role, read_only=read_only
                )
            except Exception:
                metadata = await self._session_manager.join_session(
                    target, self._user, role=role, read_only=read_only
                )
            self._state.session_id = metadata.session_id
            self._state.session_role = role
            self._state.collaborators = metadata.collaborators
            details = await self._session_manager.session_details(metadata.session_id)
            await self._record_event(
                "session-join",
                {"summary": metadata.session_id, "role": role, "read_only": read_only},
                metrics={"success": True},
            )
            return CommandResult(
                message=f"Joined session {metadata.session_id}",
                metadata={"session": details, "refresh_sessions": True},
            )
        if action == "share":
            if not self._active_session():
                return CommandResult(message="No active session to share")
            role = command.args[1] if len(command.args) > 1 else "collaborator"
            read_only = bool(command.option("--read-only"))
            token = await self._session_manager.share_session(
                self._active_session() or "", role=role, read_only=read_only
            )
            await self._record_event(
                "session-share",
                {"summary": role, "read_only": read_only},
                metrics={"success": True},
            )
            text = Text(f"Share token:\n{token}", style="green")
            return CommandResult(
                message="Share token generated", renderable=text, plain_text=text.plain
            )
        if action == "new" or action == "join":
            return CommandResult(message=f"Unsupported session action: {action}")
        return CommandResult(message=f"Unknown session action: {action}")

    async def _cmd_sync(self, command: SlashCommand) -> CommandResult:
        if self._session_manager is None or not self._active_session():
            return CommandResult(message="No active session to sync")
        await self._session_manager.sync_now(self._active_session() or "")
        await self._record_event("sync", {"summary": "manual"}, metrics={"success": True})
        return CommandResult(message="Session synchronised")

    async def _cmd_analytics(self, command: SlashCommand) -> CommandResult:
        if self._session_manager is None or not self._active_session():
            return CommandResult(message="Analytics unavailable without a session")
        session_id = self._active_session() or ""
        summary = await self._session_manager.analytics_snapshot(session_id)
        insights = await self._session_manager.analytics_insights(session_id)
        kpi_table = analytics_kpi_table(summary.get("kpis", {}))
        events_table = analytics_event_table(summary.get("events", []))
        renderable = Table.grid(expand=True)
        renderable.add_row(kpi_table)
        renderable.add_row(events_table)
        await self._record_event("analytics", {"summary": "snapshot"}, metrics={"success": True})
        return CommandResult(
            message="Analytics snapshot generated",
            renderable=renderable,
            metadata={"analytics": summary, "insights": insights},
        )

    async def _cmd_reports(self, command: SlashCommand) -> CommandResult:
        if self._session_manager is None or not self._active_session():
            return CommandResult(message="No analytics available")
        session_id = self._active_session() or ""
        report = await self._session_manager.analytics_report(session_id)
        text = json.dumps(report, indent=2)
        await self._record_event("report", {"summary": "export"}, metrics={"success": True})
        return CommandResult(
            message="Analytics report exported",
            renderable=Syntax(text, "json", theme=self._syntax_theme),
            plain_text=text,
            metadata={"analytics": report},
        )

    async def _cmd_dashboard(self, command: SlashCommand) -> CommandResult:
        if self._session_manager is None or not self._active_session():
            return CommandResult(message="Dashboard unavailable without a session")
        session_id = self._active_session() or ""
        report = await self._session_manager.analytics_report(session_id)
        insights = await self._session_manager.analytics_insights(session_id)
        await self._record_event("dashboard", {"summary": "open"}, metrics={"success": True})
        return CommandResult(
            message="Dashboard opened",
            metadata={"analytics": report, "insights": insights, "open_dashboard": True},
        )

    async def _cmd_insights(self, command: SlashCommand) -> CommandResult:
        if self._session_manager is None or not self._active_session():
            return CommandResult(message="Insights unavailable")
        session_id = self._active_session() or ""
        insights = await self._session_manager.analytics_insights(session_id)
        await self._record_event("insights", {"summary": "generated"}, metrics={"success": True})
        text = Text("\n".join(f"• {line}" for line in insights) or "No insights yet.")
        return CommandResult(
            message="Insights generated",
            renderable=text,
            plain_text=text.plain,
            metadata={"insights": insights},
        )

    async def _cmd_compare(self, command: SlashCommand) -> CommandResult:
        if self._session_manager is None:
            return CommandResult(message="Analytics store unavailable")
        if len(command.args) < 3:
            return CommandResult(message="Usage: /compare <id1> <id2>")
        first, second = command.args[1], command.args[2]
        comparison = await self._session_manager.analytics_compare(first, second)
        table = Table(title="Comparison", expand=True)
        table.add_column("Metric")
        table.add_column(first)
        table.add_column(second)
        table.add_row(
            "Success Rate",
            f"{comparison['first']['success_rate']*100:.1f}%",
            f"{comparison['second']['success_rate']*100:.1f}%",
        )
        table.add_row(
            "Total Cost",
            f"${self._total_cost(comparison['first']):.2f}",
            f"${self._total_cost(comparison['second']):.2f}",
        )
        await self._record_event(
            "compare", {"summary": f"{first} vs {second}"}, metrics={"success": True}
        )
        return CommandResult(message="Sessions compared", renderable=table)

    @staticmethod
    def _total_cost(summary: Dict[str, Any]) -> float:
        return sum(entry.get("cost", 0.0) for entry in summary.get("events", []))

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
