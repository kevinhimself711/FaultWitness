"""Versioned authenticated checkpoint serialization; pickle is deliberately unsupported."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True, slots=True)
class EncryptedCheckpoint:
    key_id: str
    nonce: bytes
    ciphertext: bytes
    format_version: int = 1


class CheckpointCipher:
    def __init__(self, key_id: str, key: bytes) -> None:
        if len(key) not in {16, 24, 32}:
            raise ValueError("AES-GCM key must contain 16, 24, or 32 bytes")
        self.key_id = key_id
        self._cipher = AESGCM(key)

    def seal(self, value: dict[str, Any], *, tenant_id: str, task_id: str) -> EncryptedCheckpoint:
        body = json.dumps(
            {"format": "faultwitness-checkpoint", "version": 1, "state": value},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        nonce = os.urandom(12)
        aad = f"{tenant_id}:{task_id}:v1".encode()
        return EncryptedCheckpoint(self.key_id, nonce, self._cipher.encrypt(nonce, body, aad))

    def open(
        self, checkpoint: EncryptedCheckpoint, *, tenant_id: str, task_id: str
    ) -> dict[str, Any]:
        if checkpoint.format_version != 1 or checkpoint.key_id != self.key_id:
            raise ValueError("unknown checkpoint format or key")
        aad = f"{tenant_id}:{task_id}:v1".encode()
        document = json.loads(self._cipher.decrypt(checkpoint.nonce, checkpoint.ciphertext, aad))
        if document.get("format") != "faultwitness-checkpoint" or document.get("version") != 1:
            raise ValueError("unknown checkpoint payload")
        state = document.get("state")
        if not isinstance(state, dict):
            raise ValueError("checkpoint state must be an object")
        return state
