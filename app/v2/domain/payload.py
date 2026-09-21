"""
Raw evidence payloads: the exact bytes a source exposed.

Content-addressed: the identity of a payload is the sha256 of its bytes
(app.v2.observations.hashing computes and verifies it; the domain holds only
the vocabulary and the size policy). Two payloads are "the same" iff their
bytes are identical. That is NOT the same question as "is this the same
Observation": an Observation is a Source exposing a payload.

Phase 1 stores payloads inline only. The limit is defined here, once.
Oversized evidence is rejected, never truncated.
"""

from enum import Enum

from pydantic import field_validator

from app.v2.domain.base import DomainModel
from app.v2.domain.content import ContentHash
from app.v2.domain.errors import UnsupportedInputError

MAX_INLINE_PAYLOAD_BYTES = 1024 * 1024  # 1 MiB


class StorageKind(str, Enum):
    INLINE = "inline"  # external / object storage is a later, separate decision


class RawPayload(DomainModel):
    content_hash: ContentHash
    payload_bytes: bytes
    storage_kind: StorageKind

    @field_validator("payload_bytes")
    @classmethod
    def _within_the_inline_limit(cls, value: bytes) -> bytes:
        if len(value) > MAX_INLINE_PAYLOAD_BYTES:
            raise UnsupportedInputError("payload_too_large", "payload exceeds the inline size limit")
        return value

    @property
    def size_bytes(self) -> int:
        return len(self.payload_bytes)
