"""
Collection run persistence: job history for bounded collection attempts (Increment 18.5).

    start_run(db, *, job_name, trigger_type, triggered_by, query, max_filings, lease_seconds) -> StoredCollectionRun
    renew_lease(db, run_id, *, lease_seconds)               -> StoredCollectionRun
    complete_run(db, run_id, *, status, counts..., failure_detail=, result_detail=) -> StoredCollectionRun
    recover_interrupted_runs(db, *, job_name=None)           -> list[StoredCollectionRun]
    get_collection_run(db, run_id)                           -> StoredCollectionRun | None
    list_collection_runs(db, *, job_name=None, limit=50, offset=0) -> list[StoredCollectionRun]
    count_pending_review_candidates(db)                      -> dict  (companies/financing, for the ops UI)

start_run is the ONLY way "no overlapping collection runs" is enforced: it INSERTs a status='running' row, and
the database's own partial unique index (uq_collection_run_one_active_per_job, migration 0011) is the actual
lock -- a second concurrent start_run for the same job_name gets IntegrityError, translated to
CollectionAlreadyRunningError, never a silently-lost race. This holds across process crashes and separate CLI
invocations, not just within one Python process.

renew_lease / recover_interrupted_runs implement "interrupted jobs have a recoverable or explicitly failed
state": a run whose lease_expires_at has passed without completing is never silently retried and never left
"running" forever -- recover_interrupted_runs moves it to status='interrupted' (a terminal, explicit state),
freeing the job_name lock for a new run. The v2.collection_run_guard() trigger (migration 0011) is the second,
database-level line of defense: it refuses any UPDATE once a row is already terminal, so even a buggy caller
cannot resurrect or silently rewrite a finished run's outcome.

Nothing here writes evidence, a candidate, or a canonical fact -- this module is purely operational metadata.
Reads may be broad (there is no untrusted/canonical boundary here to protect).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.v2.db.tables import collection_run_table as t
from app.v2.db.tables import company_candidate_table as cc
from app.v2.db.tables import financing_event_candidate_table as fcc
from app.v2.db.tables import financing_resolution_decision_table as frd
from app.v2.db.tables import resolution_decision_table as rd
from app.v2.domain.collection import (
    MAX_FILINGS_PER_RUN,
    CollectionRunStatus,
    CollectionTriggerType,
    StoredCollectionRun,
    validate_collection_query,
    validate_failure_detail,
    validate_job_name,
    validate_max_filings,
    validate_triggered_by,
)
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError
from app.v2.domain.resolution import FINAL_DECISION_KINDS
from app.v2.domain.financing_resolution import FINAL_FINANCING_DECISION_KINDS
from app.v2.repositories._db import connection as _connection
from app.v2.repositories._db import integrity_error_to_domain
from app.v2.repositories.errors import ConflictError, NotFoundError

DEFAULT_LEASE_SECONDS = 900  # 15 minutes: generous for a <=25-filing bounded run, still bounded
MAX_LEASE_SECONDS = 3600
MAX_LIST_LIMIT = 200


class CollectionAlreadyRunningError(ConflictError):
    """Another run for this job_name is already active (uq_collection_run_one_active_per_job)."""


def validate_lease_seconds(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_LEASE_SECONDS:
        raise InvalidInputError("invalid_lease_seconds", f"lease seconds must be an integer from 1 to {MAX_LEASE_SECONDS}")
    return value


def _to_stored(row) -> StoredCollectionRun:
    m = row._mapping
    try:
        return StoredCollectionRun(
            id=m["id"], job_name=m["job_name"], trigger_type=CollectionTriggerType(m["trigger_type"]),
            triggered_by=m["triggered_by"], status=CollectionRunStatus(m["status"]), query=m["query"],
            max_filings=m["max_filings"], started_at=m["started_at"], completed_at=m["completed_at"],
            lease_expires_at=m["lease_expires_at"], discovered_count=m["discovered_count"],
            collected_count=m["collected_count"], duplicate_count=m["duplicate_count"],
            failed_count=m["failed_count"], candidate_count=m["candidate_count"],
            failure_detail=m["failure_detail"], result_detail=m["result_detail"],
        )
    except (DomainError, ValueError):
        raise InvariantViolationError("stored_collection_run_invalid", "a stored collection run does not satisfy the domain model") from None


def start_run(
    db: Engine | Connection, *, job_name: str, trigger_type: CollectionTriggerType, triggered_by: str,
    query: str, max_filings: int, lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> StoredCollectionRun:
    job_name = validate_job_name(job_name)
    if not isinstance(trigger_type, CollectionTriggerType):
        raise InvalidInputError("invalid_trigger_type", "trigger_type must be a CollectionTriggerType")
    triggered_by = validate_triggered_by(triggered_by)
    query = validate_collection_query(query)
    max_filings = validate_max_filings(max_filings)
    lease_seconds = validate_lease_seconds(lease_seconds)
    lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)

    with _connection(db) as connection:
        try:
            row = connection.execute(
                pg_insert(t).values(
                    job_name=job_name, trigger_type=trigger_type.value, triggered_by=triggered_by,
                    status=CollectionRunStatus.RUNNING.value, query=query, max_filings=max_filings,
                    lease_expires_at=lease_expires_at,
                ).returning(*t.c)
            ).one()
        except IntegrityError as exc:
            from app.v2.repositories._db import constraint_of
            if constraint_of(exc) == "uq_collection_run_one_active_per_job":
                raise CollectionAlreadyRunningError(
                    "collection_already_running", f"a collection run for job {job_name!r} is already active"
                ) from None
            raise integrity_error_to_domain(exc) from None
    return _to_stored(row)


def renew_lease(db: Engine | Connection, run_id: int, *, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> StoredCollectionRun:
    """Extend a still-running run's lease -- called periodically during a long collection so a slow (but
    healthy) run is never mistaken for an interrupted one."""
    lease_seconds = validate_lease_seconds(lease_seconds)
    lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
    with _connection(db) as connection:
        try:
            row = connection.execute(
                update(t).where(t.c.id == run_id, t.c.status == CollectionRunStatus.RUNNING.value)
                .values(lease_expires_at=lease_expires_at).returning(*t.c)
            ).one_or_none()
        except IntegrityError as exc:
            raise integrity_error_to_domain(exc) from None
    if row is None:
        raise NotFoundError("collection_run_not_found", "no running collection run exists with that id")
    return _to_stored(row)


def complete_run(
    db: Engine | Connection, run_id: int, *, status: CollectionRunStatus, discovered_count: int, collected_count: int,
    duplicate_count: int, failed_count: int, candidate_count: int, failure_detail: str | None = None,
    result_detail: str | None = None,
) -> StoredCollectionRun:
    """Move a running run to a terminal status, recording final counts. Refused (NotFoundError) if the run does
    not exist or is not currently running -- a terminal run can never be completed a second time; the database
    trigger is the last-resort enforcement of that, this is the friendly, typed one."""
    if not isinstance(status, CollectionRunStatus) or status is CollectionRunStatus.RUNNING:
        raise InvalidInputError("invalid_terminal_status", "status must be a terminal CollectionRunStatus")
    for name, value in (("discovered_count", discovered_count), ("collected_count", collected_count),
                       ("duplicate_count", duplicate_count), ("failed_count", failed_count),
                       ("candidate_count", candidate_count)):
        if type(value) is not int or value < 0:
            raise InvalidInputError("invalid_count", f"{name} must be a non-negative integer")
    if failure_detail is not None:
        failure_detail = validate_failure_detail(failure_detail)
    if result_detail is not None:
        result_detail = validate_failure_detail(result_detail)  # same bound family; length-checked at the DB too

    with _connection(db) as connection:
        try:
            row = connection.execute(
                update(t).where(t.c.id == run_id, t.c.status == CollectionRunStatus.RUNNING.value).values(
                    status=status.value, completed_at=datetime.now(timezone.utc),
                    discovered_count=discovered_count, collected_count=collected_count,
                    duplicate_count=duplicate_count, failed_count=failed_count, candidate_count=candidate_count,
                    failure_detail=failure_detail, result_detail=result_detail,
                ).returning(*t.c)
            ).one_or_none()
        except IntegrityError as exc:
            raise integrity_error_to_domain(exc) from None
    if row is None:
        raise NotFoundError("collection_run_not_found", "no running collection run exists with that id")
    return _to_stored(row)


def recover_interrupted_runs(db: Engine | Connection, *, job_name: str | None = None) -> list[StoredCollectionRun]:
    """Every run still 'running' whose lease has already expired is moved to the terminal 'interrupted' status
    -- a crashed process (or a machine that lost power mid-run) never leaves job_name locked forever, and the
    interrupted run's own row states plainly what happened rather than vanishing or silently retrying."""
    now = datetime.now(timezone.utc)
    with _connection(db) as connection:
        condition = (t.c.status == CollectionRunStatus.RUNNING.value) & (t.c.lease_expires_at < now)
        if job_name is not None:
            condition = condition & (t.c.job_name == validate_job_name(job_name))
        try:
            rows = connection.execute(
                update(t).where(condition).values(
                    status=CollectionRunStatus.INTERRUPTED.value, completed_at=now,
                    failure_detail="lease_expired",
                ).returning(*t.c)
            ).all()
        except IntegrityError as exc:
            raise integrity_error_to_domain(exc) from None
    return [_to_stored(r) for r in rows]


