import json
from pathlib import Path

from vortex.org.knowledge_graph import OrgKnowledgeGraph
from vortex.org.relations import EntityType, GraphEntity, GraphRelation, RelationType


def test_knowledge_graph_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "kg.sqlite"
    graph = OrgKnowledgeGraph(database_path=db_path)
    project = GraphEntity(id="project:test", type=EntityType.PROJECT, attributes={"name": "demo"})
    graph.upsert_entity(project)
    pipeline = GraphEntity(
        id="pipeline:build",
        type=EntityType.PIPELINE,
        attributes={"status": "passed", "latency": 12.0},
    )
    graph.upsert_entity(pipeline)
    relation = GraphRelation(
        source=pipeline.id,
        target=project.id,
        type=RelationType.RELATES_TO,
        attributes={"reason": "ci"},
    )
    graph.add_relation(relation)
    graph.index_session("abc", {"owner": "alice"})
    graph.index_project("demo", {"language": "python"})

    snapshot = graph.snapshot()
    assert any(entity.id == project.id for entity in snapshot.entities)
    assert any(rel.source == pipeline.id for rel in snapshot.relations)
    exported = graph.export_graph()
    assert exported["entities"]
    assert exported["relations"]
    graph.configure_neo4j("bolt://localhost:7687")
    refreshed = graph.export_graph()
    assert refreshed["neo4j_uri"] == "bolt://localhost:7687"
    assert graph.find_entities(EntityType.PROJECT, "demo")
    assert graph.neighbours(pipeline.id).entities
    graph.delete_entity(pipeline.id)
    assert graph.get_entity(pipeline.id) is None
    graph.close()
