"""Team management and distributed coordination for Vortex agents."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from vortex.performance.analytics import TeamAnalyticsStore
from vortex.security.encryption import CredentialStore, NetworkEncryptor
from vortex.utils.logging import get_logger

from .protocol import AgentConnection, AgentProtocol

logger = get_logger(__name__)

TEAM_ROOT = Path.home() / ".vortex" / "teams"
TEAM_ROOT.mkdir(parents=True, exist_ok=True)


@dataclass
class TeamNode:
    """Representation of a connected node in a team."""

    node_id: str
    name: str
    host: str
    role: str
    read_only: bool
    capabilities: Dict[str, Any]
    last_seen: float
    repositories: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:  # pragma: no cover - serialization helper
        return {
            "node_id": self.node_id,
            "name": self.name,
            "host": self.host,
            "role": self.role,
            "read_only": self.read_only,
            "capabilities": self.capabilities,
            "last_seen": self.last_seen,
            "repositories": list(self.repositories),
        }


@dataclass
class TeamState:
    """Aggregate view of the current team."""

    team_id: str
    broker_uri: str
    mode: str
    nodes: Dict[str, TeamNode]
    ledger: List[Dict[str, Any]]
    attachments: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:  # pragma: no cover - serialization helper
        return {
            "team_id": self.team_id,
            "broker_uri": self.broker_uri,
            "mode": self.mode,
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            "ledger": list(self.ledger),
            "attachments": dict(self.attachments),
        }


class TeamManager:
    """Coordinate multi-agent collaboration sessions."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        team_analytics: Optional[TeamAnalyticsStore] = None,
        node_name: Optional[str] = None,
    ) -> None:
        self._root = root or TEAM_ROOT
        self._root.mkdir(parents=True, exist_ok=True)
        store = CredentialStore(self._root / "secrets")
        key_override = os.getenv("VORTEX_AGENT_KEY")
        if key_override:
            key_bytes = base64.urlsafe_b64decode(key_override.encode("utf-8"))
            encryptor = NetworkEncryptor(key=key_bytes)
        else:
            encryptor = NetworkEncryptor(store=store, name="agent-network")
        self._protocol = AgentProtocol(encryptor, request_handler=self._handle_request, notification_handler=self._handle_notification)
        self._team_analytics = team_analytics or TeamAnalyticsStore(database=self._root / "team-analytics.sqlite")
        self._node_id = uuid.uuid4().hex
        self._node_name = node_name or os.getenv("USER", "operator")
        self._host = socket.gethostname()
        self._mode = "sync"
        self._team_id: Optional[str] = None
        self._broker_uri: Optional[str] = None
        self._server = None
        self._connection: Optional[AgentConnection] = None
        self._nodes: Dict[str, TeamNode] = {}
        self._ledger: List[Dict[str, Any]] = []
        self._attachments: Dict[str, str] = {}
        self._subscribers: List[asyncio.Queue[Dict[str, Any]]] = []
        self._ledger_lock = asyncio.Lock()
        self._sync_interval = float(os.getenv("VORTEX_SYNC_INTERVAL", "5") or 5)
        self._background: Optional[asyncio.Task[None]] = None
        self._capabilities: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Properties and helpers
    # ------------------------------------------------------------------
    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def team_id(self) -> Optional[str]:
        return self._team_id

    @property
    def broker_uri(self) -> Optional[str]:
        return self._broker_uri

    def state(self) -> Optional[TeamState]:
        if not self._team_id:
            return None
        return TeamState(
            team_id=self._team_id,
            broker_uri=self._broker_uri or "",
            mode=self._mode,
            nodes=dict(self._nodes),
            ledger=list(self._ledger),
            attachments=dict(self._attachments),
        )

    def subscribe(self) -> asyncio.Queue[Dict[str, Any]]:
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    async def _publish(self, event: Dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - bounded queues optional
                logger.debug("subscriber queue full", extra={"event": event})

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    async def join(
        self,
        uri: Optional[str] = None,
        *,
        capabilities: Optional[Dict[str, Any]] = None,
        role: str = "editor",
        read_only: bool = False,
        team_id: Optional[str] = None,
    ) -> TeamState:
        """Join or form a team at ``uri``.

        When ``uri`` is omitted we spawn a local broker using the configured
        sync host/port which allows air-gapped collaboration.  The first node to
        join becomes the coordinator and subsequent nodes connect using the
        published broker URI.
        """

        self._capabilities = capabilities or {}
        broker = uri or os.getenv("VORTEX_AGENT_BROKER")
        if broker is None:
            broker = await self._start_local_broker()
        self._broker_uri = broker
        if self._connection is None:
            self._connection = await self._protocol.connect(
                broker,
                request_handler=self._handle_request,
                notification_handler=self._handle_notification,
            )
        request = {
            "node_id": self._node_id,
            "name": self._node_name,
            "host": self._host,
            "role": role,
            "read_only": read_only,
            "capabilities": self._capabilities,
            "team_id": team_id,
        }
        response = await self._connection.request("register", request)
        payload = self._decrypt_result(response)
        self._team_id = payload["team_id"]
        self._mode = payload.get("mode", "sync")
        self._ledger = payload.get("ledger", [])
        nodes = payload.get("nodes", [])
        self._nodes = {
            node["node_id"]: TeamNode(
                node_id=node["node_id"],
                name=node.get("name", node["node_id"]),
                host=node.get("host", "unknown"),
                role=node.get("role", "editor"),
                read_only=bool(node.get("read_only", False)),
                capabilities=node.get("capabilities", {}),
                last_seen=float(node.get("last_seen", time.time())),
                repositories=list(node.get("repositories", [])),
            )
            for node in nodes
        }
        self._attachments = payload.get("attachments", {})
        await self._write_capabilities()
        await self._publish({"kind": "team-join", "team": payload})
        if self._background is None:
            self._background = asyncio.create_task(self._heartbeat())
        return self.state()  # type: ignore[return-value]

    async def leave(self) -> None:
        if self._connection is None:
            return
        try:
            await self._connection.notify("leave", {"node_id": self._node_id})
        finally:
            await self._connection.close()
            self._connection = None
            await self._publish({"kind": "team-leave", "node": self._node_id})
        if self._server is not None:
            await self._server.close()
            self._server = None

    async def list_nodes(self) -> List[Dict[str, Any]]:
        return [node.to_dict() for node in self._nodes.values()]

    async def broadcast(self, message: str, payload: Dict[str, Any]) -> None:
        if self._connection is None:
            return
        await self._connection.request(
            "broadcast",
            {"node_id": self._node_id, "message": message, "payload": payload},
        )

    async def set_mode(self, mode: str) -> None:
        self._mode = mode
        if self._connection:
            await self._connection.notify("mode", {"mode": mode})
        await self._publish({"kind": "mode", "mode": mode})

    async def attach_repo(self, identifier: str, *, path: str) -> None:
        self._attachments[identifier] = self._node_id
        await self._persist_state()
        if self._connection:
            await self._connection.request(
                "attach",
                {"node_id": self._node_id, "repo": identifier, "path": path},
            )
            return
        await self._publish({"kind": "attach", "repo": identifier, "path": path})

    async def handoff(self, repo: str, task: str, *, target: Optional[str] = None) -> None:
        payload = {
            "repo": repo,
            "task": task,
            "source": self._node_id,
            "target": target,
        }
        if self._connection:
            await self._connection.request("handoff", payload)
            return
        await self._publish({"kind": "handoff", **payload})

    async def record_budget(
        self,
        *,
        tokens: float,
        minutes: float,
        reason: str,
        actor: Optional[str] = None,
    ) -> None:
        entry = {
            "timestamp": time.time(),
            "node": actor or self._node_id,
            "tokens": float(tokens),
            "minutes": float(minutes),
            "reason": reason,
        }
        if self._connection:
            await self._connection.request("ledger", {"entry": entry})
            return
        async with self._ledger_lock:
            self._ledger.append(entry)
            await self._persist_state()
        await self._publish({"kind": "ledger", "entry": entry})
        await self._team_analytics.record_entry(self._team_id or "local", entry)

    async def ledger_summary(self) -> Dict[str, Any]:
        async with self._ledger_lock:
            ledger = list(self._ledger)
        tokens = sum(item.get("tokens", 0.0) for item in ledger)
        minutes = sum(item.get("minutes", 0.0) for item in ledger)
        return {"total_tokens": tokens, "total_minutes": minutes, "entries": ledger}

    async def team_metrics(self) -> Dict[str, Any]:
        team_id = self._team_id or "local"
        snapshot = await self._team_analytics.snapshot(team_id)
        totals = snapshot.get("totals", {})
        return {
            "team_id": team_id,
            "total_tokens": float(totals.get("tokens", 0.0) or 0.0),
            "total_minutes": float(totals.get("minutes", 0.0) or 0.0),
            "total_cost": float(totals.get("cost", 0.0) or 0.0),
            "entries": int(totals.get("entries", 0) or 0),
            "contributors": snapshot.get("contributors", []),
        }

    async def insights(self) -> List[str]:
        team_id = self._team_id or "local"
        return await self._team_analytics.insights(team_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _start_local_broker(self) -> str:
        host = os.getenv("VORTEX_TUI_SYNC_HOST", "127.0.0.1")
        port = int(os.getenv("VORTEX_TUI_SYNC_PORT", "0") or 0)
        self._server = await self._protocol.serve(host, port, self._handle_request, notification_handler=self._handle_notification)
        actual_port = self._server.port
        self._team_id = self._team_id or uuid.uuid4().hex
        broker_uri = f"ws://{host}:{actual_port}"
        logger.info("team broker listening", extra={"uri": broker_uri})
        return broker_uri

    async def _heartbeat(self) -> None:  # pragma: no cover - background loop
        while self._connection is not None:
            await asyncio.sleep(self._sync_interval)
            try:
                await self._connection.notify("heartbeat", {"node_id": self._node_id})
            except Exception:
                logger.warning("heartbeat failed", exc_info=True)
                return

    async def _handle_request(
        self, method: str, params: Dict[str, Any], connection: AgentConnection
    ) -> Any:
        if method == "register":
            return await self._handle_register(params, connection)
        if method == "ledger":
            return await self._handle_ledger(params)
        if method == "broadcast":
            await self._handle_broadcast(params, connection)
            return {"status": "ok"}
        if method == "attach":
            await self._handle_attach(params)
            return {"status": "ok"}
        if method == "handoff":
            await self._publish({"kind": "handoff", **params})
            return {"status": "ok"}
        if method == "mode":
            self._mode = params.get("mode", self._mode)
            await self._publish({"kind": "mode", "mode": self._mode})
            return {"status": "ok"}
        if method == "heartbeat":
            node_id = params.get("node_id")
            if node_id and node_id in self._nodes:
                self._nodes[node_id].last_seen = time.time()
            return {"status": "ok"}
        if method == "leave":
            await self._handle_leave(params, connection)
            return {"status": "ok"}
        raise RuntimeError(f"Unknown RPC method {method}")

    async def _handle_notification(
        self, method: str, params: Dict[str, Any], connection: AgentConnection
    ) -> None:
        if method == "team.event":
            await self._publish(params)
            return
        if method == "ledger":
            await self._handle_ledger(params)
            return
        if method == "mode":
            self._mode = params.get("mode", self._mode)
            await self._publish({"kind": "mode", "mode": self._mode})
            return
        if method == "broadcast":
            await self._publish({"kind": "broadcast", **params})
            return

    async def _handle_register(self, params: Dict[str, Any], connection: AgentConnection) -> Dict[str, Any]:
        self._team_id = self._team_id or params.get("team_id") or uuid.uuid4().hex
        node_id = params.get("node_id", uuid.uuid4().hex)
        connection.metadata["node_id"] = node_id
        node = TeamNode(
            node_id=node_id,
            name=params.get("name", node_id),
            host=params.get("host", "unknown"),
            role=params.get("role", "editor"),
            read_only=bool(params.get("read_only", False)),
            capabilities=params.get("capabilities", {}),
            last_seen=time.time(),
            repositories=[],
        )
        self._nodes[node_id] = node
        await self._publish({"kind": "join", "node": node.to_dict()})
        state = {
            "team_id": self._team_id,
            "mode": self._mode,
            "nodes": [item.to_dict() for item in self._nodes.values()],
            "ledger": list(self._ledger),
            "attachments": dict(self._attachments),
        }
        return state

    async def _handle_ledger(self, params: Dict[str, Any]) -> Dict[str, Any]:
        entry = params.get("entry")
        if not entry:
            return {"status": "ignored"}
        async with self._ledger_lock:
            self._ledger.append(entry)
            await self._persist_state()
        await self._team_analytics.record_entry(self._team_id or "local", entry)
        await self._publish({"kind": "ledger", "entry": entry})
        return {"status": "ok"}

    async def _handle_broadcast(self, params: Dict[str, Any], connection: AgentConnection) -> None:
        message = params.get("message", "")
        payload = params.get("payload", {})
        node_id = params.get("node_id")
        event = {"kind": "broadcast", "message": message, "payload": payload, "node": node_id}
        await self._publish(event)
        for peer in list(self._protocol._connections.values()):  # pragma: no cover - network scatter
            if peer.peer_id == connection.peer_id:
                continue
            await peer.notify("team.event", event)

    async def _handle_attach(self, params: Dict[str, Any]) -> None:
        repo = params.get("repo")
        node_id = params.get("node_id")
        if not repo or not node_id:
            return
        path = params.get("path", "")
        self._attachments[repo] = node_id
        await self._persist_state()
        await self._publish({"kind": "attach", "repo": repo, "path": path, "node": node_id})

    async def _handle_leave(self, params: Dict[str, Any], connection: AgentConnection) -> None:
        node_id = params.get("node_id") or connection.metadata.get("node_id")
        if node_id and node_id in self._nodes:
            self._nodes.pop(node_id, None)
            await self._publish({"kind": "leave", "node": node_id})

    async def _persist_state(self) -> None:
        if not self._team_id:
            return
        team_dir = self._root / self._team_id
        team_dir.mkdir(parents=True, exist_ok=True)
        ledger_path = team_dir / "ledger.json"
        ledger_path.write_text(json.dumps(self._ledger, indent=2), encoding="utf-8")
        attachments_path = team_dir / "attachments.json"
        attachments_path.write_text(json.dumps(self._attachments, indent=2), encoding="utf-8")

    async def _write_capabilities(self) -> None:
        if not self._team_id:
            return
        team_dir = self._root / self._team_id
        team_dir.mkdir(parents=True, exist_ok=True)
        path = team_dir / "agent.capabilities.json"
        payload = {
            "node_id": self._node_id,
            "name": self._node_name,
            "host": self._host,
            "capabilities": self._capabilities,
            "timestamp": time.time(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _decrypt_result(self, response: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(response, dict):
            return {}
        result = response.get("result")
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            try:
                decrypted = self._protocol.encryptor.decrypt(result.encode("utf-8"))
                payload = json.loads(decrypted.decode("utf-8"))
                if isinstance(payload, dict) and "result" in payload:
                    inner = payload["result"]
                    if isinstance(inner, dict):
                        return inner
                    return {"result": inner}
            except Exception:  # pragma: no cover - surfaced in tests
                logger.exception("failed to decrypt result payload")
                return {}
        return {}


__all__ = ["TeamManager", "TeamNode", "TeamState"]
