"""
Content hashing: sha256 over the EXACT bytes received, as lowercase hex.

No normalization, decoding, newline handling or re-encoding of any kind: two
payloads hash equal iff they are byte-for-byte identical. Text must be encoded
by the caller, whose bytes are what get hashed (a str is refused, not silently
encoded, so there is only one meaning of "the hash of this content").
"""

import hashlib

from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.payload import RawPayload, StorageKind


def compute_content_hash(data: bytes | bytearray | memoryview) -> str:
    if isinstance(data, (bytes, bytearray, memoryview)):
        return hashlib.sha256(data).hexdigest()
    raise InvalidInputError("content_must_be_bytes", "content must be bytes; encode text explicitly before hashing")


def build_raw_payload(data: bytes | bytearray | memoryview) -> RawPayload:
    """The RawPayload for exactly these bytes: hash computed here, never supplied by a caller.
    Oversized content raises UnsupportedInputError (nothing is truncated)."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise InvalidInputError("content_must_be_bytes", "content must be bytes; encode text explicitly before storing")
    raw = bytes(data)
    return RawPayload(content_hash=compute_content_hash(raw), payload_bytes=raw, storage_kind=StorageKind.INLINE)


def verify_raw_payload(payload: RawPayload) -> None:
    """Raise InvariantViolationError unless sha256(payload_bytes) == content_hash.
    Corrupted evidence fails loudly; nothing here (or anywhere) repairs it."""
    if compute_content_hash(payload.payload_bytes) != payload.content_hash:
        raise InvariantViolationError("payload_hash_mismatch", "stored payload bytes do not match their content hash")
