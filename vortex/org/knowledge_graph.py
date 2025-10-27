"""Persistent organisational knowledge graph."""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from vortex.utils.logging import get_logger

from .relations import EntityType, GraphEntity, GraphRelation, RelationType

logger = get_logger(__name__)


@dataclass
class GraphQueryResult:
    """Container returned from graph lookups."""

    entities: List[GraphEntity]
    relations: List[GraphRelation]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [entity.to_dict() for entity in self.entities],
            "relations": [relation.to_dict() for relation in self.relations],
        }


class OrgKnowledgeGraph:
    """Organisation-level graph persisted to SQLite.

    The implementation keeps the storage simple and dependency-free.  SQLite is
    used for durability and optional Neo4j integration can be added by
    registering a bolt URI through :meth:`configure_neo4j`.
    """

    def __init__(self, database_path: Optional[Path] = None) -> None:
        self._path = database_path or Path.home() / ".vortex" / "org" / "knowledge_graph.db"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._path)
        self._connection.row_factory = sqlite3.Row
        self._ensure_schema()
        self._neo4j_uri: Optional[str] = None

    # -- schema -----------------------------------------------------------------
    def _ensure_schema(self) -> None:
        cur = self._connection.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                data TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                type TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY(source) REFERENCES entities(id),
                FOREIGN KEY(target) REFERENCES entities(id)
            )
            """
        )
        self._connection.commit()

    # -- configuration -----------------------------------------------------------
    def configure_neo4j(self, uri: str) -> None:
        """Register an optional Neo4j bolt URI.

        The library does not depend on a specific driver; the URI is stored so a
        downstream integration can pick it up.  Tests assert the value is kept.
        """

        self._neo4j_uri = uri
        logger.info("Neo4j endpoint configured", extra={"uri": uri})

    # -- entity management -------------------------------------------------------
    def upsert_entity(self, entity: GraphEntity) -> None:
        logger.debug("Upserting entity", extra={"id": entity.id, "type": entity.type.value})
        cur = self._connection.cursor()
        cur.execute(
            """
            INSERT INTO entities(id, type, data, updated_at)
            VALUES (:id, :type, :data, :updated_at)
            ON CONFLICT(id) DO UPDATE SET data=:data, type=:type, updated_at=:updated_at
            """,
            {
                "id": entity.id,
                "type": entity.type.value,
                "data": json.dumps(entity.attributes, sort_keys=True),
                "updated_at": time.time(),
            },
        )
        self._connection.commit()

    def upsert_entities(self, entities: Iterable[GraphEntity]) -> None:
        for entity in entities:
            self.upsert_entity(entity)

    def delete_entity(self, entity_id: str) -> None:
        cur = self._connection.cursor()
        cur.execute("DELETE FROM relations WHERE source=:id OR target=:id", {"id": entity_id})
        cur.execute("DELETE FROM entities WHERE id=:id", {"id": entity_id})
        self._connection.commit()

    def get_entity(self, entity_id: str) -> Optional[GraphEntity]:
        cur = self._connection.cursor()
        row = cur.execute("SELECT * FROM entities WHERE id=:id", {"id": entity_id}).fetchone()
        if not row:
            return None
        return GraphEntity(
            id=row["id"],
            type=EntityType(row["type"]),
            attributes=json.loads(row["data"]),
        )

    # -- relations ---------------------------------------------------------------
    def add_relation(self, relation: GraphRelation) -> None:
        logger.debug(
            "Recording relation", extra={"source": relation.source, "target": relation.target}
        )
        cur = self._connection.cursor()
        cur.execute(
            """
            INSERT INTO relations(source, target, type, data, created_at)
            VALUES (:source, :target, :type, :data, :created_at)
            """,
            {
                "source": relation.source,
                "target": relation.target,
                "type": relation.type.value,
                "data": json.dumps(relation.attributes, sort_keys=True),
                "created_at": time.time(),
            },
        )
        self._connection.commit()

    def relations_from(self, entity_id: str) -> List[GraphRelation]:
        cur = self._connection.cursor()
        rows = cur.execute("SELECT * FROM relations WHERE source=:id", {"id": entity_id}).fetchall()
        return [
            GraphRelation(
                source=row["source"],
                target=row["target"],
                type=RelationType(row["type"]),
                attributes=json.loads(row["data"]),
            )
            for row in rows
        ]

    def relations_to(self, entity_id: str) -> List[GraphRelation]:
        cur = self._connection.cursor()
        rows = cur.execute("SELECT * FROM relations WHERE target=:id", {"id": entity_id}).fetchall()
        return [
            GraphRelation(
                source=row["source"],
                target=row["target"],
                type=RelationType(row["type"]),
                attributes=json.loads(row["data"]),
            )
            for row in rows
        ]

    # -- discovery ----------------------------------------------------------------
    def find_entities(self, entity_type: EntityType | None = None, text: str | None = None) -> List[GraphEntity]:
        cur = self._connection.cursor()
        if entity_type and text:
            rows = cur.execute(
                """
                SELECT * FROM entities
                WHERE type=:type AND data LIKE :query
                ORDER BY updated_at DESC
                """,
                {"type": entity_type.value, "query": f"%{text}%"},
            ).fetchall()
        elif entity_type:
            rows = cur.execute(
                "SELECT * FROM entities WHERE type=:type ORDER BY updated_at DESC",
                {"type": entity_type.value},
            ).fetchall()
        elif text:
            rows = cur.execute(
                "SELECT * FROM entities WHERE data LIKE :query ORDER BY updated_at DESC",
                {"query": f"%{text}%"},
            ).fetchall()
        else:
            rows = cur.execute("SELECT * FROM entities ORDER BY updated_at DESC").fetchall()
        return [
            GraphEntity(id=row["id"], type=EntityType(row["type"]), attributes=json.loads(row["data"]))
            for row in rows
        ]

    def neighbours(self, entity_id: str) -> GraphQueryResult:
        entity = self.get_entity(entity_id)
        if not entity:
            return GraphQueryResult([], [])
        outgoing = self.relations_from(entity_id)
        ids = {relation.target for relation in outgoing}
        if ids:
            cur = self._connection.cursor()
            rows = cur.execute(
                "SELECT * FROM entities WHERE id IN (%s)" % ",".join(["?"] * len(ids)),
                list(ids),
            ).fetchall()
            neighbours = [
                GraphEntity(id=row["id"], type=EntityType(row["type"]), attributes=json.loads(row["data"]))
                for row in rows
            ]
        else:
            neighbours = []
        return GraphQueryResult([entity] + neighbours, outgoing)

    # -- ingestion ----------------------------------------------------------------
    def index_session(self, session_id: str, metadata: Dict[str, Any]) -> None:
        entity = GraphEntity(
            id=f"session:{session_id}",
            type=EntityType.SESSION,
            attributes=metadata,
        )
        self.upsert_entity(entity)

    def index_project(self, project_id: str, metadata: Dict[str, Any]) -> None:
        project_entity = GraphEntity(
            id=f"project:{project_id}",
            type=EntityType.PROJECT,
            attributes=metadata,
        )
        self.upsert_entity(project_entity)

    def index_pipeline_run(self, pipeline_id: str, project_id: str, metadata: Dict[str, Any]) -> None:
        pipeline_entity = GraphEntity(
            id=f"pipeline:{pipeline_id}",
            type=EntityType.PIPELINE,
            attributes=metadata,
        )
        self.upsert_entity(pipeline_entity)
        self.add_relation(
            GraphRelation(
                source=pipeline_entity.id,
                target=f"project:{project_id}",
                type=RelationType.RELATES_TO,
                attributes={"reason": "pipeline-run"},
            )
        )

    def snapshot(self) -> GraphQueryResult:
        entities = self.find_entities()
        cur = self._connection.cursor()
        rows = cur.execute("SELECT * FROM relations").fetchall()
        relations = [
            GraphRelation(
                source=row["source"],
                target=row["target"],
                type=RelationType(row["type"]),
                attributes=json.loads(row["data"]),
            )
            for row in rows
        ]
        return GraphQueryResult(entities, relations)

    # -- export -------------------------------------------------------------------
    def export_graph(self) -> Dict[str, Any]:
        snapshot = self.snapshot()
        payload = snapshot.to_dict()
        payload["neo4j_uri"] = self._neo4j_uri
        return payload

    def close(self) -> None:
        self._connection.close()

