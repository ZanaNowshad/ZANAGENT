"""Minimal REST/GraphQL API surface for organisational insights."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional

from vortex.security.encryption import SecretBox
from vortex.utils.logging import get_logger

from .knowledge_graph import OrgKnowledgeGraph
from .ops_center import OrgOpsCenter
from .policy_engine import OrgPolicyEngine

logger = get_logger(__name__)

HttpHandler = Callable[[str, Dict[str, str], str], Awaitable[tuple[int, Dict[str, str], str]]]


@dataclass
class ApiRoute:
    method: str
    path: str
    handler: HttpHandler


class OrgOpsAPIServer:
    """Tiny HTTP server exposing metrics and graph queries.

    The server intentionally avoids large dependencies.  It supports a subset of
    HTTP/1.1 sufficient for local dashboards and automation hooks.  Requests are
    authenticated through a bearer token encrypted at rest via :class:`SecretBox`.
    """

    def __init__(
        self,
        graph: OrgKnowledgeGraph,
        ops_center: OrgOpsCenter,
        policy_engine: OrgPolicyEngine,
        host: str = "127.0.0.1",
        port: int = 8088,
        token: Optional[str] = None,
    ) -> None:
        self._graph = graph
        self._ops = ops_center
        self._policies = policy_engine
        self._host = host
        self._port = port
        self._routes: list[ApiRoute] = []
        self._server: Optional[asyncio.base_events.Server] = None
        self._secret_box = SecretBox()
        self._token = token or self._secret_box.generate_key().hex()
        self._register_routes()

    # -- routing -----------------------------------------------------------------
    def _register_routes(self) -> None:
        self.add_route("GET", "/metrics", self._handle_metrics)
        self.add_route("GET", "/graph", self._handle_graph)
        self.add_route("POST", "/query", self._handle_query)
        self.add_route("GET", "/policies", self._handle_policies)

    def add_route(self, method: str, path: str, handler: HttpHandler) -> None:
        self._routes.append(ApiRoute(method, path, handler))

    async def _dispatch(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        data = await reader.readuntil(b"\r\n\r\n")
        header_text = data.decode("utf-8", errors="ignore")
        request_line, *header_lines = header_text.strip().split("\r\n")
        method, path, _ = request_line.split(" ")
        headers: Dict[str, str] = {}
        for line in header_lines:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        content_length = int(headers.get("content-length", "0"))
        body = ""
        if content_length:
            body_bytes = await reader.readexactly(content_length)
            body = body_bytes.decode("utf-8", errors="ignore")
        route = next((route for route in self._routes if route.method == method and route.path == path), None)
        if not route:
            response = (404, {"Content-Type": "application/json"}, json.dumps({"error": "not found"}))
        else:
            if not self._authorised(headers):
                response = (401, {"Content-Type": "application/json"}, json.dumps({"error": "unauthorised"}))
            else:
                response = await route.handler(path, headers, body)
        status, response_headers, payload = response
        response_headers.setdefault("Content-Type", "application/json")
        response_bytes = payload.encode("utf-8")
        response_headers["Content-Length"] = str(len(response_bytes))
        header_blob = "".join([f"HTTP/1.1 {status} OK\r\n"] + [f"{k}: {v}\r\n" for k, v in response_headers.items()])
        writer.write(header_blob.encode("utf-8") + b"\r\n" + response_bytes)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    def _authorised(self, headers: Dict[str, str]) -> bool:
        auth = headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return False
        token = auth.split(" ", 1)[1]
        return token == self._token

    # -- handlers ----------------------------------------------------------------
    async def _handle_metrics(self, path: str, headers: Dict[str, str], body: str) -> tuple[int, Dict[str, str], str]:
        payload = self._ops.broadcast_health()
        return 200, {}, json.dumps(payload)

    async def _handle_graph(self, path: str, headers: Dict[str, str], body: str) -> tuple[int, Dict[str, str], str]:
        payload = self._graph.export_graph()
        return 200, {}, json.dumps(payload)

    async def _handle_query(self, path: str, headers: Dict[str, str], body: str) -> tuple[int, Dict[str, str], str]:
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return 400, {}, json.dumps({"error": "invalid json"})
        prompt = payload.get("query", "")
        if not prompt:
            return 400, {}, json.dumps({"error": "query missing"})
        result = self._graph.find_entities(text=prompt)
        return 200, {}, json.dumps({"results": [entity.to_dict() for entity in result]})

    async def _handle_policies(self, path: str, headers: Dict[str, str], body: str) -> tuple[int, Dict[str, str], str]:
        return 200, {}, json.dumps({"policies": self._policies.list_policies()})

    # -- lifecycle ----------------------------------------------------------------
    async def start(self) -> None:
        if self._server:
            return
        self._server = await asyncio.start_server(self._dispatch, self._host, self._port)
        logger.info("Org API server listening", extra={"host": self._host, "port": self._port})

    async def stop(self) -> None:
        if not self._server:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    @property
    def token(self) -> str:
        return self._token

