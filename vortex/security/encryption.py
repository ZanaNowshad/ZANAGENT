"""Credential encryption helpers."""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from vortex.utils.errors import SecurityError

try:  # pragma: no cover - optional dependency may be missing in CI
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover
    Fernet = None  # type: ignore


@dataclass
class EncryptionKey:
    value: bytes

    def as_token(self) -> str:
        return base64.urlsafe_b64encode(self.value).decode("utf-8")


class CredentialStore:
    """Persist encrypted credentials on disk."""

    def __init__(self, directory: Path, key: Optional[EncryptionKey] = None) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.key = key or self._load_or_create_key()
        self._fernet = Fernet(self.key.value) if Fernet else None

    def _load_or_create_key(self) -> EncryptionKey:
        key_path = self.directory / "key"
        if key_path.exists():
            return EncryptionKey(value=key_path.read_bytes())
        if Fernet:
            key_value = Fernet.generate_key()
        else:
            key_value = base64.urlsafe_b64encode(os.urandom(32))
        key_path.write_bytes(key_value)
        return EncryptionKey(value=key_value)

    def save(self, name: str, secret: str) -> None:
        path = self.directory / f"{name}.secret"
        if self._fernet:
            token = self._fernet.encrypt(secret.encode("utf-8"))
        else:  # pragma: no cover - fallback path
            token = base64.urlsafe_b64encode(secret.encode("utf-8"))
        path.write_bytes(token)

    def load(self, name: str) -> str:
        path = self.directory / f"{name}.secret"
        if not path.exists():
            raise SecurityError(f"Secret {name} missing")
        data = path.read_bytes()
        if self._fernet:
            return self._fernet.decrypt(data).decode("utf-8")
        return base64.urlsafe_b64decode(data).decode("utf-8")

class DataEncryptor:
    """Encrypt arbitrary values for database persistence."""

    def __init__(self, store: CredentialStore) -> None:
        self._store = store
        self._fernet = store._fernet

    def encrypt_value(self, value: str) -> str:
        if self._fernet is None:
            token = base64.urlsafe_b64encode(value.encode("utf-8"))
        else:
            token = self._fernet.encrypt(value.encode("utf-8"))
        return token.decode("utf-8")

    def decrypt_value(self, value: str) -> str:
        data = value.encode("utf-8")
        if self._fernet is None:
            decoded = base64.urlsafe_b64decode(data)
        else:
            decoded = self._fernet.decrypt(data)
        return decoded.decode("utf-8")


class SessionEncryptor:
    """Encrypt per-session payloads and generate share tokens."""

    def __init__(self, store: CredentialStore) -> None:
        self._store = store
        self._fernet = store._fernet
        self._cache: Dict[str, bytes] = {}

    def ensure_session_key(self, session_id: str) -> str:
        """Load or create the symmetric key for ``session_id``."""

        key_path = self._store.directory / f"session-{session_id}.key"
        if key_path.exists():
            token = key_path.read_bytes()
            key_bytes = self._decrypt_bytes(token)
        else:
            key_bytes = self._generate_key()
            token = self._encrypt_bytes(key_bytes)
            key_path.write_bytes(token)
        self._cache[session_id] = key_bytes
        return base64.urlsafe_b64encode(key_bytes).decode("utf-8")

    def encrypt_event(self, session_id: str, payload: dict) -> str:
        """Encrypt a JSON payload for persistence or sharing."""

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        cipher = self._session_cipher(session_id)
        if cipher:
            token = cipher.encrypt(data)
        else:  # pragma: no cover - fallback when cryptography missing
            token = base64.urlsafe_b64encode(data)
        return token.decode("utf-8")

    def decrypt_event(self, session_id: str, token: str) -> dict:
        data = token.encode("utf-8")
        cipher = self._session_cipher(session_id)
        if cipher:
            decoded = cipher.decrypt(data)
        else:  # pragma: no cover - fallback path
            decoded = base64.urlsafe_b64decode(data)
        return json.loads(decoded.decode("utf-8"))

    def generate_share_token(self, session_id: str, *, role: str, read_only: bool) -> str:
        """Return a signed token describing share permissions."""

        key = self.ensure_session_key(session_id)
        payload = {
            "session": session_id,
            "role": role,
            "read_only": read_only,
            "key": key,
        }
        raw = json.dumps(payload).encode("utf-8")
        token = base64.urlsafe_b64encode(self._encrypt_bytes(raw))
        return token.decode("utf-8")

    def decode_share_token(self, token: str) -> Tuple[str, str, bool]:
        """Decode a previously generated share token."""

        raw = base64.urlsafe_b64decode(token.encode("utf-8"))
        payload = json.loads(self._decrypt_bytes(raw).decode("utf-8"))
        session_id = payload["session"]
        key = payload["key"].encode("utf-8")
        self._cache[session_id] = base64.urlsafe_b64decode(key)
        return session_id, payload.get("role", "collaborator"), bool(payload.get("read_only", False))

    def _session_cipher(self, session_id: str):
        key = self._cache.get(session_id)
        if key is None:
            try:
                key_b64 = self.ensure_session_key(session_id)
            except SecurityError:
                return None
            key = base64.urlsafe_b64decode(key_b64.encode("utf-8"))
        if Fernet is None:
            return None
        return Fernet(base64.urlsafe_b64encode(key))

    def _generate_key(self) -> bytes:
        if Fernet:
            return base64.urlsafe_b64decode(Fernet.generate_key())
        return os.urandom(32)

    def _encrypt_bytes(self, payload: bytes) -> bytes:
        if self._fernet:
            return self._fernet.encrypt(payload)
        return base64.urlsafe_b64encode(payload)

    def _decrypt_bytes(self, payload: bytes) -> bytes:
        if self._fernet:
            return self._fernet.decrypt(payload)
        return base64.urlsafe_b64decode(payload)


