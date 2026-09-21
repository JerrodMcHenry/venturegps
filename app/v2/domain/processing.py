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
