"""
Content hashing: sha256 over the EXACT bytes received, as lowercase hex.

No normalization, decoding, newline handling or re-encoding of any kind: two
payloads hash equal iff they are byte-for-byte identical. Text must be encoded
by the caller, whose bytes are what get hashed (a str is refused, not silently
encoded, so there is only one meaning of "the hash of this content").
"""

import hashlib

from app.v2.domain.errors import InvalidInputError


def compute_content_hash(data: bytes | bytearray | memoryview) -> str:
    if isinstance(data, (bytes, bytearray, memoryview)):
        return hashlib.sha256(data).hexdigest()
    raise InvalidInputError("content_must_be_bytes", "content must be bytes; encode text explicitly before hashing")
