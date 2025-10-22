import asyncio
from pathlib import Path

import pytest

from vortex.core.config import UnifiedConfigManager


def test_load_default_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "providers:\n  - name: echo\n    type: echo\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VORTEX_CONFIG", str(config_path))
    manager = UnifiedConfigManager()
    settings = asyncio.run(manager.load())
    assert settings.providers[0].name == "echo"
