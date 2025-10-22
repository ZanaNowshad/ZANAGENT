"""Role-based access control helpers."""

from __future__ import annotations

import asyncio
from typing import Dict, Set

from vortex.security.permissions import PermissionRegistry
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


class AccessControl:
    """Layered RBAC policies atop :class:`PermissionRegistry`."""

    def __init__(self, registry: PermissionRegistry) -> None:
        self._registry = registry
        self._roles: Dict[str, Set[str]] = {}
        self._assignments: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()

    async def define_role(self, name: str, permissions: Set[str]) -> None:
        async with self._lock:
            self._roles[name] = permissions
            logger.debug("role defined", extra={"role": name})

    async def assign_role(self, principal: str, role: str) -> None:
        async with self._lock:
            if role not in self._roles:
                raise KeyError(role)
            self._assignments.setdefault(principal, set()).add(role)
            self._registry.grant(principal, self._roles[role])
            logger.info("role assigned", extra={"principal": principal, "role": role})

    async def revoke_role(self, principal: str, role: str) -> None:
        async with self._lock:
            assignments = self._assignments.get(principal)
            if assignments and role in assignments:
                assignments.remove(role)
                # Recompute permissions for the principal to maintain consistency
                aggregated: Set[str] = set().union(*(self._roles[r] for r in assignments))
                self._registry.grant(principal, aggregated)

    async def roles_for(self, principal: str) -> Set[str]:
        async with self._lock:
            return set(self._assignments.get(principal, set()))