class SecretBox:
    """Lightweight symmetric encryption helper.

    The helper is purposely tiny so it can be used by subsystems that need
    ephemeral tokens without wiring the heavier :class:`CredentialStore` flows.
    Keys are generated using ``os.urandom`` when the ``cryptography`` package is
    not available.
    """

    def __init__(self, key: Optional[bytes] = None) -> None:
        if key is None:
            key = self.generate_key()
        self._key = key
        self._fernet = Fernet(key) if Fernet else None

    @staticmethod
    def generate_key() -> bytes:
        if Fernet:
            return Fernet.generate_key()
        return base64.urlsafe_b64encode(os.urandom(32))

    def encrypt(self, payload: bytes) -> bytes:
        if self._fernet:
            return self._fernet.encrypt(payload)
        return base64.urlsafe_b64encode(payload)

    def decrypt(self, payload: bytes) -> bytes:
        if self._fernet:
            return self._fernet.decrypt(payload)
        return base64.urlsafe_b64decode(payload)

    def token(self) -> str:
        return self._key.decode("utf-8")


class NetworkEncryptor:
    """Encrypt payloads shared across the agent network."""

    def __init__(
        self,
        store: Optional[CredentialStore] = None,
        *,
        name: str = "network",
        key: Optional[bytes] = None,
    ) -> None:
        self._store = store
        self._name = name
        if key is not None:
            token = base64.urlsafe_b64encode(key)
        elif store is not None:
            try:
                token = store.load(name).encode("utf-8")
            except SecurityError:
                token = self._generate_key()
                store.save(name, token.decode("utf-8"))
        else:
            token = self._generate_key()
        self._token = token
        self._fernet = Fernet(token) if Fernet else None

    @staticmethod
    def _generate_key() -> bytes:
        if Fernet:
            return Fernet.generate_key()
        return base64.urlsafe_b64encode(os.urandom(32))

    def encrypt(self, payload: bytes) -> bytes:
        if self._fernet is None:
            return base64.urlsafe_b64encode(payload)
        return self._fernet.encrypt(payload)

    def decrypt(self, payload: bytes) -> bytes:
        if self._fernet is None:
            return base64.urlsafe_b64decode(payload)
        return self._fernet.decrypt(payload)

    def export_token(self) -> str:
        return self._token.decode("utf-8")


__all__ = [
    "CredentialStore",
    "EncryptionKey",
    "DataEncryptor",
    "SessionEncryptor",
    "NetworkEncryptor",
    "SecretBox",
]
