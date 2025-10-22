"""Collaboration and multi-session coordination for the Vortex TUI."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from vortex.performance.analytics import SessionAnalyticsStore
from vortex.security.encryption import CredentialStore, SessionEncryptor
from vortex.utils.logging import get_logger
from vortex.utils.profiling import profile

logger = get_logger(__name__)

SESSION_ROOT = Path.home() / ".vortex" / "sessions"
SESSION_ROOT.mkdir(parents=True, exist_ok=True)


@dataclass
class SessionMetadata:
    """Metadata describing a collaborative session."""

    session_id: str
    title: str
    created_at: float
    created_by: str
    share_key: Optional[str]
    collaborators: Dict[str, Dict[str, Any]]
    path: Path

    @property
    def participants(self) -> List[str]:
        return list(self.collaborators.keys())


@dataclass
class SessionEvent:
    """Event broadcast across participants."""

    identifier: str
    kind: str
    payload: Dict[str, Any]
    author: str
    timestamp: float

    def to_json(self, *, encrypted: bool, payload: Any) -> str:
        record = {
            "id": self.identifier,
            "kind": self.kind,
            "author": self.author,
            "timestamp": self.timestamp,
            "encrypted": encrypted,
            "payload": payload,
        }
        return json.dumps(record, ensure_ascii=False)


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:  # pragma: no cover - platform guard
        return "localhost"


class SessionManager:
    """Manage collaborative sessions, transcripts, and event propagation."""

    def __init__(
        self,
        *,
        root: Path = SESSION_ROOT,
        encryptor: Optional[SessionEncryptor] = None,
        analytics: Optional[SessionAnalyticsStore] = None,
        poll_interval: float = 0.75,
    ) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        store = CredentialStore(self._root / "secrets")
        self._encryptor = encryptor or SessionEncryptor(store)
        self._analytics = analytics
        self._locks: Dict[str, asyncio.Lock] = {}
        self._queues: Dict[str, asyncio.Queue[SessionEvent]] = {}
        self._pollers: Dict[str, asyncio.Task[None]] = {}
        self._positions: Dict[str, int] = {}
        self._poll_interval = max(0.25, poll_interval)
        self._sync_host = os.getenv("VORTEX_TUI_SYNC_HOST")
        self._sync_port = int(os.getenv("VORTEX_TUI_SYNC_PORT", "0") or 0)
        self._hostname = _hostname()

    # ------------------------------------------------------------------
    # Session lifecycle helpers
    # ------------------------------------------------------------------
    async def create_session(self, title: str, user: str) -> SessionMetadata:
        """Create a new collaborative session owned by ``user``."""

        session_id = uuid.uuid4().hex[:12]
        path = self._root / session_id
        path.mkdir(parents=True, exist_ok=True)
        (path / "transcript.md").touch(exist_ok=True)
        (path / "plan.json").write_text("{}", encoding="utf-8")
        (path / "metrics.jsonl").touch(exist_ok=True)
        (path / "events.jsonl").touch(exist_ok=True)
        share_key = self._encryptor.ensure_session_key(session_id)
        metadata = SessionMetadata(
            session_id=session_id,
            title=title,
            created_at=time.time(),
            created_by=user,
            share_key=share_key,
            collaborators={
                f"{user}@{self._hostname}": {
                    "user": user,
                    "host": self._hostname,
                    "role": "owner",
                    "read_only": False,
                    "last_seen": time.time(),
                }
            },
            path=path,
        )
        await self._write_metadata(metadata, owner=user)
        if self._analytics:
            await self._analytics.register_session(session_id, title, owner=user)
        logger.info("session created", extra={"session_id": session_id, "title": title})
        return metadata

    async def list_sessions(self) -> List[SessionMetadata]:
        """Return metadata for sessions stored on disk."""

        results: List[SessionMetadata] = []
        for path in self._root.iterdir():
            if not path.is_dir():
                continue
            meta_path = path / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                payload = json.loads(meta_path.read_text())
                metadata = SessionMetadata(
                    session_id=payload["session_id"],
                    title=payload.get("title", payload["session_id"]),
                    created_at=payload.get("created_at", 0.0),
                    created_by=payload.get("created_by", "unknown"),
                    share_key=payload.get("share_key"),
                    collaborators=payload.get("collaborators", {}),
                    path=path,
                )
                results.append(metadata)
            except Exception:
                logger.warning("corrupt session metadata", extra={"path": str(meta_path)})
        results.sort(key=lambda item: item.created_at, reverse=True)
        return results

    async def join_session(
        self,
        session_id: str,
        user: str,
        *,
        role: str = "collaborator",
        read_only: bool = False,
    ) -> SessionMetadata:
        """Join an existing session and register presence."""

        metadata = await self._load_metadata(session_id)
        collaborator = {
            "user": user,
            "host": self._hostname,
            "role": role,
            "read_only": read_only,
            "last_seen": time.time(),
        }
        metadata.collaborators[f"{user}@{self._hostname}"] = collaborator
        await self._write_metadata(metadata)
        logger.info(
            "session joined",
            extra={"session_id": session_id, "user": user, "role": role, "read_only": read_only},
        )
        if self._analytics:
            await self._analytics.register_session(
                session_id, metadata.title, owner=metadata.created_by
            )
        return metadata

    async def join_with_token(self, token: str, user: str) -> SessionMetadata:
        """Join a session using an encrypted share token."""

        session_id, role, read_only = self._encryptor.decode_share_token(token)
        return await self.join_session(session_id, user, role=role, read_only=read_only)

    def parse_share_token(self, token: str) -> Tuple[str, str, bool]:
        """Decode ``token`` without mutating session metadata."""

        return self._encryptor.decode_share_token(token)

    async def share_session(
        self, session_id: str, *, role: str = "collaborator", read_only: bool = False
    ) -> str:
        """Return a share token for inviting another collaborator."""

        metadata = await self._load_metadata(session_id)
        token = self._encryptor.generate_share_token(session_id, role=role, read_only=read_only)
        metadata.share_key = metadata.share_key or self._encryptor.ensure_session_key(session_id)
        await self._write_metadata(metadata)
        return token

    async def session_details(self, session_id: str) -> Dict[str, Any]:
        """Return the serialisable metadata for ``session_id``."""

        metadata = await self._load_metadata(session_id)
        return {
            "session_id": metadata.session_id,
            "title": metadata.title,
            "created_at": metadata.created_at,
            "created_by": metadata.created_by,
            "collaborators": metadata.collaborators,
            "share_key": metadata.share_key,
            "transcript": str((metadata.path / "transcript.md")),
        }

    # ------------------------------------------------------------------
    # Event streaming
    # ------------------------------------------------------------------
    async def broadcast(
        self,
        session_id: str,
        kind: str,
        payload: Dict[str, Any],
        *,
        author: str,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> SessionEvent:
        """Append an event to the session log and notify subscribers."""

        metadata = await self._load_metadata(session_id)
        with profile("session_broadcast"):
            event = SessionEvent(
                identifier=uuid.uuid4().hex,
                kind=kind,
                payload=self._sanitize_payload(payload),
                author=author,
                timestamp=time.time(),
            )
            encrypted = False
            payload_data: Any = event.payload
            if metadata.share_key:
                encrypted = True
                payload_data = self._encryptor.encrypt_event(session_id, event.payload)
            await self._append_event(metadata, event, payload_data, encrypted)
            self._enqueue(session_id, event)
            self._append_transcript(metadata, event)
            await self._append_metrics(metadata, event, metrics)
            await self._record_analytics(metadata, event, metrics)
            if event.author in metadata.collaborators:
                metadata.collaborators[event.author]["last_seen"] = event.timestamp
                await self._write_metadata(metadata)
        return event

    async def subscribe(self, session_id: str) -> AsyncIterator[SessionEvent]:
        """Yield events streamed from the session log."""

        queue = self._queues.setdefault(session_id, asyncio.Queue())
        await self._ensure_poller(session_id)

        async def _iterator() -> AsyncIterator[SessionEvent]:
            while True:
                event = await queue.get()
                yield event

        return _iterator()

    async def sync_now(self, session_id: str) -> None:
        """Manually persist metadata and trigger remote sync when configured."""

        metadata = await self._load_metadata(session_id)
        await self._write_metadata(metadata)
        if self._sync_host and self._sync_port:
            await self._push_to_peer(metadata)

    # ------------------------------------------------------------------
    # Analytics helpers
    # ------------------------------------------------------------------
    async def analytics_snapshot(self, session_id: str) -> Dict[str, Any]:
        if not self._analytics:
            return {}
        return await self._analytics.session_summary(session_id)

    async def analytics_report(self, session_id: str) -> Dict[str, Any]:
        if not self._analytics:
            return {}
        return await self._analytics.generate_report(session_id)

    async def analytics_compare(self, first: str, second: str) -> Dict[str, Any]:
        if not self._analytics:
            return {}
        return await self._analytics.compare_sessions(first, second)

    async def analytics_insights(self, session_id: str) -> List[str]:
        if not self._analytics:
            return []
        return await self._analytics.insights(session_id)

    async def record_presence(self, session_id: str, identity: str) -> None:
        """Update the ``last_seen`` timestamp for ``identity``."""

        metadata = await self._load_metadata(session_id)
        if identity in metadata.collaborators:
            metadata.collaborators[identity]["last_seen"] = time.time()
            await self._write_metadata(metadata)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _load_metadata(self, session_id: str) -> SessionMetadata:
        path = self._root / session_id / "metadata.json"
        if not path.exists():
            raise FileNotFoundError(f"Session {session_id} missing")
        payload = json.loads(path.read_text())
        return SessionMetadata(
            session_id=session_id,
            title=payload.get("title", session_id),
            created_at=payload.get("created_at", 0.0),
            created_by=payload.get("created_by", "unknown"),
            share_key=payload.get("share_key"),
            collaborators=payload.get("collaborators", {}),
            path=path.parent,
        )

    async def _write_metadata(self, metadata: SessionMetadata, owner: Optional[str] = None) -> None:
        lock = self._locks.setdefault(metadata.session_id, asyncio.Lock())
        async with lock:
            payload = {
                "session_id": metadata.session_id,
                "title": metadata.title,
                "created_at": metadata.created_at,
                "created_by": owner or metadata.created_by,
                "share_key": metadata.share_key,
                "collaborators": metadata.collaborators,
            }
            (metadata.path / "metadata.json").write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )

    async def _append_event(
        self,
        metadata: SessionMetadata,
        event: SessionEvent,
        payload: Any,
        encrypted: bool,
    ) -> None:
        lock = self._locks.setdefault(metadata.session_id, asyncio.Lock())
        record = event.to_json(encrypted=encrypted, payload=payload)
        async with lock:
            path = metadata.path / "events.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(record + "\n")

    def _enqueue(self, session_id: str, event: SessionEvent) -> None:
        queue = self._queues.setdefault(session_id, asyncio.Queue())
        queue.put_nowait(event)

    def _append_transcript(self, metadata: SessionMetadata, event: SessionEvent) -> None:
        text = self._summarise_event(event)
        path = metadata.path / "transcript.md"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")

    async def _append_metrics(
        self, metadata: SessionMetadata, event: SessionEvent, metrics: Optional[Dict[str, Any]]
    ) -> None:
        payload = {
            "timestamp": event.timestamp,
            "kind": event.kind,
            "author": event.author,
            "metrics": metrics or {},
        }
        path = metadata.path / "metrics.jsonl"
        lock = self._locks.setdefault(metadata.session_id, asyncio.Lock())
        async with lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload) + "\n")

    async def _record_analytics(
        self, metadata: SessionMetadata, event: SessionEvent, metrics: Optional[Dict[str, Any]]
    ) -> None:
        if not self._analytics:
            return
        await self._analytics.record_session_event(
            metadata.session_id,
            event.kind,
            metrics=metrics or {},
            author=event.author,
        )

    async def _ensure_poller(self, session_id: str) -> None:
        if session_id in self._pollers:
            return
        task = asyncio.create_task(self._poll_session(session_id))
        self._pollers[session_id] = task

    async def _poll_session(self, session_id: str) -> None:
        path = self._root / session_id / "events.jsonl"
        position = self._positions.get(session_id, 0)
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        while True:
            await asyncio.sleep(self._poll_interval)
            if not path.exists():
                continue
            async with lock:
                with path.open("r", encoding="utf-8") as handle:
                    handle.seek(position)
                    lines = handle.readlines()
                    position = handle.tell()
            self._positions[session_id] = position
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload: Dict[str, Any]
                if record.get("encrypted"):
                    try:
                        payload = self._encryptor.decrypt_event(session_id, record["payload"])
                    except Exception:
                        logger.warning(
                            "failed to decrypt session payload", extra={"id": session_id}
                        )
                        continue
                else:
                    payload = record.get("payload", {})
                event = SessionEvent(
                    identifier=record.get("id", uuid.uuid4().hex),
                    kind=record.get("kind", "event"),
                    payload=payload,
                    author=record.get("author", "unknown"),
                    timestamp=record.get("timestamp", time.time()),
                )
                self._enqueue(session_id, event)

    async def _push_to_peer(self, metadata: SessionMetadata) -> None:
        if not self._sync_host or not self._sync_port:
            return
        try:
            reader, writer = await asyncio.open_connection(self._sync_host, self._sync_port)
        except Exception as exc:  # pragma: no cover - network optional
            logger.debug("sync peer unavailable", extra={"error": str(exc)})
            return
        payload = {
            "session_id": metadata.session_id,
            "metadata": metadata.collaborators,
            "timestamp": time.time(),
        }
        data = json.dumps(payload).encode("utf-8")
        writer.write(len(data).to_bytes(4, "big") + data)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    @staticmethod
    def _sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        sanitized: Dict[str, Any] = {}
        for key, value in payload.items():
            if key in {"diff", "raw", "secret"}:
                continue
            sanitized[key] = value
        return sanitized

    @staticmethod
    def _summarise_event(event: SessionEvent) -> str:
        summary = event.payload.get("summary") or event.payload.get("message") or event.kind
        return f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(event.timestamp))} | {event.kind} | {summary}"


__all__ = ["SessionManager", "SessionEvent", "SessionMetadata"]
