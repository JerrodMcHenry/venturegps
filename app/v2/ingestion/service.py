"""
ingest_evidence(db, command): the deterministic evidence-ingestion workflow.

    1  resolve the Source                     (missing -> NotFoundError)
    2  require it to be active                (inactive -> SourceInactiveError)
    3  validate size + hash exact bytes       (> 1 MiB -> UnsupportedInputError; nothing truncated)
    4  sniff media type from the bytes
    5  normalize the declared media type      (malformed -> InvalidInputError)
    6  build + validate the Observation       (agreement/mismatch is derived, and never grounds for rejection)
    7  store or reuse the RawPayload
    8  store or reuse the Observation         (identity: source, record identifier incl. none, content hash)
    9  store or reuse the Sighting            (identity: observation + acquisition_key)

Atomic: everything runs in ONE transaction (or, when handed a Connection, in a
SAVEPOINT inside the caller's transaction), so a failure leaves no partial
payload, observation or sighting. PostgreSQL constraints are the final
authority under concurrency; the application logic never relies on check-then-insert.

Repeat acquisition of identical evidence reuses the payload and the Observation
and adds a Sighting. The existing Observation is never mutated: its observed_time
stays the FIRST time it was observed, and a duplicate command's differing
non-identity metadata is reported in `differences`, not stored. Sightings may
arrive out of order; the policy is to record them as-is (a sighting may be earlier
than the Observation's observed_time), preserving history rather than rewriting it.

Only the ACTIVE-source rule is policy here; it is not a constraint on the
evidence tables, so deactivating a Source never touches existing evidence.

No network, no AI, no environment access.
"""

from contextlib import contextmanager

from sqlalchemy.engine import Connection, Engine

from app.v2.domain.content import normalize_declared_media_type
from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.observation import Observation
from app.v2.domain.sighting import Sighting
from app.v2.ingestion.errors import SourceInactiveError
from app.v2.ingestion.models import IngestionCommand, IngestionResult
from app.v2.observations.hashing import build_raw_payload
from app.v2.observations.media import sniff_media_type
from app.v2.repositories.errors import NotFoundError
from app.v2.repositories.observations import store_observation
from app.v2.repositories.raw_payloads import store_raw_payload
from app.v2.repositories.sightings import store_sighting
from app.v2.repositories.sources import get_source_by_key

_OBSERVATION_FIELDS_REPORTED = (
    "observation_type", "event_time", "collection_version", "collector_id", "declared_media_type", "sniffed_media_type",
)
_SIGHTING_FIELDS_REPORTED = ("observed_time", "collector_id", "collection_version")


@contextmanager
def _atomic(db: Engine | Connection):
    if isinstance(db, Engine):
        with db.begin() as connection:
            yield connection
    else:
        with db.begin_nested():  # a SAVEPOINT: a failure undoes only this ingestion
            yield db


def ingest_evidence(db: Engine | Connection, command: IngestionCommand) -> IngestionResult:
    if not isinstance(command, IngestionCommand):
        raise InvalidInputError("not_an_ingestion_command", "ingest_evidence requires an IngestionCommand")

    with _atomic(db) as connection:
        source = get_source_by_key(connection, command.source_key, lock_shared=True)
        if source is None:
            raise NotFoundError("source_not_found", "no source is registered under that key")
        if not source.source.is_active:
            raise SourceInactiveError("source_inactive", "the source is deactivated, so new evidence is not ingested")

        payload = build_raw_payload(command.payload_bytes)
        observation = Observation(
            source_key=command.source_key,
            source_record_identifier=command.source_record_identifier,
            observation_type=command.observation_type,
            event_time=command.event_time,
            observed_time=command.observed_time,
            collection_version=command.collection_version,
            collector_id=command.collector_id,
            content_hash=payload.content_hash,
            declared_media_type=normalize_declared_media_type(command.declared_media_type),
            sniffed_media_type=sniff_media_type(payload.payload_bytes),
        )
        sighting = Sighting(
            observed_time=command.observed_time,
            collector_id=command.collector_id,
            collection_version=command.collection_version,
            acquisition_key=command.acquisition_key,
        )

        payload_result = store_raw_payload(connection, payload.payload_bytes)
        observation_result = store_observation(connection, observation)
        sighting_result = store_sighting(connection, observation_result.stored.id, sighting)

        if observation_result.created and observation_result.stored.observation.observed_time != sighting.observed_time:
            raise InvariantViolationError(
                "first_sighting_mismatch", "a new observation's observed_time must equal its first sighting's"
            )

        differences: list[str] = []
        if not observation_result.created:
            existing = observation_result.stored.observation
            differences += [f"observation.{f}" for f in _OBSERVATION_FIELDS_REPORTED
                            if getattr(existing, f) != getattr(observation, f)]
        if not sighting_result.created:
            existing_sighting = sighting_result.stored.sighting
            differences += [f"sighting.{f}" for f in _SIGHTING_FIELDS_REPORTED
                            if getattr(existing_sighting, f) != getattr(sighting, f)]

        return IngestionResult(
            payload=payload_result.payload,
            observation=observation_result.stored,
            sighting=sighting_result.stored,
            payload_created=payload_result.created,
            observation_created=observation_result.created,
            sighting_created=sighting_result.created,
            differences=tuple(differences),
        )
