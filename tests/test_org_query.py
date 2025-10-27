from pathlib import Path

from vortex.ai import NLPEngine
from vortex.org.knowledge_graph import OrgKnowledgeGraph
from vortex.org.query import GraphQueryService
from vortex.org.relations import EntityType, GraphEntity


def test_graph_query_service(tmp_path: Path) -> None:
    graph = OrgKnowledgeGraph(database_path=tmp_path / "graph.sqlite")
    graph.upsert_entity(
        GraphEntity(id="project:demo", type=EntityType.PROJECT, attributes={"label": "project Demo"})
    )
    service = GraphQueryService(graph, NLPEngine())
    result = service.query("project Demo")
    assert result.entities
    graph.close()
