"""
The typed ingestion command and result.

The command holds only what is known at the collection boundary. It has no
content_hash, sniffed_media_type, recorded_time, processing status, AI output
or company identity: the service computes deterministic facts itself, and the
command model forbids extra fields, so a caller cannot supply them.
"""

from dataclasses import dataclass

from pydantic import Field

from app.v2.domain.base import DomainModel
from app.v2.domain.observation import CollectorId, ObservationType, SourceRecordIdentifier, StoredObservation
from app.v2.domain.payload import RawPayload
from app.v2.domain.sighting import AcquisitionKey, StoredSighting
from app.v2.domain.source import SourceKey
from app.v2.domain.time import EventTime, UtcDatetime
from app.v2.domain.versions import VersionId


class IngestionCommand(DomainModel):
    source_key: SourceKey
    source_record_identifier: SourceRecordIdentifier | None = None  # None = the source gave none
    observation_type: ObservationType
    event_time: EventTime | None = None                             # None = unknown
    observed_time: UtcDatetime                                      # when THIS acquisition happened
    collection_version: VersionId
    collector_id: CollectorId
    declared_media_type: str | None = None                          # the raw Content-Type claim; untrusted
    payload_bytes: bytes = Field(repr=False)                        # never echoed in logs/tracebacks
    acquisition_key: AcquisitionKey                                 # chosen by the collector; makes replays idempotent


@dataclass(frozen=True)
class IngestionResult:
    payload: RawPayload
    observation: StoredObservation
    sighting: StoredSighting
    payload_created: bool
    observation_created: bool
    sighting_created: bool
    # Static field names where an EXISTING record differs from what this command carried
    # (e.g. "observation.observation_type", "sighting.observed_time"). The existing record is
    # never modified; this only reports the difference.
    differences: tuple[str, ...] = ()

    @property
    def is_replay(self) -> bool:
        """True when this exact acquisition had already been ingested (no new sighting)."""
        return not self.sighting_created
