import pytest

from vortex.security.encryption import CredentialStore, DataEncryptor
from vortex.security.manager import UnifiedSecurityManager


@pytest.mark.asyncio
async def test_access_control_and_audit(tmp_path):
    security = UnifiedSecurityManager(
        credential_dir=tmp_path,
        allowed_modules=["json"],
        forbidden_modules=[],
    )
    await security.access_control.define_role("reader", {"read"})
    await security.access_control.assign_role("alice", "reader")
    roles = await security.access_control.roles_for("alice")
    assert roles == {"reader"}
    await security.audit_system.log("alice", "read", {"resource": "doc"})
    events = await security.audit_system.recent_events()
    assert events and events[0].actor == "alice"


def test_data_encryptor_roundtrip(tmp_path):
    store = CredentialStore(tmp_path)
    encryptor = DataEncryptor(store)
    token = encryptor.encrypt_value("secret")
    assert encryptor.decrypt_value(token) == "secret"
