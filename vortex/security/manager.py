"""Security management facade."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Dict, Optional

from vortex.security.access_control import AccessControl
from vortex.security.audit import AuditTrail
from vortex.security.audit_system import AuditSystem
from vortex.security.encryption import CredentialStore
from vortex.security.permissions import PermissionRegistry
from vortex.security.sandbox import Sandbox, SandboxPolicy
from vortex.utils.errors import SecurityError
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class UnifiedSecurityManager:
    """Coordinates all security sub-systems."""

    def __init__(
        self,
        *,
        credential_dir: Path,
        allowed_modules: Optional[list[str]] = None,
        forbidden_modules: Optional[list[str]] = None,
        key_rotation_interval: int = 7 * 24 * 3600,
    ) -> None:
        policy = SandboxPolicy(
            allowed_modules=set(allowed_modules or ["math", "json", "vortex"]),
            forbidden_builtins={"open", "exec", "eval", "compile"},
        )
        self.sandbox = Sandbox(policy=policy)
        self.permissions = PermissionRegistry()
        self.credential_store = CredentialStore(credential_dir)
        audit_path = credential_dir / "audit.log"
        self.audit = AuditTrail(audit_path)
        self.audit_system = AuditSystem(audit_path)
        self.access_control = AccessControl(self.permissions)
        self.key_rotation_interval = key_rotation_interval
        self._last_rotation = time.time()
        self._lock = asyncio.Lock()

    async def ensure_permission(self, principal: str, action: str) -> None:
        if not self.permissions.check(principal, action):
            await self.audit_system.log(principal, "permission_denied", {"action": action})
            raise SecurityError(f"Principal {principal} not permitted to {action}")

    async def rotate_keys(self) -> None:
        async with self._lock:
            now = time.time()
            if now - self._last_rotation < self.key_rotation_interval:
                return
            self.credential_store._load_or_create_key()
            self._last_rotation = now
            await self.audit_system.log("security", "key_rotated", {})

    async def store_secret(self, name: str, secret: str) -> None:
        await self.rotate_keys()
        self.credential_store.save(name, secret)
        await self.audit_system.log("system", "store_secret", {"name": name})

    async def retrieve_secret(self, name: str) -> str:
        secret = self.credential_store.load(name)
        await self.audit_system.log("system", "load_secret", {"name": name})
        return secret


__all__ = ["UnifiedSecurityManager"]
