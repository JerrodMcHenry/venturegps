"""Pure processing-attempt domain: policy, stored-attempt invariants, codes, leases."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.processing import (
    ProcessingStatus,
    check_may_start_attempt,
    next_attempt_number_for,
)
from app.v2.domain.processing_attempt import (
    DEFAULT_LEASE_SECONDS,
    LEASE_EXPIRED_REASON,
    MAX_LEASE_SECONDS,
    StoredProcessingAttempt,
    validate_detail_code,
    validate_lease_seconds,
    validate_processor_id,
    validate_reason_code,
)

P, D, F, Q = (ProcessingStatus.PROCESSING, ProcessingStatus.PROCESSED, ProcessingStatus.FAILED, ProcessingStatus.QUARANTINED)
T0 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def attempt(**overrides):
    base = dict(id=1, observation_id=1, processor_id="fin_extractor", processor_version="fin_extractor.v1", attempt_number=1,
                status=P, started_at=T0, lease_expires_at=T0 + timedelta(minutes=5))
    base.update(overrides)
    return StoredProcessingAttempt(**base)


def failed(**overrides):
    return attempt(status=F, finished_at=T0 + timedelta(seconds=3), lease_expires_at=None, reason_code="parse_error", **overrides)


# ---------------- start policy

@pytest.mark.parametrize(
    "latest_status, latest_version, requested, allowed",
    [
        (None, None, "x_proc.v1", True),                       # first attempt
        (F, "x_proc.v1", "x_proc.v1", True),                   # retry of a failure, same version
        (F, "x_proc.v1", "x_proc.v2", True),                   # ...or a newer one
        (F, "x_proc.v2", "x_proc.v1", True),                   # a failure is retryable under any version
        (D, "x_proc.v1", "x_proc.v2", True),                   # explicit reprocessing under a LATER version
        (D, "x_proc.v1", "x_proc.v1", False),                  # a processed attempt is not retried automatically
        (D, "x_proc.v2", "x_proc.v1", False),                  # nor "reprocessed" with an older version
        (Q, "x_proc.v1", "x_proc.v1", False),                  # a quarantine is not auto-retried
        (Q, "x_proc.v1", "x_proc.v2", True),                   # a later version may reprocess quarantined evidence
        (Q, "x_proc.v3", "x_proc.v2", False),
        (P, "x_proc.v1", "x_proc.v2", False),                  # one active attempt at a time
        (P, "x_proc.v1", "x_proc.v1", False),
    ],
)
def test_start_policy(latest_status, latest_version, requested, allowed):
    if allowed:
        check_may_start_attempt(latest_status, latest_version, requested)
    else:
        with pytest.raises(InvariantViolationError) as info:
            check_may_start_attempt(latest_status, latest_version, requested)
        assert info.value.code == ("attempt_already_active" if latest_status is P else "retry_not_allowed")


def test_attempt_numbers_are_linear_regardless_of_version():
    assert next_attempt_number_for(None) == 1
    assert next_attempt_number_for(1) == 2 and next_attempt_number_for(41) == 42
    for bad in (0, -1, "1", 1.0, True):
        with pytest.raises(InvariantViolationError):
            next_attempt_number_for(bad)


# ---------------- stored attempt invariants

def test_a_processing_attempt_has_a_lease_and_nothing_else():
    a = attempt()
    assert a.status is P and a.finished_at is None and a.reason_code is None and a.detail_code is None
    assert not a.is_terminal


def test_a_processed_attempt_is_finished_with_no_lease_and_no_failure_metadata():
    a = attempt(status=D, finished_at=T0 + timedelta(seconds=2), lease_expires_at=None)
    assert a.is_terminal and a.reason_code is None


@pytest.mark.parametrize("status", [F, Q])
def test_failed_and_quarantined_attempts_require_a_reason_and_allow_a_detail(status):
    common = dict(status=status, finished_at=T0 + timedelta(seconds=1), lease_expires_at=None)
    assert attempt(reason_code="unsupported_format", **common).detail_code is None
    assert attempt(reason_code="unsupported_format", detail_code="pdf_encrypted", **common).detail_code == "pdf_encrypted"
    with pytest.raises(InvariantViolationError):
        attempt(**common)                                    # reason missing


@pytest.mark.parametrize(
    "overrides",
    [
        dict(finished_at=T0 + timedelta(seconds=1)),                                  # processing but finished
        dict(lease_expires_at=None),                                                  # processing without a lease
        dict(reason_code="oops_code"),                                                # processing with failure metadata
        dict(detail_code="oops_code"),
        dict(status=D, lease_expires_at=None),                                        # processed but not finished
        dict(status=D, finished_at=T0 + timedelta(seconds=1)),                        # processed with a lease
        dict(status=D, finished_at=T0 + timedelta(seconds=1), lease_expires_at=None, reason_code="oops_code"),
        dict(status=D, finished_at=T0 + timedelta(seconds=1), lease_expires_at=None, detail_code="oops_code"),
        dict(status=F, finished_at=T0 + timedelta(seconds=1), reason_code="oops_code"),          # failed with a lease
        dict(status=F, lease_expires_at=None, reason_code="oops_code"),                          # failed but not finished
        dict(status=Q, finished_at=T0 + timedelta(seconds=1), lease_expires_at=None, detail_code="only_detail"),
    ],
)
def test_invalid_state_combinations_are_rejected(overrides):
    with pytest.raises(InvariantViolationError) as info:
        attempt(**overrides)
    assert info.value.code == "invalid_attempt_state"


def test_finished_at_cannot_precede_started_at():
    with pytest.raises(InvariantViolationError) as info:
        attempt(status=D, finished_at=T0 - timedelta(seconds=1), lease_expires_at=None)
    assert info.value.code == "finished_before_started"


def test_the_processor_version_must_belong_to_the_processor():
    with pytest.raises(InvalidInputError) as info:
        attempt(processor_version="other_processor.v1")
    assert info.value.code == "processor_version_mismatch"
    assert attempt(processor_id="fin_extractor", processor_version="fin_extractor.v12").processor_version == "fin_extractor.v12"


def test_times_must_be_aware_and_are_normalized():
    with pytest.raises(InvalidInputError):
        attempt(started_at=datetime(2026, 1, 1))
    plus2 = timezone(timedelta(hours=2))
    a = attempt(started_at=datetime(2026, 9, 21, 14, tzinfo=plus2), lease_expires_at=datetime(2026, 9, 21, 15, tzinfo=plus2))
    assert a.started_at == T0 and a.started_at.tzinfo is timezone.utc


@pytest.mark.parametrize("bad", [0, -1, "1", None, 1.0, True])
def test_ids_and_attempt_numbers(bad):
    for field in ("id", "observation_id", "attempt_number"):
        with pytest.raises(ValidationError):
            attempt(**{field: bad})


def test_the_model_is_immutable_and_closed():
    a = attempt()
    with pytest.raises(ValidationError):
        a.status = D
    with pytest.raises(ValidationError):
        attempt(extra_field=1)
    with pytest.raises(ValidationError):
        attempt(status="processing")


def test_an_attempt_has_only_operational_fields():
    fields = set(StoredProcessingAttempt.model_fields)
    assert fields == {"id", "observation_id", "processor_id", "processor_version", "attempt_number", "status",
                      "started_at", "finished_at", "lease_expires_at", "reason_code", "detail_code"}
    for banned in ("payload", "bytes", "hash", "excerpt", "message", "exception", "trace", "prompt", "model", "ai_",
                   "response", "confidence", "candidate", "company", "score", "observed_time", "recorded_time"):
        assert not any(banned in f for f in fields), banned


# ---------------- leases: expiry is informational and uses a supplied clock

def test_lease_expiry_is_computed_against_a_supplied_clock_and_changes_nothing():
    a = attempt()
    assert a.is_lease_expired(T0) is False and a.is_lease_expired(T0 + timedelta(minutes=4, seconds=59)) is False
    assert a.is_lease_expired(T0 + timedelta(minutes=5)) is True           # at the boundary: expired
    assert a.is_lease_expired(T0 + timedelta(days=1)) is True
    assert a.status is P                                                   # still PROCESSING: expiry alone is not a transition


def test_terminal_attempts_are_never_lease_expired():
    assert failed().is_lease_expired(T0 + timedelta(days=9)) is False
    with pytest.raises(InvalidInputError):
        attempt().is_lease_expired(datetime(2026, 1, 1))                    # a naive clock is refused


@pytest.mark.parametrize("seconds", [1, DEFAULT_LEASE_SECONDS, 3600, MAX_LEASE_SECONDS])
def test_valid_lease_durations(seconds):
    assert validate_lease_seconds(seconds) == seconds


@pytest.mark.parametrize("seconds", [0, -1, MAX_LEASE_SECONDS + 1, 1.5, "60", None, True])
def test_invalid_lease_durations(seconds):
    with pytest.raises(InvalidInputError) as info:
        validate_lease_seconds(seconds)
    assert info.value.code == "invalid_lease_seconds"


# ---------------- bounded machine codes only

@pytest.mark.parametrize("validator", [validate_processor_id, validate_reason_code, validate_detail_code])
@pytest.mark.parametrize("value", ["ab", "parse_error", "lease_expired", "x" * 64, "a1_b2"])
def test_valid_codes(validator, value):
    assert validator(value) == value


@pytest.mark.parametrize("validator", [validate_processor_id, validate_reason_code, validate_detail_code])
@pytest.mark.parametrize(
    "value",
    ["", "a", "Parse", "parse error", "parse-error", "1abc", "_abc", "x" * 65, "err\n", "café", None, 5, b"abc",
     "Traceback (most recent call last):", "ValueError: bad input at line 3", "the company raised $5M"],
)
def test_free_text_and_malformed_codes_are_rejected(validator, value):
    with pytest.raises(InvalidInputError):
        validator(value)


def test_the_lease_expired_reason_is_itself_a_valid_code():
    assert validate_reason_code(LEASE_EXPIRED_REASON) == "lease_expired"
