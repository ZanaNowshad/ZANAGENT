# Organisation Knowledge Graph

Vortex maintains a persistent knowledge graph that links projects, sessions,
agents, pipelines, policies, and releases. The graph is stored locally in
`~/.vortex/org/knowledge_graph.db` using SQLite and can optionally be mirrored
to a Neo4j instance by configuring the `org.knowledge_graph.neo4j_uri` setting.

## Entities

Entities are typed using the `vortex.org.relations.EntityType` enumeration. The
most common nodes are:

- **project** – Registered repositories and orchestrated workstreams.
- **session** – Collaborative TUI sessions and transcripts.
- **pipeline** – CI/CD runs, linked back to the project that initiated them.
- **agent** – Connected Vortex nodes with declared capabilities.
- **policy** – Governance rules loaded from `~/.vortex/org/policies`.

Relationships (e.g. `related_to`, `uses`, `member_of`) capture the dependencies
between these nodes. All mutations are immediately persisted so the knowledge
graph survives restarts and can be queried by any Vortex client.

## Indexing

The graph automatically indexes:

1. Collaborative sessions and their transcripts.
2. Pipeline runs recorded via the Ops Centre.
3. Projects registered through `/project init` and `/attach` commands.
4. Team events recorded by the analytics store.

Custom data can be ingested through the Python API:

```python
from vortex.org import OrgKnowledgeGraph
from vortex.org.relations import EntityType, GraphEntity

graph = OrgKnowledgeGraph()
graph.upsert_entity(GraphEntity(id="tool:black", type=EntityType.TOOL, attributes={"version": "23.3"}))
```

## Querying

Use `/graph view` from the TUI to render a snapshot or the CLI to search:

```bash
vortex graph ask "show recent projects"
vortex graph find project --term platform
```

The API server exposed via `vortex org serve` responds with the full graph in
JSON format for integration with external dashboards.