def get_collection_run(db: Engine | Connection, run_id: int) -> StoredCollectionRun | None:
    with _connection(db) as connection:
        row = connection.execute(select(t).where(t.c.id == run_id)).one_or_none()
    return None if row is None else _to_stored(row)


def list_collection_runs(
    db: Engine | Connection, *, job_name: str | None = None, limit: int = 50, offset: int = 0
) -> list[StoredCollectionRun]:
    if type(limit) is not int or limit < 1 or limit > MAX_LIST_LIMIT:
        raise InvalidInputError("invalid_limit", f"limit must be 1-{MAX_LIST_LIMIT}")
    if type(offset) is not int or offset < 0:
        raise InvalidInputError("invalid_offset", "offset must be 0 or a positive integer")
    query = select(t).order_by(t.c.started_at.desc(), t.c.id.desc()).limit(limit).offset(offset)
    if job_name is not None:
        query = query.where(t.c.job_name == validate_job_name(job_name))
    with _connection(db) as connection:
        return [_to_stored(r) for r in connection.execute(query)]


def count_pending_review_candidates(db: Engine | Connection) -> dict:
    """Companies-review-summary counts for the collection operations UI: how much backlog exists right now.
    A plain COUNT over the same "no final decision" shape companies.list_pending_company_candidates and
    financing_events.list_pending_financing_candidates already use -- this only counts, it does not load rows."""
    company_final = rd.c.decision_kind.in_([k.value for k in FINAL_DECISION_KINDS])
    financing_final = frd.c.decision_kind.in_([k.value for k in FINAL_FINANCING_DECISION_KINDS])
    with _connection(db) as connection:
        pending_companies = connection.execute(
            select(func.count()).select_from(cc).where(
                ~select(rd.c.id).where(rd.c.candidate_id == cc.c.id, company_final).exists()
            )
        ).scalar_one()
        pending_financing = connection.execute(
            select(func.count()).select_from(fcc).where(
                ~select(frd.c.id).where(frd.c.candidate_id == fcc.c.id, financing_final).exists()
            )
        ).scalar_one()
    return {"pending_company_candidates": pending_companies, "pending_financing_candidates": pending_financing}
