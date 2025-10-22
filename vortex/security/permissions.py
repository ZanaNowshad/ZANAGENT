"""Permission models for Vortex."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set


@dataclass
class PermissionSet:
    """Represents permissions assigned to a principal."""

    name: str
    actions: Set[str] = field(default_factory=set)

    def allows(self, action: str) -> bool:
        return action in self.actions or "*" in self.actions


class PermissionRegistry:
    """Registry storing permission mappings."""

    def __init__(self) -> None:
        self._permissions: Dict[str, PermissionSet] = {}

    def grant(self, principal: str, actions: Set[str]) -> None:
        self._permissions[principal] = PermissionSet(name=principal, actions=actions)

    def revoke(self, principal: str) -> None:
        self._permissions.pop(principal, None)

    def check(self, principal: str, action: str) -> bool:
        perm = self._permissions.get(principal)
        if not perm:
            return False
        return perm.allows(action)


__all__ = ["PermissionRegistry", "PermissionSet"]
