"""
Content vocabulary: the content hash type and media-type metadata.

Declared media type = what the source CLAIMED (untrusted, may be absent).
Sniffed media type  = what the BYTES look like (computed by
app.v2.observations.media, conservatively; UNKNOWN when unsure).
They are stored separately and never merged: a declared type can never
override what the bytes show.
"""

import re
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator

from app.v2.domain.errors import InvalidInputError

# ---- content hash: sha256 of the exact received bytes, lowercase hex

_CONTENT_HASH = re.compile(r"[0-9a-f]{64}")


def validate_content_hash(value: object) -> str:
    if not isinstance(value, str) or _CONTENT_HASH.fullmatch(value) is None:
        raise InvalidInputError("invalid_content_hash", "content hash must be 64 lowercase hex characters")
    return value


ContentHash = Annotated[str, AfterValidator(validate_content_hash)]


# ---- media types

class MediaType(str, Enum):
    """The formats Phase 1 can recognise. UNKNOWN is a first-class, valid value:
    'we could not confidently classify these bytes'."""

    TEXT_PLAIN = "text/plain"
    TEXT_HTML = "text/html"
    APPLICATION_JSON = "application/json"
    APPLICATION_PDF = "application/pdf"
    UNKNOWN = "unknown"  # not a valid MIME string, so it cannot collide with a declared type


class MediaAgreement(str, Enum):
    CONSISTENT = "consistent"    # declared and sniffed are the same known type
    CONFLICT = "conflict"        # both are known types from our vocabulary, and they differ
    UNVERIFIED = "unverified"    # we cannot compare: nothing declared, bytes unclassified,
                                 # or a declared type outside our vocabulary


MAX_DECLARED_MEDIA_TYPE_LENGTH = 255
_ESSENCE = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_KNOWN = frozenset(m.value for m in MediaType if m is not MediaType.UNKNOWN)


def normalize_declared_media_type(raw: str | None) -> str | None:
    """A declared Content-Type header value -> its lowercase `type/subtype`
    (parameters such as charset are dropped). None or blank -> None (not declared).
    Malformed -> InvalidInputError. Never guesses a type."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise InvalidInputError("invalid_media_type", "declared media type must be a string")
    if len(raw) > MAX_DECLARED_MEDIA_TYPE_LENGTH or _CONTROL.search(raw) or not raw.isascii():
        raise InvalidInputError("invalid_media_type", "declared media type is malformed")
    essence = raw.split(";", 1)[0].strip().lower()
    if not essence:
        return None
    if _ESSENCE.fullmatch(essence) is None:
        raise InvalidInputError("invalid_media_type", "declared media type is malformed")
    return essence


def assess_media_agreement(declared: str | None, detected: MediaType) -> MediaAgreement:
    """`declared` must already be normalized (see normalize_declared_media_type)."""
    if declared is None or detected is MediaType.UNKNOWN or declared not in _KNOWN:
        return MediaAgreement.UNVERIFIED
    return MediaAgreement.CONSISTENT if declared == detected.value else MediaAgreement.CONFLICT
