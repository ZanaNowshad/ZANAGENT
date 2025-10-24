"""JSON-RPC over WebSocket transport for multi-agent collaboration."""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

from websockets.client import connect as ws_connect
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed
from websockets.server import WebSocketServerProtocol, serve

from vortex.security.encryption import NetworkEncryptor
from vortex.utils.logging import get_logger

logger = get_logger(__name__)

RequestHandler = Callable[[str, Dict[str, Any], "AgentConnection"], Awaitable[Any]]
NotificationHandler = Callable[[str, Dict[str, Any], "AgentConnection"], Awaitable[None]]


@dataclass
class AgentServer:
    """Wrapper around a running WebSocket server.

    ``websockets`` changed the structure of the object returned by
    :func:`~websockets.server.serve` in recent releases.  Older versions exposed
    a ``ws_server`` attribute while modern builds expose the ``sockets`` and
    ``close`` helpers directly on the returned instance.  The helpers below keep
    the code compatible with both layouts and make the behaviour explicit for
    tests so we can deterministically bind to ephemeral ports.
    """

    _serve: Any

    @property
    def _sockets(self) -> list[Any]:
        server = self._serve
        if hasattr(server, "sockets"):
            sockets = getattr(server, "sockets") or []
        else:  # pragma: no cover - compatibility with very old versions
            ws_server = getattr(server, "ws_server", None)
            sockets = getattr(ws_server, "sockets", []) if ws_server else []
        return list(sockets)

    @property
    def port(self) -> int:
        sockets = self._sockets
        if not sockets:  # pragma: no cover - defensive
            return 0
        return sockets[0].getsockname()[1]

    async def close(self) -> None:
        server = self._serve
        closer = getattr(server, "close", None)
        waiter = getattr(server, "wait_closed", None)
        if closer is not None:
            closer()
        if asyncio.iscoroutinefunction(waiter):  # pragma: no cover - depends on version
            await waiter()
        elif waiter is not None:
            await waiter


@dataclass
class AgentConnection:
    """Represents a peer in the agent mesh."""

    websocket: WebSocketClientProtocol | WebSocketServerProtocol
    protocol: "AgentProtocol"
    peer_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    async def request(self, method: str, params: Dict[str, Any]) -> Any:
        return await self.protocol.send_request(self, method, params)

    async def notify(self, method: str, params: Dict[str, Any]) -> None:
        await self.protocol.send_notification(self, method, params)

    async def close(self) -> None:
        await self.websocket.close()


