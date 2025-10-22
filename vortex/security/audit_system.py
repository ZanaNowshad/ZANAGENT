"""Advanced audit facilities."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from vortex.security.audit import AuditTrail
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AuditEvent:
    timestamp: datetime
    actor: str
    action: str
    metadata: Dict[str, str]


class AuditSystem:
    """Load and query audit trails."""

    def __init__(self, log_path: Path) -> None:
        self._trail = AuditTrail(log_path)
        self._lock = asyncio.Lock()

    async def log(self, actor: str, action: str, metadata: Dict[str, str]) -> None:
        async with self._lock:
            self._trail.log(actor, action, metadata)

    async def recent_events(self, limit: int = 50) -> List[AuditEvent]:
        async with self._lock:
            entries = self._trail.read_recent(limit)
        events = []
        for entry in entries:
            raw_timestamp = entry.get("timestamp")
            if isinstance(raw_timestamp, (int, float)):
                timestamp = datetime.fromtimestamp(raw_timestamp)
            else:
                timestamp = datetime.fromisoformat(str(raw_timestamp))
            events.append(
                AuditEvent(
                    timestamp=timestamp,
                    actor=entry.get("actor", "unknown"),
                    action=entry.get("action", "unknown"),
                    metadata=entry.get("metadata", {}),
                )
            )
        logger.debug("loaded audit events", extra={"count": len(events)})
        return events
