"""Shared state management for the Textual user interface."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import RenderableType

SESSION_DIR = Path.home() / ".agent" / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class CollaboratorState:
    """Represents a collaborator connected to the active session."""

    user: str
    host: str
    role: str
    read_only: bool
    last_seen: float

    def label(self) -> str:
        access = "RO" if self.read_only else "RW"
        return f"{self.user}@{self.host} ({self.role}|{access})"


@dataclass
class SessionLogEntry:
    """Represents an event rendered in the log panel."""

    timestamp: float
    level: str
    message: str
    icon: str = ""

    def format(self) -> str:
        icon_prefix = f"{self.icon} " if self.icon else ""
        return f"[{self.level}] {icon_prefix}{self.message}"


@dataclass
class CheckpointSnapshot:
    """Captures a workspace checkpoint diff."""

    identifier: str
    summary: str
    diff: str
    files: List[str]
    created_at: float


def _default_flags() -> Dict[str, bool]:
    """Return default feature-flag configuration."""

    return {"experimental_tui": False, "lyra_assistant": True}


@dataclass
class TUISessionState:
    """Mutable UI session state persisted between runs."""

    mode: str = "chat"
    active_panel: str = "main"
    logs: List[SessionLogEntry] = field(default_factory=list)
    checkpoints: List[CheckpointSnapshot] = field(default_factory=list)
    autopilot_steps: int = 0
    budget_minutes: Optional[int] = None
    palette_history: List[str] = field(default_factory=list)
    status_renderable: Optional[RenderableType] = None
    theme: str = "dark"
    high_contrast: bool = False
    feature_flags: Dict[str, bool] = field(default_factory=_default_flags)
    accessibility_enabled: bool = False
    accessibility_verbosity: str = "normal"
    narration_enabled: bool = False
    screen_reader_mode: bool = False
    last_plain_text: Optional[str] = None
    history: List[str] = field(default_factory=list)
    session_id: Optional[str] = None
    session_role: str = "owner"
    collaborators: Dict[str, CollaboratorState] = field(default_factory=dict)
    session_lock_holder: Optional[str] = None
    session_metrics: Dict[str, float] = field(default_factory=dict)
    analytics_trends: List[Dict[str, Any]] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    transcript_path: Optional[str] = None
    session_acl: Dict[str, str] = field(default_factory=dict)
    team_nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    project_status: Dict[str, Any] = field(default_factory=dict)
    pipeline_history: List[Dict[str, Any]] = field(default_factory=list)
    governance_reports: List[Dict[str, Any]] = field(default_factory=list)

    def add_log(self, level: str, message: str, *, icon: str = "") -> SessionLogEntry:
        entry = SessionLogEntry(timestamp=time.time(), level=level, message=message, icon=icon)
        self.logs.append(entry)
        return entry

    def add_checkpoint(self, summary: str, diff: str, files: List[str]) -> CheckpointSnapshot:
        identifier = f"cp-{len(self.checkpoints) + 1:03d}"
        snapshot = CheckpointSnapshot(
            identifier=identifier,
            summary=summary,
            diff=diff,
            files=files,
            created_at=time.time(),
        )
        self.checkpoints.append(snapshot)
        return snapshot

    def latest_checkpoint(self) -> Optional[CheckpointSnapshot]:
        return self.checkpoints[-1] if self.checkpoints else None

    def record_history(self, command: str) -> None:
        if command:
            self.history.append(command)
            if len(self.history) > 200:
                self.history = self.history[-200:]

    def search_history(self, query: str) -> List[str]:
        if not query:
            return list(reversed(self.history[-10:]))
        query_lower = query.lower()
        return [item for item in reversed(self.history) if query_lower in item.lower()][:10]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "active_panel": self.active_panel,
            "logs": [entry.__dict__ for entry in self.logs][-200:],
            "checkpoints": [snapshot.__dict__ for snapshot in self.checkpoints][-50:],
            "autopilot_steps": self.autopilot_steps,
            "budget_minutes": self.budget_minutes,
            "palette_history": self.palette_history[-50:],
            "theme": self.theme,
            "high_contrast": self.high_contrast,
            "feature_flags": self.feature_flags,
            "accessibility_enabled": self.accessibility_enabled,
            "accessibility_verbosity": self.accessibility_verbosity,
            "narration_enabled": self.narration_enabled,
            "screen_reader_mode": self.screen_reader_mode,
            "last_plain_text": self.last_plain_text,
            "history": self.history[-200:],
            "session_id": self.session_id,
            "session_role": self.session_role,
            "collaborators": {key: value.__dict__ for key, value in self.collaborators.items()},
            "session_lock_holder": self.session_lock_holder,
            "session_metrics": self.session_metrics,
            "analytics_trends": self.analytics_trends[-50:],
            "insights": self.insights[-20:],
            "transcript_path": self.transcript_path,
            "session_acl": self.session_acl,
            "team_nodes": self.team_nodes,
            "project_status": self.project_status,
            "pipeline_history": self.pipeline_history[-20:],
            "governance_reports": self.governance_reports[-10:],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "TUISessionState":
        state = cls()
        state.mode = payload.get("mode", state.mode)
        state.active_panel = payload.get("active_panel", state.active_panel)
        state.autopilot_steps = payload.get("autopilot_steps", 0)
        state.budget_minutes = payload.get("budget_minutes")
        state.palette_history = list(payload.get("palette_history", []))
        state.theme = payload.get("theme", state.theme)
        state.high_contrast = payload.get("high_contrast", state.high_contrast)
        state.feature_flags.update(payload.get("feature_flags", {}))
        state.accessibility_enabled = payload.get("accessibility_enabled", state.accessibility_enabled)
        state.accessibility_verbosity = payload.get(
            "accessibility_verbosity", state.accessibility_verbosity
        )
        state.narration_enabled = payload.get("narration_enabled", state.narration_enabled)
        state.screen_reader_mode = payload.get("screen_reader_mode", state.screen_reader_mode)
        state.last_plain_text = payload.get("last_plain_text")
        state.history = list(payload.get("history", []))
        state.session_id = payload.get("session_id")
        state.session_role = payload.get("session_role", state.session_role)
        for key, value in payload.get("collaborators", {}).items():
            try:
                state.collaborators[key] = CollaboratorState(**value)
            except TypeError:
                continue
        state.session_lock_holder = payload.get("session_lock_holder")
        state.session_metrics = dict(payload.get("session_metrics", {}))
        state.analytics_trends = list(payload.get("analytics_trends", []))
        state.insights = list(payload.get("insights", []))
        state.transcript_path = payload.get("transcript_path")
        state.session_acl = dict(payload.get("session_acl", {}))
        state.team_nodes = dict(payload.get("team_nodes", {}))
        state.project_status = dict(payload.get("project_status", {}))
        state.pipeline_history = list(payload.get("pipeline_history", []))
        state.governance_reports = list(payload.get("governance_reports", []))
        for item in payload.get("logs", []):
            try:
                state.logs.append(SessionLogEntry(**item))
            except TypeError:
                continue
        for item in payload.get("checkpoints", []):
            try:
                state.checkpoints.append(CheckpointSnapshot(**item))
            except TypeError:
                continue
        return state


@dataclass
class TUIOptions:
    """User provided options for launching the TUI."""

    resume: bool = False
    color_scheme: str = "auto"
    no_color: bool = False
    screen_reader: bool = False


class TUIRuntimeBridge:
    """Adapter around the CLI runtime context.

    The bridge keeps filesystem interactions local to this module so that the UI
    code can remain declarative. This is particularly helpful for testing,
    allowing the bridge to be swapped with a fixture providing predictable
    behaviour.
    """

    def __init__(self, runtime: Any, *, session_dir: Path = SESSION_DIR) -> None:
        self.runtime = runtime
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)

    @property
    def settings(self) -> Any:
        return getattr(self.runtime, "settings", None)

    def session_file(self) -> Path:
        return self.session_dir / "latest.json"

    def load_state(self) -> Optional[TUISessionState]:
        path = self.session_file()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            return None
        return TUISessionState.from_dict(data)

    def save_state(self, state: TUISessionState) -> None:
        payload = state.to_dict()
        tmp = self.session_file().with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(self.session_file())

    def session_directory(self, session_id: str) -> Path:
        """Return the filesystem directory associated with ``session_id``."""

        path = Path.home() / ".vortex" / "sessions" / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path


__all__ = [
    "CollaboratorState",
    "TUIOptions",
    "TUIRuntimeBridge",
    "TUISessionState",
    "SessionLogEntry",
    "CheckpointSnapshot",
]


__all__ = [
    "CheckpointSnapshot",
    "SessionLogEntry",
    "TUIOptions",
    "TUIRuntimeBridge",
    "TUISessionState",
]
