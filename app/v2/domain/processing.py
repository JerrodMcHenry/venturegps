"""
Processing-attempt state semantics (pure; no persistence, workers or leases).

An ATTEMPT to process an observation is PROCESSING until it ends in exactly
one terminal state. "COLLECTED" (an observation nobody has processed) is not
a stored state: it is the absence of any attempt.

    PROCESSING -> PROCESSED | FAILED | QUARANTINED
    PROCESSED, FAILED, QUARANTINED are terminal.

A retry is a NEW attempt with the next attempt number, never a transition
back out of FAILED. A QUARANTINED attempt is not retried automatically; that
needs an explicit decision (later). Reprocessing with a newer processor
version is likewise a new attempt series.
"""

from enum import Enum

from app.v2.domain.errors import InvariantViolationError
from app.v2.domain.versions import version_number


class ProcessingStatus(str, Enum):
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    QUARANTINED = "quarantined"


INITIAL_STATUS = ProcessingStatus.PROCESSING

TERMINAL_STATUSES = frozenset(
    {ProcessingStatus.PROCESSED, ProcessingStatus.FAILED, ProcessingStatus.QUARANTINED}
)

ALLOWED_TRANSITIONS: dict[ProcessingStatus, frozenset[ProcessingStatus]] = {
    ProcessingStatus.PROCESSING: TERMINAL_STATUSES,
    ProcessingStatus.PROCESSED: frozenset(),
    ProcessingStatus.FAILED: frozenset(),
    ProcessingStatus.QUARANTINED: frozenset(),
}


def is_terminal(status: ProcessingStatus) -> bool:
    return status in TERMINAL_STATUSES


def can_transition(current: ProcessingStatus, new: ProcessingStatus) -> bool:
    return new in ALLOWED_TRANSITIONS[current]


def assert_transition(current: ProcessingStatus, new: ProcessingStatus) -> None:
    if not can_transition(current, new):
        raise InvariantViolationError(
            "illegal_transition", f"a {current.value} attempt cannot become {new.value}"
        )


def next_attempt_number(previous_attempt_number: int, previous_status: ProcessingStatus) -> int:
    """The attempt number of a retry. Only a FAILED attempt is retried this way."""
    if type(previous_attempt_number) is not int or previous_attempt_number < 1:
        raise InvariantViolationError("invalid_attempt_number", "attempt numbers start at 1")
    if previous_status is not ProcessingStatus.FAILED:
        raise InvariantViolationError(
            "retry_not_allowed", f"a {previous_status.value} attempt is not retried automatically"
        )
    return previous_attempt_number + 1


def check_may_start_attempt(
    latest_status: ProcessingStatus | None, latest_version: str | None, requested_version: str
) -> None:
    """May a NEW attempt be started for an observation + processor, given the latest one?

        no attempt yet        -> yes (attempt 1)
        PROCESSING            -> no: one active attempt at a time
        FAILED                -> yes: a retry (same or another version)
        PROCESSED/QUARANTINED -> only for a LATER processor_version (an explicit
                                 reprocessing request); the same or an older version is not
                                 retried automatically, and a quarantine is not auto-retried.

    Attempt numbering is separate: it is linear per observation + processor_id
    regardless of version (see next_attempt_number_for).
    """
    if latest_status is None:
        return
    if latest_status is ProcessingStatus.PROCESSING:
        raise InvariantViolationError("attempt_already_active", "an attempt is already processing")
    if latest_status is ProcessingStatus.FAILED:
        return
    if latest_version is None or version_number(requested_version) <= version_number(latest_version):
        raise InvariantViolationError(
            "retry_not_allowed",
            f"a {latest_status.value} attempt is not retried automatically; only a later processor version may reprocess",
        )


def next_attempt_number_for(latest_attempt_number: int | None) -> int:
    """Linear per (observation, processor_id): 1 for the first, else the latest + 1."""
    if latest_attempt_number is None:
        return 1
    if type(latest_attempt_number) is not int or latest_attempt_number < 1:
        raise InvariantViolationError("invalid_attempt_number", "attempt numbers start at 1")
    return latest_attempt_number + 1
