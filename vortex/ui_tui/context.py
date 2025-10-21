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
class SessionLogEntry:
    """Represents an event rendered in the log panel."""

    timestamp: float
    level: str
    message: str
    icon: str = ""

    def format(self) -> str:
        return f"[{self.level}] {self.message}"


@dataclass
class CheckpointSnapshot:
    """Captures a workspace checkpoint diff."""

    identifier: str
    summary: str
    diff: str
    files: List[str]
    created_at: float


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "active_panel": self.active_panel,
            "logs": [entry.__dict__ for entry in self.logs][-200:],
            "checkpoints": [snapshot.__dict__ for snapshot in self.checkpoints][-50:],
            "autopilot_steps": self.autopilot_steps,
            "budget_minutes": self.budget_minutes,
            "palette_history": self.palette_history[-50:],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "TUISessionState":
        state = cls()
        state.mode = payload.get("mode", state.mode)
        state.active_panel = payload.get("active_panel", state.active_panel)
        state.autopilot_steps = payload.get("autopilot_steps", 0)
        state.budget_minutes = payload.get("budget_minutes")
        state.palette_history = list(payload.get("palette_history", []))
        for item in payload.get("logs", []):
            state.logs.append(SessionLogEntry(**item))
        for item in payload.get("checkpoints", []):
            state.checkpoints.append(CheckpointSnapshot(**item))
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


__all__ = [
    "CheckpointSnapshot",
    "SessionLogEntry",
    "TUIOptions",
    "TUIRuntimeBridge",
    "TUISessionState",
]
