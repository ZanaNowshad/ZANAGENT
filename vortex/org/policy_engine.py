"""Policy evaluation for organisation governance."""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from vortex.security.audit_system import AuditSystem
from vortex.security.encryption import SecretBox
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PolicyViolation:
    """Violation emitted during policy evaluation."""

    policy_id: str
    message: str
    blocking: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"policy_id": self.policy_id, "message": self.message, "blocking": self.blocking}


class OrgPolicyEngine:
    """Loads policy definitions and evaluates operations against them."""

    def __init__(self, policy_dir: Path | None = None, audit: AuditSystem | None = None) -> None:
        self._policy_dir = policy_dir or Path.home() / ".vortex" / "org" / "policies"
        self._policy_dir.mkdir(parents=True, exist_ok=True)
        self._policies: List[Dict[str, Any]] = []
        self._audit = audit or AuditSystem(Path.home() / ".vortex" / "audit.log")
        self._encrypter = SecretBox()
        self.reload()

    # -- loading -----------------------------------------------------------------
    def reload(self) -> None:
        policies: List[Dict[str, Any]] = []
        for path in sorted(self._policy_dir.glob("*")):
            if path.suffix.lower() in {".yml", ".yaml"}:
                data = yaml.safe_load(path.read_text())
            elif path.suffix.lower() in {".toml"}:
                data = tomllib.loads(path.read_text())
            elif path.suffix.lower() == ".json":
                data = json.loads(path.read_text())
            else:
                continue
            if data:
                policies.append(data)
        self._policies = policies
        logger.info("Policies reloaded", extra={"count": len(self._policies)})

    # -- evaluation --------------------------------------------------------------
    def evaluate(self, context: Dict[str, Any]) -> List[PolicyViolation]:
        violations: List[PolicyViolation] = []
        for policy in self._policies:
            policy_id = policy.get("id", "unknown")
            rule_type = policy.get("type")
            try:
                if rule_type == "coverage":
                    violations.extend(self._evaluate_coverage(policy, context))
                elif rule_type == "model_restriction":
                    violations.extend(self._evaluate_model(policy, context))
                elif rule_type == "role":
                    violations.extend(self._evaluate_roles(policy, context))
                elif rule_type == "license":
                    violations.extend(self._evaluate_license(policy, context))
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Policy evaluation failed", extra={"policy": policy_id, "error": str(exc)})
        if violations:
            for violation in violations:
                self._audit._trail.log(  # type: ignore[attr-defined]
                    actor="policy",
                    action="violation",
                    metadata={
                        "policy_id": violation.policy_id,
                        "message": violation.message,
                    },
                )
        return violations

    def _evaluate_coverage(self, policy: Dict[str, Any], context: Dict[str, Any]) -> List[PolicyViolation]:
        required = float(policy.get("minimum", 0.0))
        coverage = float(context.get("coverage", 0.0))
        if coverage < required:
            return [
                PolicyViolation(
                    policy_id=policy.get("id", "coverage"),
                    message=f"Coverage {coverage:.2%} below threshold {required:.2%}",
                    blocking=policy.get("blocking", True),
                )
            ]
        return []

    def _evaluate_model(self, policy: Dict[str, Any], context: Dict[str, Any]) -> List[PolicyViolation]:
        restricted = set(policy.get("deny", []))
        used_models = set(context.get("models", []))
        hits = restricted.intersection(used_models)
        if hits:
            return [
                PolicyViolation(
                    policy_id=policy.get("id", "model_restriction"),
                    message=f"Models not permitted: {', '.join(sorted(hits))}",
                    blocking=True,
                )
            ]
        return []

    def _evaluate_roles(self, policy: Dict[str, Any], context: Dict[str, Any]) -> List[PolicyViolation]:
        required = set(policy.get("roles", []))
        actor_roles = set(context.get("roles", []))
        if not required.intersection(actor_roles):
            return [
                PolicyViolation(
                    policy_id=policy.get("id", "role"),
                    message="Actor lacks required role",
                    blocking=policy.get("blocking", False),
                )
            ]
        return []

    def _evaluate_license(self, policy: Dict[str, Any], context: Dict[str, Any]) -> List[PolicyViolation]:
        allowed = set(policy.get("allow", []))
        dependencies = set(context.get("licenses", []))
        disallowed = dependencies.difference(allowed)
        if disallowed:
            return [
                PolicyViolation(
                    policy_id=policy.get("id", "license"),
                    message=f"Unapproved licenses: {', '.join(sorted(disallowed))}",
                    blocking=policy.get("blocking", True),
                )
            ]
        return []

    # -- commands -----------------------------------------------------------------
    def list_policies(self) -> List[Dict[str, Any]]:
        return list(self._policies)

    def encrypt_policy(self, policy: Dict[str, Any]) -> bytes:
        return self._encrypter.encrypt(json.dumps(policy).encode("utf-8"))

    def decrypt_policy(self, payload: bytes) -> Dict[str, Any]:
        data = self._encrypter.decrypt(payload)
        return json.loads(data.decode("utf-8"))

