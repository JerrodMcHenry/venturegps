"""
Version identifiers for collectors, processors, verification methods and rules.

Format:  <name>.v<N>      e.g.  manual_upload.v1   byte_range_match.v2

  name  lowercase letter, then lowercase letters/digits/underscores, up to 64 chars
  N     a positive integer with no leading zero, up to 6 digits

They are plain strings so they store as-is and compare by equality. Ordering
is only meaningful within one name (compare version_number()); there is
deliberately no semantic-versioning machinery. Taxonomy and methodology
versions are NOT modelled here yet.
"""

import re
from typing import Annotated

from pydantic import AfterValidator

from app.v2.domain.errors import InvalidInputError

_VERSION_ID = re.compile(r"[a-z][a-z0-9_]{0,63}\.v[1-9][0-9]{0,5}")


def validate_version_id(value: object) -> str:
    if not isinstance(value, str) or _VERSION_ID.fullmatch(value) is None:
        raise InvalidInputError("invalid_version_id", "version id must look like name.v1")
    return value


VersionId = Annotated[str, AfterValidator(validate_version_id)]


def is_valid_version_id(value: object) -> bool:
    return isinstance(value, str) and _VERSION_ID.fullmatch(value) is not None


def make_version_id(name: str, number: int) -> str:
    if type(number) is not int:
        raise InvalidInputError("invalid_version_id", "version number must be an integer")
    return validate_version_id(f"{name}.v{number}")


def version_name(version_id: str) -> str:
    return validate_version_id(version_id).rsplit(".v", 1)[0]


def version_number(version_id: str) -> int:
    return int(validate_version_id(version_id).rsplit(".v", 1)[1])
