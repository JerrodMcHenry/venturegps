import pytest

from app.v2.domain.errors import InvariantViolationError
from app.v2.domain.processing import (
    ALLOWED_TRANSITIONS,
    INITIAL_STATUS,
    TERMINAL_STATUSES,
    ProcessingStatus,
    assert_transition,
    can_transition,
    is_terminal,
    next_attempt_number,
)

P, D, F, Q = (ProcessingStatus.PROCESSING, ProcessingStatus.PROCESSED,
              ProcessingStatus.FAILED, ProcessingStatus.QUARANTINED)


def test_the_stored_states_are_exactly_four_and_collected_is_derived_not_stored():
    assert {s.value for s in ProcessingStatus} == {"processing", "processed", "failed", "quarantined"}
    assert "COLLECTED" not in ProcessingStatus.__members__ and "collected" not in {s.value for s in ProcessingStatus}
    assert INITIAL_STATUS is P


def test_terminal_statuses():
    assert TERMINAL_STATUSES == {D, F, Q}
    assert not is_terminal(P) and all(is_terminal(s) for s in (D, F, Q))


@pytest.mark.parametrize("target", [D, F, Q])
def test_processing_may_end_in_any_terminal_state(target):
    assert can_transition(P, target)
    assert_transition(P, target)  # does not raise


@pytest.mark.parametrize("current", [D, F, Q])
@pytest.mark.parametrize("new", list(ProcessingStatus))
def test_terminal_attempts_never_transition_again(current, new):
    assert not can_transition(current, new)
    with pytest.raises(InvariantViolationError) as info:
        assert_transition(current, new)
    assert info.value.code == "illegal_transition"


def test_processing_cannot_stay_or_loop():
    assert not can_transition(P, P)
    with pytest.raises(InvariantViolationError):
        assert_transition(P, P)


def test_the_transition_table_is_exactly_the_specified_one():
    assert ALLOWED_TRANSITIONS == {P: frozenset({D, F, Q}), D: frozenset(), F: frozenset(), Q: frozenset()}


def test_retry_is_a_new_attempt_not_a_reversal_of_failed():
    assert not can_transition(F, P)                       # FAILED is never mutated back into PROCESSING
    with pytest.raises(InvariantViolationError):
        assert_transition(F, P)
    assert next_attempt_number(1, F) == 2                 # the retry is attempt 2, starting again at INITIAL_STATUS
    assert next_attempt_number(2, F) == 3
    assert INITIAL_STATUS is P


@pytest.mark.parametrize("status", [P, D, Q])
def test_only_a_failed_attempt_is_retried_automatically(status):
    with pytest.raises(InvariantViolationError) as info:
        next_attempt_number(1, status)
    assert info.value.code == "retry_not_allowed"


@pytest.mark.parametrize("number", [0, -1, 1.0, "1", None, True])
def test_attempt_numbers_start_at_one(number):
    with pytest.raises(InvariantViolationError) as info:
        next_attempt_number(number, F)
    assert info.value.code == "invalid_attempt_number"
