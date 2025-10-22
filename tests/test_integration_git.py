import pytest

from vortex.integration.git import GitManager
from vortex.security.manager import UnifiedSecurityManager


@pytest.mark.asyncio
async def test_git_status(tmp_path):
    security = UnifiedSecurityManager(
        credential_dir=tmp_path,
        allowed_modules=["json"],
        forbidden_modules=[],
    )
    security.permissions.grant("cli", {"git:run"})
    manager = GitManager(security)
    result = await manager.status()
    assert result.success
