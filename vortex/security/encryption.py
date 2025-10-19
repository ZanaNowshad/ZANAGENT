"""Credential encryption helpers."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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


__all__ = ["CredentialStore", "EncryptionKey"]
