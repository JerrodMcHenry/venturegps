"""
Collection run: a persistent operational record of one bounded SEC Form D collection attempt (Increment 18.5).

This is NOT evidence, a candidate, or a canonical fact -- it is operational metadata about a run of the
existing, unmodified collection pipeline (app.v2.tools.sec_form_d_collector + app.v2.tools.cli's own
_collect_and_extract_one). Nothing here proposes, resolves or promotes anything; a CollectionRun records what
the pipeline did, never what it decided.

    CollectionTriggerType   manual (a human ran the CLI or the admin-only manual-trigger endpoint) or
                            scheduled (an external cron invoked the same CLI command unattended)
    CollectionRunStatus     running -> succeeded | failed | partial | interrupted
                            (interrupted is terminal too: a crashed run's lease expired before it could
                            reach any other terminal state, and an explicit recovery step said so -- it is
                            never silently retried or silently left "running" forever)

MAX_FILINGS_PER_RUN mirrors the existing, already-enforced app.v2.tools.sec_form_d_collector.MAX_DISCOVERY_RESULTS
(25) -- this module does not invent a new bound, it validates against the one the collector already has.

Failure detail is bounded, sanitized text: never a raw exception message, a stack trace, an evidence excerpt,
a byte hash, credentials or a session token. The per-filing collection pipeline already only ever returns
exception TYPE names and its own static CollectionError text (see docs/v2/SEC_COLLECTION_SECURITY.md) --
validate_failure_detail enforces the same bound here, structurally, rather than trusting every caller to
remember it.
"""

import re
from enum import Enum

from pydantic import Field, model_validator

from app.v2.domain.base import DomainModel
from app.v2.domain.errors import InvalidInputError
from app.v2.domain.time import UtcDatetime

MAX_FILINGS_PER_RUN = 25  # matches app.v2.tools.sec_form_d_collector.MAX_DISCOVERY_RESULTS exactly
MAX_QUERY_LENGTH = 200
MAX_FAILURE_DETAIL_LENGTH = 4000
MAX_JOB_NAME_LENGTH = 64

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_JOB_NAME = re.compile(r"[a-z][a-z0-9_]{1,63}")
_TRIGGERED_BY = re.compile(r"[a-z][a-z0-9_]{0,31}:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


class CollectionTriggerType(str, Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class CollectionRunStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    INTERRUPTED = "interrupted"


TERMINAL_COLLECTION_STATUSES = frozenset({
    CollectionRunStatus.SUCCEEDED, CollectionRunStatus.FAILED,
    CollectionRunStatus.PARTIAL, CollectionRunStatus.INTERRUPTED,
})


def validate_job_name(value: object) -> str:
    if not isinstance(value, str) or _JOB_NAME.fullmatch(value) is None:
        raise InvalidInputError("invalid_job_name", "job name must be a lowercase slug of 2-64 characters")
    return value


def validate_collection_query(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_QUERY_LENGTH or _CONTROL.search(value):
        raise InvalidInputError("invalid_collection_query", f"query must be 1-{MAX_QUERY_LENGTH} characters without control characters")
    return value


def validate_max_filings(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_FILINGS_PER_RUN:
        raise InvalidInputError("invalid_max_filings", f"max filings must be an integer from 1 to {MAX_FILINGS_PER_RUN}")
    return value


def validate_triggered_by(value: object) -> str:
    """The actor that started the run: 'cli:scheduled', 'cli:manual', or 'admin:<clerk user id>' for the
    review API's manual trigger -- never a client-supplied free string, always constructed server-side."""
    if not isinstance(value, str) or _TRIGGERED_BY.fullmatch(value) is None:
        raise InvalidInputError("invalid_triggered_by", "triggered_by must look like kind:identifier")
    return value


def validate_failure_detail(value: object) -> str:
    if not isinstance(value, str) or len(value) > MAX_FAILURE_DETAIL_LENGTH or _CONTROL.search(value):
        raise InvalidInputError("invalid_failure_detail", f"failure detail must be at most {MAX_FAILURE_DETAIL_LENGTH} characters without control characters")
    return value


class StoredCollectionRun(DomainModel):
    """A persisted collection run. Counts default to 0 (a just-started run has counted nothing yet) and only
    ever move forward -- this module does not enforce that itself (the repository's UPDATE statements do,
    always writing the run's own row by id), but nothing here ever decrements a count."""

    id: int = Field(gt=0)
    job_name: str
    trigger_type: CollectionTriggerType
    triggered_by: str
    status: CollectionRunStatus
    query: str
    max_filings: int = Field(ge=1, le=MAX_FILINGS_PER_RUN)
    started_at: UtcDatetime
    completed_at: UtcDatetime | None = None
    lease_expires_at: UtcDatetime
    discovered_count: int = Field(ge=0, default=0)
    collected_count: int = Field(ge=0, default=0)
    duplicate_count: int = Field(ge=0, default=0)
    failed_count: int = Field(ge=0, default=0)
    candidate_count: int = Field(ge=0, default=0)
    failure_detail: str | None = None
    result_detail: str | None = None  # bounded JSON summary of per-filing outcomes; never raw evidence

    @model_validator(mode="after")
    def _shape_is_coherent(self) -> "StoredCollectionRun":
        is_terminal = self.status in TERMINAL_COLLECTION_STATUSES
        if is_terminal != (self.completed_at is not None):
            raise InvalidInputError("invalid_run_state", "completed_at must be set iff the run reached a terminal status")
        if self.status is CollectionRunStatus.RUNNING and self.failure_detail is not None:
            raise InvalidInputError("invalid_run_state", "a running run cannot already carry a failure detail")
        return self

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_COLLECTION_STATUSES
