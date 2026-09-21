"""
Observation: an immutable representation of information VentureGPS acquired
from a Source at a particular time.

Deliberately NOT here: processing status (attempts are separate records --
see processing.py), AI fields, database ids, recorded_time (assigned by the
database), or the raw bytes (referenced by content_hash).

event_time and observed_time are independent: no ordering between them is
enforced, and event_time may be None (unknown).
"""

import re
from typing import Annotated

from pydantic import AfterValidator, Field, field_validator

from app.v2.domain.base import DomainModel
from app.v2.domain.content import (
    ContentHash,
    MediaAgreement,
    MediaType,
    assess_media_agreement,
    normalize_declared_media_type,
)
from app.v2.domain.errors import InvalidInputError
from app.v2.domain.source import SourceKey
from app.v2.domain.time import EventTime, UtcDatetime
from app.v2.domain.versions import VersionId

_OBSERVATION_TYPE = re.compile(r"[a-z][a-z0-9_]{1,63}")
_COLLECTOR_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_SOURCE_RECORD_IDENTIFIER_LENGTH = 512


def validate_observation_type(value: object) -> str:
    if not isinstance(value, str) or _OBSERVATION_TYPE.fullmatch(value) is None:
        raise InvalidInputError("invalid_observation_type", "observation type must be a lowercase slug of 2-64 characters")
    return value


def validate_collector_id(value: object) -> str:
    if not isinstance(value, str) or _COLLECTOR_ID.fullmatch(value) is None:
        raise InvalidInputError("invalid_collector_id", "collector id must be 1-128 characters from A-Za-z0-9_.:@/-")
    return value


def validate_source_record_identifier(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_SOURCE_RECORD_IDENTIFIER_LENGTH
        or _CONTROL.search(value)
    ):
        raise InvalidInputError("invalid_source_record_identifier", "source record identifier must be 1-512 characters without control characters")
    return value


ObservationType = Annotated[str, AfterValidator(validate_observation_type)]
CollectorId = Annotated[str, AfterValidator(validate_collector_id)]
SourceRecordIdentifier = Annotated[str, AfterValidator(validate_source_record_identifier)]


class Observation(DomainModel):
    source_key: SourceKey
    source_record_identifier: SourceRecordIdentifier | None = None  # supplied by the source, opaque, untrusted
    observation_type: ObservationType
    event_time: EventTime | None = None                             # None = unknown
    observed_time: UtcDatetime                                      # required
    collection_version: VersionId
    collector_id: CollectorId
    content_hash: ContentHash                                       # sha256 of the exact received bytes
    declared_media_type: str | None = None                          # normalized essence; None = not declared
    sniffed_media_type: MediaType                                   # UNKNOWN when not confidently classified

    @field_validator("declared_media_type")
    @classmethod
    def _declared_media_type_is_normalized(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # Strict: an immutable record does not silently rewrite what it was given.
        # Callers normalize explicitly with normalize_declared_media_type().
        if normalize_declared_media_type(value) != value:
            raise InvalidInputError("media_type_not_normalized", "declared media type must be a normalized type/subtype")
        return value

    @property
    def media_agreement(self) -> MediaAgreement:
        return assess_media_agreement(self.declared_media_type, self.sniffed_media_type)

    @property
    def media_type_mismatch(self) -> bool:
        return self.media_agreement is MediaAgreement.CONFLICT

    @property
    def dedup_key(self) -> tuple[str, str | None, str]:
        """Two observations are the same evidence state iff this is equal."""
        return (self.source_key, self.source_record_identifier, self.content_hash)


class StoredObservation(DomainModel):
    """An Observation as persisted: the unchanged Observation plus what only
    persistence knows. Evidence is immutable, so there is no updated_time.

    id             opaque persistence identifier
    source_id      opaque identifier of the persisted Source (observation.source_key names it)
    recorded_time  when VentureGPS persisted it: assigned by the database, never by the caller,
                   and independent of event_time and observed_time
    """

    id: int = Field(gt=0)
    source_id: int = Field(gt=0)
    observation: Observation
    recorded_time: UtcDatetime
