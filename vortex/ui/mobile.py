"""Mobile-facing API adapter."""

from __future__ import annotations

import json
from typing import Any, Dict

from vortex.security.manager import UnifiedSecurityManager
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class MobileAPI:
    """Expose a constrained JSON API for mobile clients."""

    def __init__(self, security: UnifiedSecurityManager) -> None:
        self._security = security

    async def dispatch(self, principal: str, action: str, payload: Dict[str, Any]) -> str:
        await self._security.ensure_permission(principal, f"mobile:{action}")
        logger.info("mobile action", extra={"principal": principal, "action": action})
        return json.dumps({"status": "ok", "action": action, "payload": payload})
