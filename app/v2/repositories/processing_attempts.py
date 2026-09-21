"""
Processing-attempt persistence: durable operational history for immutable
Observations. Nothing here processes anything, and nothing here writes to
evidence (Source, RawPayload, Observation, ObservationSighting).

    start_processing(db, observation_id, processor_id, processor_version, lease_seconds=)
    renew_lease(db, attempt_id, lease_seconds=)
    mark_processed(db, attempt_id)
    mark_failed(db, attempt_id, reason_code, detail_code=None)
    mark_quarantined(db, attempt_id, reason_code, detail_code=None)
    fail_expired_attempt(db, attempt_id, as_of=None)
    get_processing_attempt(db, attempt_id)
    list_processing_attempts(db, observation_id, processor_id=None)
    get_latest_attempt(db, observation_id, processor_id)
    list_unprocessed_observation_ids(db, processor_id, limit=100)

Attempt numbers are linear per (observation, processor_id), whatever the
processor_version. start_processing serialises starts for an observation by
taking a row lock on the Observation (FOR NO KEY UPDATE: a lock, never a
write), then computes latest + 1. That is convenience: the database constraints
stay the final authority (UNIQUE (observation, processor, attempt_number) and
at most one PROCESSING attempt per observation + processor), and a violation
that gets past the lock is reported as ConflictError, never a duplicate row.

Lifecycle: PROCESSING -> PROCESSED | FAILED | QUARANTINED, once. Terminal
attempts are immutable; a retry is always a NEW attempt. start_processing
applies domain.processing.check_may_start_attempt: FAILED may be retried,
PROCESSED/QUARANTINED only by a LATER processor_version, and an active attempt
is a ConflictError. Timing is the database's (started_at, finished_at, lease
arithmetic); callers choose only a lease DURATION.

An expired lease is NOT a state change: the attempt stays PROCESSING until
fail_expired_attempt marks it FAILED (reason lease_expired). A lease may be
renewed while the attempt is PROCESSING, expired or not, and never shortened.
`as_of` exists so tests and replays can supply the clock; the default is the
database clock, which is what workers should use.
"""

from datetime import datetime

from sqlalchemy import func, insert, literal, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.v2.db.tables import observation_table as o
from app.v2.db.tables import processing_attempt_table as t
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError
from app.v2.domain.processing import (
    ProcessingStatus,
    assert_transition,
    check_may_start_attempt,
    next_attempt_number_for,
)
from app.v2.domain.processing_attempt import (
    DEFAULT_LEASE_SECONDS,
    LEASE_EXPIRED_REASON,
    StoredProcessingAttempt,
    validate_detail_code,
    validate_lease_seconds,
    validate_processor_id,
    validate_reason_code,
)
from app.v2.domain.time import ensure_utc
from app.v2.domain.versions import validate_version_id, version_name
from app.v2.repositories._db import connection as _connection
from app.v2.repositories._db import constraint_of, integrity_error_to_domain
from app.v2.repositories.errors import ConflictError, NotFoundError

MAX_LIST_LIMIT = 1000


def _positive_id(value: object, what: str) -> None:
    if type(value) is not int or value < 1:
        raise InvalidInputError(f"invalid_{what}", f"{what.replace('_', ' ')} must be a positive integer")


def _to_stored(row) -> StoredProcessingAttempt:
    m = row._mapping
    try:
        return StoredProcessingAttempt(
            id=m["id"], observation_id=m["observation_id"], processor_id=m["processor_id"],
            processor_version=m["processor_version"], attempt_number=m["attempt_number"],
            status=ProcessingStatus(m["status"]), started_at=m["started_at"], finished_at=m["finished_at"],
            lease_expires_at=m["lease_expires_at"], reason_code=m["reason_code"], detail_code=m["detail_code"],
        )
    except (DomainError, ValueError):
        raise InvariantViolationError("stored_attempt_invalid", "a stored processing attempt does not satisfy the domain model") from None


def _lease_expression(lease_seconds: int):
    return func.clock_timestamp() + func.make_interval(0, 0, 0, 0, 0, 0, literal(float(lease_seconds)))


# ---------------------------------------------------------------- start

