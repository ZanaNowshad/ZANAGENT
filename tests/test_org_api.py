import asyncio
from pathlib import Path

import pytest

from vortex.org.api import OrgOpsAPIServer
from vortex.org.knowledge_graph import OrgKnowledgeGraph
from vortex.org.ops_center import OrgOpsCenter
from vortex.org.policy_engine import OrgPolicyEngine
from vortex.performance import PerformanceMonitor
from vortex.performance.analytics import PerformanceAnalytics, TeamAnalyticsStore


@pytest.mark.asyncio
async def test_org_api_handlers(tmp_path: Path) -> None:
    monitor = PerformanceMonitor()
    analytics = PerformanceAnalytics(monitor)
    team_store = TeamAnalyticsStore(database=tmp_path / "teams.sqlite")
    graph = OrgKnowledgeGraph(database_path=tmp_path / "graph.sqlite")
    policy_engine = OrgPolicyEngine(policy_dir=tmp_path / "policies")
    ops_center = OrgOpsCenter(analytics, team_store, graph, storage_dir=tmp_path)
    server = OrgOpsAPIServer(graph, ops_center, policy_engine, host="127.0.0.1", port=0, token="secret")

    metrics_status, headers, payload = await server._handle_metrics("/metrics", {}, "")
    assert metrics_status == 200
    assert "nodes" in payload

    graph_status, _, graph_payload = await server._handle_graph("/graph", {}, "")
    assert graph_status == 200
    assert "entities" in graph_payload

    query_status, _, query_payload = await server._handle_query("/query", {}, "{\"query\": \"demo\"}")
    assert query_status == 200
    assert "results" in query_payload

    policy_status, _, policy_payload = await server._handle_policies("/policies", {}, "")
    assert policy_status == 200
    assert "policies" in policy_payload

    error_status, _, _ = await server._handle_query("/query", {}, "not-json")
    assert error_status == 400

    assert not server._authorised({"authorization": "Bearer wrong"})
    assert server._authorised({"authorization": "Bearer secret"})

    await server.start()
    await server.stop()


@pytest.mark.asyncio
async def test_org_api_dispatch(tmp_path: Path) -> None:
    monitor = PerformanceMonitor()
    analytics = PerformanceAnalytics(monitor)
    team_store = TeamAnalyticsStore(database=tmp_path / "teams.sqlite")
    graph = OrgKnowledgeGraph(database_path=tmp_path / "graph.sqlite")
    policy_engine = OrgPolicyEngine(policy_dir=tmp_path / "policies")
    ops_center = OrgOpsCenter(analytics, team_store, graph, storage_dir=tmp_path)
    server = OrgOpsAPIServer(graph, ops_center, policy_engine, host="127.0.0.1", port=0, token="secret")
    await server.start()
    sockets = server._server.sockets  # type: ignore[attr-defined]
    assert sockets
    port = sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    request = (
        "GET /metrics HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Authorization: Bearer secret\r\n"
        "Content-Length: 0\r\n\r\n"
    )
    writer.write(request.encode("utf-8"))
    await writer.drain()
    data = await reader.read()
    assert b"200" in data
    writer.close()
    await writer.wait_closed()

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    unauth = "GET /metrics HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\n\r\n"
    writer.write(unauth.encode("utf-8"))
    await writer.drain()
    data = await reader.read()
    assert b"401" in data
    writer.close()
    await writer.wait_closed()

    await server.stop()
