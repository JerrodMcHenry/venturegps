"""
Source vocabulary. A Source is WHERE information comes from. Its identity
(source_key) is assigned by VentureGPS configuration -- it is never inferred
from payload text. The URL is data only: it is validated here and never
fetched, and fetching (later) applies its own SSRF controls.
"""

import re
from enum import Enum
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator

from app.v2.domain.base import DomainModel
from app.v2.domain.errors import InvalidInputError, UnsupportedInputError


class SourceType(str, Enum):
    GOVERNMENT_REGULATORY = "government_regulatory"
    FIRST_PARTY_COMPANY = "first_party_company"
    INVESTOR = "investor"
    JOB_PLATFORM = "job_platform"
    RESEARCH = "research"
    PATENT = "patent"
    OPEN_SOURCE = "open_source"
    MEDIA_NEWS = "media_news"
    OTHER = "other"


class CollectionMethod(str, Enum):
    MANUAL_UPLOAD = "manual_upload"
    HTTP_FETCH = "http_fetch"
    API = "api"
    FEED = "feed"
    BULK_FILE = "bulk_file"


# ---- source key: stable, configuration-assigned slug (2-64 chars)

_SOURCE_KEY = re.compile(r"[a-z][a-z0-9_]{1,63}")


def validate_source_key(value: object) -> str:
    if not isinstance(value, str) or _SOURCE_KEY.fullmatch(value) is None:
        raise InvalidInputError("invalid_source_key", "source key must be a lowercase slug of 2-64 characters")
    return value


SourceKey = Annotated[str, AfterValidator(validate_source_key)]


# ---- display name

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_SOURCE_NAME_LENGTH = 200


def validate_source_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_SOURCE_NAME_LENGTH
        or value != value.strip()
        or _CONTROL.search(value)
    ):
        raise InvalidInputError("invalid_source_name", "source name must be 1-200 printable characters without surrounding whitespace")
    return value


SourceName = Annotated[str, AfterValidator(validate_source_name)]


# ---- source URL (data only, never fetched)

MAX_SOURCE_URL_LENGTH = 2048
MAX_HOSTNAME_LENGTH = 253
ALLOWED_SOURCE_URL_SCHEMES = ("https", "http")


def validate_source_url(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_SOURCE_URL_LENGTH:
        raise InvalidInputError("invalid_source_url", "source URL is missing or too long")
    if not value.isascii() or "\\" in value or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise InvalidInputError("invalid_source_url", "source URL must be ASCII without whitespace or control characters")
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
        parts.port  # noqa: B018 -- raises ValueError for an invalid port
    except ValueError:
        raise InvalidInputError("invalid_source_url", "source URL is malformed") from None
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise InvalidInputError("url_credentials", "source URL must not contain credentials")
    if parts.scheme.lower() not in ALLOWED_SOURCE_URL_SCHEMES:
        raise UnsupportedInputError("unsupported_url_scheme", "source URL scheme must be http or https")
    if not hostname or len(hostname) > MAX_HOSTNAME_LENGTH:
        raise InvalidInputError("invalid_source_url", "source URL must have a valid host")
    return value


SourceUrl = Annotated[str, AfterValidator(validate_source_url)]


class Source(DomainModel):
    """An immutable description of a source. `is_active` is required (no implied
    default); later persistence layers timestamps and ids on top of this."""

    source_key: SourceKey
    name: SourceName
    source_type: SourceType
    collection_method: CollectionMethod
    url: SourceUrl | None = None  # None: this source has no URL (unknown/not applicable)
    is_active: bool
