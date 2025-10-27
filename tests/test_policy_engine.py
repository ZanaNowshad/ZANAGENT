from pathlib import Path

from vortex.org.policy_engine import OrgPolicyEngine


def test_policy_engine_evaluates_rules(tmp_path: Path) -> None:
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    policy_file = policy_dir / "coverage.yml"
    policy_file.write_text(
        """
        id: coverage
        type: coverage
        minimum: 0.9
        blocking: true
        """
    )
    engine = OrgPolicyEngine(policy_dir=policy_dir)
    violations = engine.evaluate({"coverage": 0.8})
    assert violations
    assert violations[0].blocking
    engine.reload()
    assert engine.list_policies()

    (policy_dir / "models.toml").write_text(
        """
        id = "restricted"
        type = "model_restriction"
        deny = ["gpt-4"]
        """
    )
    engine.reload()
    hits = engine.evaluate({"coverage": 0.95, "models": ["gpt-4"]})
    assert any(v.policy_id == "restricted" for v in hits)

    (policy_dir / "roles.yml").write_text(
        """
        id: reviewers
        type: role
        roles: ["admin", "auditor"]
        """
    )
    (policy_dir / "licenses.json").write_text(
        """{
            "id": "licenses",
            "type": "license",
            "allow": ["MIT", "Apache-2.0"],
            "blocking": false
        }"""
    )
    engine.reload()
    violations = engine.evaluate({"roles": ["developer"], "licenses": ["GPL"], "coverage": 0.95})
    ids = {violation.policy_id for violation in violations}
    assert "reviewers" in ids
    assert "licenses" in ids


def test_policy_engine_encryption_roundtrip(tmp_path: Path) -> None:
    engine = OrgPolicyEngine(policy_dir=tmp_path / "policies")
    payload = {"id": "model", "type": "model_restriction", "deny": ["gpt-4"]}
    token = engine.encrypt_policy(payload)
    decoded = engine.decrypt_policy(token)
    assert decoded == payload
