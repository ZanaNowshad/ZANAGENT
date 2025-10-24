"""Persistent memory and vector search infrastructure."""
from __future__ import annotations

import asyncio
import json
import math
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from vortex.utils.errors import MemoryError
from vortex.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryRecord:
    """Represents a stored memory item."""

    id: int
    kind: str
    content: str
    metadata: Dict[str, Any]
    embedding: List[float]
    created_at: float


class SimpleVectorStore:
    """Naive in-memory vector store with cosine similarity."""

    def __init__(self) -> None:
        self._vectors: Dict[int, List[float]] = {}

    def add(self, record_id: int, vector: List[float]) -> None:
        self._vectors[record_id] = vector

    def remove(self, record_id: int) -> None:
        self._vectors.pop(record_id, None)

    def search(self, vector: List[float], limit: int = 5) -> List[Tuple[int, float]]:
        results: List[Tuple[int, float]] = []
        for record_id, stored in self._vectors.items():
            score = self._cosine_similarity(vector, stored)
            results.append((record_id, score))
        results.sort(key=lambda item: item[1], reverse=True)
        return results[:limit]

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


def _hash_embedding(text: str, dimensions: int = 16) -> List[float]:
    """Deterministically map text to a vector.

    Real deployments would rely on an embedding provider such as OpenAI or
    HuggingFace. The deterministic hash-based embedding keeps tests hermetic and
    ensures the vector store stays functional without external services.
    """

    import hashlib

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [int.from_bytes(digest[i : i + 2], "big") / 65535.0 for i in range(0, dimensions * 2, 2)]


class UnifiedMemorySystem:
    """Coordinate relational persistence and vector search."""

    def __init__(self, database_url: str, vector_store: Optional[SimpleVectorStore] = None) -> None:
        if not database_url.startswith("sqlite"):
            raise MemoryError("Only SQLite is supported by the reference implementation")
        path = database_url.split("///")[-1]
        self.db_path = Path(path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._vector_store = vector_store or SimpleVectorStore()
        self._setup()

    def _setup(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                embedding TEXT,
                created_at REAL
            )
            """
        )
        self._conn.commit()

    async def add(self, kind: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> MemoryRecord:
        """Persist a memory and update the vector store."""

        metadata = metadata or {}
        embedding = _hash_embedding(content)
        async with self._lock:
            cursor = await asyncio.to_thread(
                self._conn.execute,
                "INSERT INTO memory (kind, content, metadata, embedding, created_at) VALUES (?, ?, ?, ?, ?)",
                (kind, content, json.dumps(metadata), json.dumps(embedding), time.time()),
            )
            self._conn.commit()
            record_id = cursor.lastrowid
            self._vector_store.add(record_id, embedding)
            return MemoryRecord(record_id, kind, content, metadata, embedding, time.time())

    async def delete(self, record_id: int) -> None:
        async with self._lock:
            await asyncio.to_thread(self._conn.execute, "DELETE FROM memory WHERE id = ?", (record_id,))
            self._conn.commit()
            self._vector_store.remove(record_id)

    async def search(self, query: str, limit: int = 5) -> List[MemoryRecord]:
        """Semantic search using cosine similarity."""

        vector = _hash_embedding(query)
        ids = self._vector_store.search(vector, limit=limit)
        records: List[MemoryRecord] = []
        for record_id, score in ids:
            cursor = await asyncio.to_thread(self._conn.execute, "SELECT * FROM memory WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            if not row:
                continue
            records.append(
                MemoryRecord(
                    id=row["id"],
                    kind=row["kind"],
                    content=row["content"],
                    metadata=json.loads(row["metadata"] or "{}"),
                    embedding=json.loads(row["embedding"] or "[]"),
                    created_at=row["created_at"],
                )
            )
        return records

    async def list(self, limit: int = 20) -> List[MemoryRecord]:
        cursor = await asyncio.to_thread(
            self._conn.execute, "SELECT * FROM memory ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = cursor.fetchall()
        return [
            MemoryRecord(
                id=row["id"],
                kind=row["kind"],
                content=row["content"],
                metadata=json.loads(row["metadata"] or "{}"),
                embedding=json.loads(row["embedding"] or "[]"),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def summarise(self, limit: int = 5) -> str:
        """Produce a naive summary of the most recent memories.

        In production this would delegate to a language model. Here we keep the
        logic deterministic yet informative.
        """

        records = await self.list(limit=limit)
        summary = "; ".join(f"[{r.kind}] {r.content}" for r in records)
        return summary or "No memories yet"


__all__ = ["UnifiedMemorySystem", "MemoryRecord", "SimpleVectorStore"]
