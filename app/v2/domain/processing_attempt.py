"""
ProcessingAttempt: operational history of processing one immutable Observation.

"VentureGPS attempted to process this Observation using this versioned
processor." It is NOT evidence, canonical truth, an Observation status, an AI
result, a candidate or a company classification. Observations contain no
processing status; "collected but not processed" means no attempt exists.

Identity: (observation_id, processor_id, attempt_number). processor_id names
the deterministic (or, later, bounded) processing implementation;
processor_version is a VersionId of it and must carry the SAME name
(financing_extractor.v2 for processor financing_extractor), so a version
cannot be attributed to a different processor. There is no processor registry.

Timing is operational and database-assigned: started_at when the attempt
begins, finished_at when it reaches a terminal state. Neither is evidence time.

Lease: a PROCESSING attempt carries lease_expires_at. An expired lease is NOT
a state change: the attempt stays PROCESSING until an explicit operation marks
it FAILED (reason lease_expired). Terminal attempts have no lease.

Failure / quarantine metadata is bounded machine codes only (reason_code
required, detail_code optional). Never payload excerpts, exception text,
stack traces, prompts or AI output.
"""

import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field, model_validator

from app.v2.domain.base import DomainModel
from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.processing import ProcessingStatus
from app.v2.domain.time import UtcDatetime, ensure_utc
from app.v2.domain.versions import VersionId, version_name

_CODE = re.compile(r"[a-z][a-z0-9_]{1,63}")

LEASE_EXPIRED_REASON = "lease_expired"
DEFAULT_LEASE_SECONDS = 300
MAX_LEASE_SECONDS = 24 * 60 * 60


def validate_processor_id(value: object) -> str:
    if not isinstance(value, str) or _CODE.fullmatch(value) is None:
        raise InvalidInputError("invalid_processor_id", "processor id must be a lowercase slug of 2-64 characters")
    return value


def validate_reason_code(value: object) -> str:
    if not isinstance(value, str) or _CODE.fullmatch(value) is None:
        raise InvalidInputError("invalid_reason_code", "reason code must be a lowercase machine code of 2-64 characters")
    return value


def validate_detail_code(value: object) -> str:
    if not isinstance(value, str) or _CODE.fullmatch(value) is None:
        raise InvalidInputError("invalid_detail_code", "detail code must be a lowercase machine code of 2-64 characters")
    return value


def validate_lease_seconds(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_LEASE_SECONDS:
        raise InvalidInputError("invalid_lease_seconds", f"lease seconds must be an integer from 1 to {MAX_LEASE_SECONDS}")
    return value


ProcessorId = Annotated[str, AfterValidator(validate_processor_id)]
ReasonCode = Annotated[str, AfterValidator(validate_reason_code)]
DetailCode = Annotated[str, AfterValidator(validate_detail_code)]


class StoredProcessingAttempt(DomainModel):
    id: int = Field(gt=0)
    observation_id: int = Field(gt=0)
    processor_id: ProcessorId
    processor_version: VersionId
    attempt_number: int = Field(ge=1)
    status: ProcessingStatus
    started_at: UtcDatetime
    finished_at: UtcDatetime | None = None
    lease_expires_at: UtcDatetime | None = None
    reason_code: ReasonCode | None = None
    detail_code: DetailCode | None = None

    @model_validator(mode="after")
    def _state_is_coherent(self) -> "StoredProcessingAttempt":
        if version_name(self.processor_version) != self.processor_id:
            raise InvalidInputError("processor_version_mismatch", "processor version must carry the processor id as its name")
        processing = self.status is ProcessingStatus.PROCESSING
        failure_like = self.status in (ProcessingStatus.FAILED, ProcessingStatus.QUARANTINED)
        ok = (
            (self.finished_at is None) == processing
            and (self.lease_expires_at is not None) == processing
            and (self.reason_code is not None) == failure_like
            and (self.detail_code is None or failure_like)
        )
        if not ok:
            raise InvariantViolationError("invalid_attempt_state", "status, finish time, lease and failure metadata are inconsistent")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise InvariantViolationError("finished_before_started", "finished_at precedes started_at")
        return self

    @property
    def is_terminal(self) -> bool:
        return self.status is not ProcessingStatus.PROCESSING

    def is_lease_expired(self, as_of: datetime) -> bool:
        """Whether this attempt is PROCESSING with a lease that ended at or before `as_of`.
        Purely informational: an expired lease does not change the attempt's status."""
        return self.status is ProcessingStatus.PROCESSING and self.lease_expires_at <= ensure_utc(as_of, field="as_of")
