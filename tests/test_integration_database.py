import pytest

from vortex.integration.database import DatabaseManager
from vortex.security.manager import UnifiedSecurityManager


@pytest.mark.asyncio
async def test_database_manager_encryption(tmp_path):
    security = UnifiedSecurityManager(
        credential_dir=tmp_path,
        allowed_modules=["json"],
        forbidden_modules=[],
    )
    manager = DatabaseManager(f"sqlite:///{tmp_path/'db.sqlite'}", security)
    await manager.execute("CREATE TABLE secrets (value TEXT)")
    await manager.store_secret_record("secrets", {"value": "top"})
    result = await manager.fetch("SELECT value FROM secrets", use_cache=True)
    assert result.rowcount == 1
    assert result.rows[0]["value"] != "top"
    await manager.close()