def start_processing(
    db: Engine | Connection,
    observation_id: int,
    processor_id: str,
    processor_version: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> StoredProcessingAttempt:
    _positive_id(observation_id, "observation_id")
    validate_processor_id(processor_id)
    validate_version_id(processor_version)
    if version_name(processor_version) != processor_id:
        raise InvalidInputError("processor_version_mismatch", "processor version must carry the processor id as its name")
    validate_lease_seconds(lease_seconds)

    with _connection(db) as connection:
        locked = connection.execute(select(o.c.id).where(o.c.id == observation_id).with_for_update(key_share=True)).scalar()
        if locked is None:
            raise NotFoundError("observation_not_found", "no observation exists with that id")

        latest = connection.execute(
            select(t.c.attempt_number, t.c.status, t.c.processor_version)
            .where(t.c.observation_id == observation_id, t.c.processor_id == processor_id)
            .order_by(t.c.attempt_number.desc()).limit(1)
        ).one_or_none()
        try:
            check_may_start_attempt(
                None if latest is None else ProcessingStatus(latest.status),
                None if latest is None else latest.processor_version,
                processor_version,
            )
        except InvariantViolationError as exc:
            if exc.code == "attempt_already_active":
                raise ConflictError("attempt_already_active", "an attempt for this observation and processor is already processing") from None
            raise

        try:
            row = connection.execute(
                insert(t).values(
                    observation_id=observation_id, processor_id=processor_id, processor_version=processor_version,
                    attempt_number=next_attempt_number_for(None if latest is None else latest.attempt_number),
                    status=ProcessingStatus.PROCESSING.value, lease_expires_at=_lease_expression(lease_seconds),
                    # started_at is deliberately absent: the database assigns it.
                ).returning(*t.c)
            ).one()
        except IntegrityError as exc:  # only reachable if something bypassed the row lock
            constraint = constraint_of(exc)
            if constraint == "uq_processing_attempt_one_active":
                raise ConflictError("attempt_already_active", "an attempt for this observation and processor is already processing") from None
            if constraint == "uq_processing_attempt_number":
                raise ConflictError("attempt_number_conflict", "another attempt claimed that attempt number") from None
            raise integrity_error_to_domain(exc) from None
        return _to_stored(row)


# ---------------------------------------------------------------- lifecycle

def _explain_unchanged(connection: Connection, attempt_id: int, target: ProcessingStatus) -> None:
    """The guarded UPDATE changed nothing: say exactly why."""
    row = connection.execute(select(t.c.status).where(t.c.id == attempt_id)).one_or_none()
    if row is None:
        raise NotFoundError("attempt_not_found", "no processing attempt exists with that id")
    assert_transition(ProcessingStatus(row.status), target)  # a terminal attempt: raises illegal_transition
    raise InvariantViolationError("attempt_not_changed", "the attempt could not be changed")


def _update_processing(db, attempt_id: int, values: dict, target: ProcessingStatus, *, extra_where=None,
                       unchanged_error: DomainError | None = None) -> StoredProcessingAttempt:
    _positive_id(attempt_id, "attempt_id")
    with _connection(db) as connection:
        try:
            statement = update(t).where(t.c.id == attempt_id, t.c.status == ProcessingStatus.PROCESSING.value)
            if extra_where is not None:
                statement = statement.where(extra_where)
            row = connection.execute(statement.values(**values).returning(*t.c)).one_or_none()
        except IntegrityError as exc:
            raise integrity_error_to_domain(exc) from None
        if row is None:
            if unchanged_error is not None:
                exists = connection.execute(select(t.c.status).where(t.c.id == attempt_id)).one_or_none()
                if exists is not None and exists.status == ProcessingStatus.PROCESSING.value:
                    raise unchanged_error  # processing, but the extra condition (lease expiry) does not hold
            _explain_unchanged(connection, attempt_id, target)
        return _to_stored(row)


def renew_lease(db: Engine | Connection, attempt_id: int, *, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> StoredProcessingAttempt:
    """Extend the lease of a PROCESSING attempt (never shorten it). Touches nothing else."""
    validate_lease_seconds(lease_seconds)
    return _update_processing(
        db, attempt_id,
        {"lease_expires_at": func.greatest(t.c.lease_expires_at, _lease_expression(lease_seconds))},
        ProcessingStatus.PROCESSING,
    )


def mark_processed(db: Engine | Connection, attempt_id: int) -> StoredProcessingAttempt:
    return _update_processing(
        db, attempt_id, {"status": ProcessingStatus.PROCESSED.value, "lease_expires_at": None}, ProcessingStatus.PROCESSED)


def _finish_unsuccessfully(db, attempt_id, status: ProcessingStatus, reason_code: str, detail_code: str | None):
    validate_reason_code(reason_code)
    if detail_code is not None:
        validate_detail_code(detail_code)
    return _update_processing(
        db, attempt_id,
        {"status": status.value, "lease_expires_at": None, "reason_code": reason_code, "detail_code": detail_code},
        status,
    )


def mark_failed(db: Engine | Connection, attempt_id: int, reason_code: str, detail_code: str | None = None) -> StoredProcessingAttempt:
    """A retryable failure. Codes are bounded machine codes: never payload text or exception messages."""
    return _finish_unsuccessfully(db, attempt_id, ProcessingStatus.FAILED, reason_code, detail_code)


def mark_quarantined(db: Engine | Connection, attempt_id: int, reason_code: str, detail_code: str | None = None) -> StoredProcessingAttempt:
    """The evidence should not be processed under this version. Never retried automatically."""
    return _finish_unsuccessfully(db, attempt_id, ProcessingStatus.QUARANTINED, reason_code, detail_code)


def fail_expired_attempt(db: Engine | Connection, attempt_id: int, *, as_of: datetime | None = None) -> StoredProcessingAttempt:
    """Explicitly fail a PROCESSING attempt whose lease has ended (reason lease_expired).
    A live lease, or an attempt that already finished, is refused with a clear error."""
    clock = func.clock_timestamp() if as_of is None else literal(ensure_utc(as_of, field="as_of"))
    return _update_processing(
        db, attempt_id,
        {"status": ProcessingStatus.FAILED.value, "lease_expires_at": None, "reason_code": LEASE_EXPIRED_REASON},
        ProcessingStatus.FAILED,
        extra_where=t.c.lease_expires_at <= clock,
        unchanged_error=InvariantViolationError("lease_not_expired", "the attempt's lease has not expired"),
    )


# ---------------------------------------------------------------- reads

def get_processing_attempt(db: Engine | Connection, attempt_id: int) -> StoredProcessingAttempt | None:
    _positive_id(attempt_id, "attempt_id")
    with _connection(db) as connection:
        row = connection.execute(select(t).where(t.c.id == attempt_id)).one_or_none()
    return None if row is None else _to_stored(row)


def list_processing_attempts(db: Engine | Connection, observation_id: int, processor_id: str | None = None) -> list[StoredProcessingAttempt]:
    """The history, ordered by (processor_id, attempt_number)."""
    _positive_id(observation_id, "observation_id")
    query = select(t).where(t.c.observation_id == observation_id).order_by(t.c.processor_id, t.c.attempt_number)
    if processor_id is not None:
        query = query.where(t.c.processor_id == validate_processor_id(processor_id))
    with _connection(db) as connection:
        return [_to_stored(row) for row in connection.execute(query)]


def get_latest_attempt(db: Engine | Connection, observation_id: int, processor_id: str) -> StoredProcessingAttempt | None:
    _positive_id(observation_id, "observation_id")
    validate_processor_id(processor_id)
    with _connection(db) as connection:
        row = connection.execute(
            select(t).where(t.c.observation_id == observation_id, t.c.processor_id == processor_id)
            .order_by(t.c.attempt_number.desc()).limit(1)
        ).one_or_none()
    return None if row is None else _to_stored(row)


def list_unprocessed_observation_ids(db: Engine | Connection, processor_id: str, *, limit: int = 100) -> list[int]:
    """'Collected but not processed' for this processor: an Observation with NO attempt at all.
    (COLLECTED is derived from that absence; it is never stored.)"""
    validate_processor_id(processor_id)
    if type(limit) is not int or not 1 <= limit <= MAX_LIST_LIMIT:
        raise InvalidInputError("invalid_limit", f"limit must be an integer from 1 to {MAX_LIST_LIMIT}")
    has_attempt = select(t.c.id).where(t.c.observation_id == o.c.id, t.c.processor_id == processor_id).exists()
    with _connection(db) as connection:
        return list(connection.execute(select(o.c.id).where(~has_attempt).order_by(o.c.id).limit(limit)).scalars())
