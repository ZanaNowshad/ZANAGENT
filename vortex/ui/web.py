"""Minimal async web UI server."""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Dict

from vortex.utils.logging import get_logger

logger = get_logger(__name__)

RequestHandler = Callable[[str], Awaitable[str]]


class WebUI:
    """Serve simple JSON responses for remote control."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8080) -> None:
        self._host = host
        self._port = port
        self._routes: Dict[str, RequestHandler] = {}
        self._server: asyncio.base_events.Server | None = None

    def route(self, path: str, handler: RequestHandler) -> None:
        self._routes[path] = handler
        logger.debug("web route registered", extra={"path": path})

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_line = await reader.readline()
        method, path, _ = request_line.decode().split(" ", 2)
        await reader.readuntil(b"\r\n\r\n")  # drain headers
        body = await self._routes.get(path, self._default_handler)(method)
        payload = body.encode("utf-8")
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("utf-8") + payload
        writer.write(response)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def _default_handler(self, _method: str) -> str:
        return "{}"

    async def start(self) -> None:
        if self._server is None:
            self._server = await asyncio.start_server(self._handle, self._host, self._port)
            logger.info("web ui listening", extra={"host": self._host, "port": self._port})

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("web ui stopped")

    async def simulate(self, method: str, path: str) -> str:
        handler = self._routes.get(path, self._default_handler)
        return await handler(method)