class AgentProtocol:
    """Lightweight JSON-RPC 2.0 helper with symmetric encryption."""

    def __init__(
        self,
        encryptor: NetworkEncryptor,
        *,
        request_handler: Optional[RequestHandler] = None,
        notification_handler: Optional[NotificationHandler] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self._encryptor = encryptor
        self._loop = loop or asyncio.get_event_loop()
        self._request_handler = request_handler
        self._notification_handler = notification_handler
        self._pending: Dict[str, asyncio.Future[Any]] = {}
        self._connections: Dict[str, AgentConnection] = {}
        self._lock = asyncio.Lock()

    def connection(self, peer_id: str) -> Optional[AgentConnection]:
        return self._connections.get(peer_id)

    @property
    def encryptor(self) -> NetworkEncryptor:
        return self._encryptor

    async def serve(
        self,
        host: str,
        port: int,
        handler: RequestHandler,
        *,
        notification_handler: Optional[NotificationHandler] = None,
    ) -> AgentServer:
        self._request_handler = handler
        self._notification_handler = notification_handler

        async def _accept(websocket: WebSocketServerProtocol) -> None:
            peer_id = uuid.uuid4().hex
            connection = AgentConnection(websocket=websocket, protocol=self, peer_id=peer_id)
            self._connections[peer_id] = connection
            try:
                await self._reader(connection)
            finally:
                self._connections.pop(peer_id, None)

        server = await serve(_accept, host, port)
        return AgentServer(server)

    async def connect(
        self,
        uri: str,
        *,
        request_handler: Optional[RequestHandler] = None,
        notification_handler: Optional[NotificationHandler] = None,
    ) -> AgentConnection:
        websocket = await ws_connect(uri)
        peer_id = uuid.uuid4().hex
        connection = AgentConnection(websocket=websocket, protocol=self, peer_id=peer_id)
        self._connections[peer_id] = connection
        if request_handler is not None:
            self._request_handler = request_handler
        if notification_handler is not None:
            self._notification_handler = notification_handler
        asyncio.create_task(self._reader(connection))
        return connection

    async def _reader(self, connection: AgentConnection) -> None:
        websocket = connection.websocket
        try:
            async for message in websocket:
                await self._handle_frame(connection, message)
        except ConnectionClosed:  # pragma: no cover - network errors are environment dependent
            logger.info("agent connection closed", extra={"peer": connection.peer_id})
        finally:
            self._connections.pop(connection.peer_id, None)

    async def send_request(self, connection: AgentConnection, method: str, params: Dict[str, Any]) -> Any:
        request_id = uuid.uuid4().hex
        payload = {"method": method, "params": params}
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        frame = {
            "jsonrpc": "2.0",
            "id": request_id,
            "payload": self._encryptor.encrypt(payload_bytes).decode("utf-8"),
        }
        future: asyncio.Future[Any] = self._loop.create_future()
        async with self._lock:
            self._pending[request_id] = future
        await connection.websocket.send(json.dumps(frame))
        return await future

    async def send_notification(
        self, connection: AgentConnection, method: str, params: Dict[str, Any]
    ) -> None:
        payload = {"method": method, "params": params}
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        frame = {
            "jsonrpc": "2.0",
            "payload": self._encryptor.encrypt(payload_bytes).decode("utf-8"),
        }
        await connection.websocket.send(json.dumps(frame))

    async def broadcast(self, method: str, params: Dict[str, Any]) -> None:
        payload = {"method": method, "params": params}
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        frame = {
            "jsonrpc": "2.0",
            "payload": self._encryptor.encrypt(payload_bytes).decode("utf-8"),
        }
        data = json.dumps(frame)
        await asyncio.gather(
            *[conn.websocket.send(data) for conn in list(self._connections.values())],
            return_exceptions=True,
        )

    async def _handle_frame(self, connection: AgentConnection, raw: str) -> None:
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("invalid frame", extra={"raw": raw[:80]})
            return
        if "id" in frame and ("result" in frame or "error" in frame):
            request_id = frame["id"]
            future = self._pending.pop(request_id, None)
            if future is None:
                return
            if "error" in frame:
                future.set_exception(RuntimeError(frame["error"]))
            else:
                result_token = frame.get("result")
                if isinstance(result_token, str):
                    try:
                        decrypted = self._encryptor.decrypt(result_token.encode("utf-8"))
                        result_payload = json.loads(decrypted.decode("utf-8"))
                    except Exception as exc:  # pragma: no cover - surfaced in tests
                        logger.exception("failed to decrypt result", exc_info=exc)
                        future.set_exception(exc)
                        return
                    future.set_result(result_payload)
                else:
                    future.set_result(result_token)
            return
        payload = frame.get("payload")
        if not isinstance(payload, str):
            logger.warning("missing payload in frame", extra={"frame": frame})
            return
        try:
            decrypted = self._encryptor.decrypt(payload.encode("utf-8"))
            message = json.loads(decrypted.decode("utf-8"))
        except Exception:  # pragma: no cover - surfaced in tests
            logger.exception("failed to decrypt payload", extra={"frame": frame})
            return
        method = message.get("method")
        params = message.get("params", {})
        request_id = frame.get("id")
        if request_id is None:
            if self._notification_handler:
                await self._notification_handler(method, params, connection)
            return
        if self._request_handler is None:
            logger.warning("request received but no handler registered", extra={"method": method})
            return
        try:
            result = await self._request_handler(method, params, connection)
            result_bytes = json.dumps({"result": result}, ensure_ascii=False).encode("utf-8")
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": self._encryptor.encrypt(result_bytes).decode("utf-8"),
            }
        except Exception as exc:  # pragma: no cover - surfaced by tests
            logger.exception("request handler failed", exc_info=exc)
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": str(exc),
            }
        await connection.websocket.send(json.dumps(response))


__all__ = ["AgentConnection", "AgentProtocol", "AgentServer", "RequestHandler", "NotificationHandler"]
