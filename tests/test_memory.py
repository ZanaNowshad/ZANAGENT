import asyncio
from pathlib import Path

import pytest

from vortex.core.memory import UnifiedMemorySystem


def test_memory_roundtrip(tmp_path: Path):
    async def _run():
        db = tmp_path / "memory.db"
        memory = UnifiedMemorySystem(f"sqlite:///{db}")
        record = await memory.add("note", "remember the milk")
        results = await memory.search("milk")
        assert any(r.id == record.id for r in results)
        summary = await memory.summarise()
        assert "remember" in summary

    asyncio.run(_run())
