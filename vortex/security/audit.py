"""Audit logging utilities."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AuditEvent:
    actor: str
    action: str
    metadata: Dict[str, Any]
    timestamp: float


class AuditTrail:
    """Persist security sensitive events."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: AuditEvent) -> None:
        self.path.write_text(
            (self.path.read_text(encoding="utf-8") if self.path.exists() else "")
            + json.dumps(event.__dict__)
            + "\n",
            encoding="utf-8",
        )
        logger.info("audit", extra=event.__dict__)

    def log(self, actor: str, action: str, metadata: Dict[str, Any]) -> None:
        event = AuditEvent(actor=actor, action=action, metadata=metadata, timestamp=time.time())
        self.record(event)

    def read_recent(self, limit: int = 100) -> list[Dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").strip().splitlines()[-limit:]
        events = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:  # pragma: no cover - handles manual file edits
                continue
        return events


__all__ = ["AuditTrail", "AuditEvent"]
