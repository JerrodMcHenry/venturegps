"""
Deterministic tests for AI Request Reliability (Portfolio Release Task 2 --
app/ai/pillar_shared.py::call_analysis_model()'s bounded retry-with-backoff
policy for transient OpenAI failures).

Fully offline: client.chat.completions.create() is monkeypatched to a fake
that raises canned openai SDK exceptions or returns a canned response,
never making a real network/API call. time.sleep() and random.random()
are also monkeypatched so no test actually waits, and backoff assertions
are exact rather than timing-dependent. Every test restores whatever it
patched in a finally block, even on failure -- the same manual-patch
convention every other test file in this directory already uses.

Run with:
    python -m app.tests.test_ai_request_reliability
"""

from unittest.mock import MagicMock

import httpx
import openai

import app.ai.pillar_shared as pillar_shared


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


_FAKE_REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def _fake_response_content(text: str) -> MagicMock:
    """A minimal stand-in for the OpenAI SDK's ChatCompletion response
    shape -- only response.choices[0].message.content is ever read by
    call_analysis_model()."""
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=text))]
    return response


def _status_error(cls, status_code: int, message: str = "error") -> Exception:
    fake_response = httpx.Response(status_code, request=_FAKE_REQUEST, json={"error": {"message": message}})
    return cls(message, response=fake_response, body=None)


def _connection_error() -> Exception:
    return openai.APIConnectionError(request=_FAKE_REQUEST)


def _timeout_error() -> Exception:
    return openai.APITimeoutError(request=_FAKE_REQUEST)


def _rate_limit_error() -> Exception:
    return _status_error(openai.RateLimitError, 429, "rate limited")


def _server_error() -> Exception:
    return _status_error(openai.InternalServerError, 500, "server error")


def _auth_error() -> Exception:
    return _status_error(openai.AuthenticationError, 401, "invalid api key")


def _bad_request_error() -> Exception:
    return _status_error(openai.BadRequestError, 400, "invalid request")


class _PatchedClient:
    """Context-manager-free patch of pillar_shared.client.chat.completions.create,
    restored by the caller's own finally block. side_effect is a list
    consumed one entry per call: an Exception instance is raised, anything
    else is returned as the (fake) response."""

    def __init__(self, side_effects: list) -> None:
        self._side_effects = list(side_effects)
        self.calls = 0
        self._original_create = pillar_shared.client.chat.completions.create

    def _fake_create(self, *args, **kwargs):
        self.calls += 1
        effect = self._side_effects.pop(0)

        if isinstance(effect, Exception):
            raise effect

        return effect

    def __enter__(self) -> "_PatchedClient":
        pillar_shared.client.chat.completions.create = self._fake_create
        return self

    def __exit__(self, *exc) -> bool:
        pillar_shared.client.chat.completions.create = self._original_create
        return False


class _PatchedSleep:
    """Records every call_analysis_model()-issued sleep without actually
    sleeping, and pins random.random() so backoff delays are exact and
    assertable rather than jittered within a range."""

    def __init__(self, fixed_random: float = 0.5) -> None:
        self.delays: list[float] = []
        self._original_sleep = pillar_shared.time.sleep
        self._original_random = pillar_shared.random.random
        self._fixed_random = fixed_random

    def _fake_sleep(self, seconds: float) -> None:
        self.delays.append(seconds)

    def __enter__(self) -> "_PatchedSleep":
        pillar_shared.time.sleep = self._fake_sleep
        pillar_shared.random.random = lambda: self._fixed_random
        return self

    def __exit__(self, *exc) -> bool:
        pillar_shared.time.sleep = self._original_sleep
        pillar_shared.random.random = self._original_random
        return False


def test_successful_first_attempt_makes_exactly_one_call() -> None:
    with _PatchedClient([_fake_response_content("ok")]) as fake_client, _PatchedSleep() as fake_sleep:
        result = pillar_shared.call_analysis_model("system", "user", 0.0)

    expect(result == "ok", f"Expected the first attempt's content, got {result!r}")
    expect(fake_client.calls == 1, f"Expected exactly 1 call for an immediate success, got {fake_client.calls}")
    expect(fake_sleep.delays == [], f"Expected no backoff sleep on a first-attempt success, got {fake_sleep.delays}")


def test_transient_failure_then_success() -> None:
    """One rate-limit error, then a success -- must retry exactly once
    and return the eventual success's content."""
    with _PatchedClient([_rate_limit_error(), _fake_response_content("recovered")]) as fake_client, \
         _PatchedSleep() as fake_sleep:
        result = pillar_shared.call_analysis_model("system", "user", 0.0)

    expect(result == "recovered", f"Expected the successful retry's content, got {result!r}")
    expect(fake_client.calls == 2, f"Expected exactly 2 calls (1 failure + 1 success), got {fake_client.calls}")
    expect(len(fake_sleep.delays) == 1, f"Expected exactly one backoff sleep, got {fake_sleep.delays}")


def test_retry_exhaustion_raises_the_last_transient_error() -> None:
    """MAX_ATTEMPTS consecutive transient failures must raise (the last
    one), after making exactly MAX_ATTEMPTS calls -- never fewer (giving
    up early) and never more (retrying past the configured bound)."""
    errors = [_connection_error(), _rate_limit_error(), _server_error()]
    expect(
        len(errors) == pillar_shared.MAX_ATTEMPTS,
        "This test's fixture must supply exactly MAX_ATTEMPTS failures to exercise exhaustion precisely",
    )

    with _PatchedClient(list(errors)) as fake_client, _PatchedSleep() as fake_sleep:
        try:
            pillar_shared.call_analysis_model("system", "user", 0.0)
        except openai.InternalServerError:
            pass
        else:
            raise AssertionError("Expected the last transient error to be raised after exhausting all attempts")

    expect(
        fake_client.calls == pillar_shared.MAX_ATTEMPTS,
        f"Expected exactly MAX_ATTEMPTS ({pillar_shared.MAX_ATTEMPTS}) calls, got {fake_client.calls}",
    )
    expect(
        len(fake_sleep.delays) == pillar_shared.MAX_ATTEMPTS - 1,
        f"Expected MAX_ATTEMPTS - 1 backoff sleeps between attempts, got {fake_sleep.delays}",
    )


def test_permanent_failure_is_not_retried() -> None:
    """An authentication failure must raise on the FIRST attempt -- no
    retry, no backoff sleep at all. Proven for two distinct permanent
    classes (auth and bad-request) in one test since the assertion is
    identical for both."""
    for make_error, expected_type in (
        (_auth_error, openai.AuthenticationError),
        (_bad_request_error, openai.BadRequestError),
    ):
        with _PatchedClient([make_error()]) as fake_client, _PatchedSleep() as fake_sleep:
            try:
                pillar_shared.call_analysis_model("system", "user", 0.0)
            except expected_type:
                pass
            else:
                raise AssertionError(f"Expected {expected_type.__name__} to propagate unretried")

        expect(
            fake_client.calls == 1,
            f"Expected exactly 1 call for a permanent {expected_type.__name__} failure, got {fake_client.calls}",
        )
        expect(
            fake_sleep.delays == [],
            f"Expected no backoff sleep for a permanent failure, got {fake_sleep.delays}",
        )


def test_backoff_is_exponential_and_capped_without_real_sleeping() -> None:
    """Three transient failures in a row (== MAX_ATTEMPTS, so the loop
    exhausts without a successful call) must produce exactly
    MAX_ATTEMPTS - 1 sleeps, growing exponentially (INITIAL_BACKOFF_SECONDS,
    then * BACKOFF_MULTIPLIER), each within the documented jitter band --
    with random.random() pinned (via _PatchedSleep), the exact jittered
    value is computable and asserted precisely, not just bounded."""
    with _PatchedClient([_connection_error(), _connection_error(), _connection_error()]) as fake_client, \
         _PatchedSleep(fixed_random=0.5) as fake_sleep:
        try:
            pillar_shared.call_analysis_model("system", "user", 0.0)
        except openai.APIConnectionError:
            pass
        else:
            raise AssertionError("Expected the final connection error to be raised")

    # With random.random() pinned at 0.5, jitter = 1 - JITTER_FRACTION * 0.5
    # is a fixed multiplier -- the exact expected delay for each attempt is
    # therefore fully computable, not just "some value less than the base".
    jitter = 1 - pillar_shared.JITTER_FRACTION * 0.5
    expected_delays = [
        pillar_shared.INITIAL_BACKOFF_SECONDS * jitter,
        min(pillar_shared.INITIAL_BACKOFF_SECONDS * pillar_shared.BACKOFF_MULTIPLIER, pillar_shared.MAX_BACKOFF_SECONDS) * jitter,
    ]

    expect(
        len(fake_sleep.delays) == len(expected_delays),
        f"Expected {len(expected_delays)} backoff sleeps, got {fake_sleep.delays}",
    )
    for actual, expected in zip(fake_sleep.delays, expected_delays):
        expect(
            abs(actual - expected) < 1e-9,
            f"Expected backoff delay {expected!r}, got {actual!r} (exponential growth or jitter formula changed)",
        )
    expect(
        fake_sleep.delays[1] > fake_sleep.delays[0],
        f"Expected the second backoff delay to be strictly larger than the first, got {fake_sleep.delays}",
    )
    expect(fake_client.calls == pillar_shared.MAX_ATTEMPTS, f"Expected {pillar_shared.MAX_ATTEMPTS} calls, got {fake_client.calls}")


def test_no_calls_ever_exceed_max_attempts_even_on_repeated_transient_failure() -> None:
    """A pathological case: far more transient failures are QUEUED than
    MAX_ATTEMPTS ever allows the loop to consume. If the retry loop were
    unbounded, it would exhaust the whole queue; bounded correctly, it
    must stop and raise after exactly MAX_ATTEMPTS calls, leaving queued
    failures untouched."""
    excess_failures = [_connection_error() for _ in range(pillar_shared.MAX_ATTEMPTS + 5)]

    with _PatchedClient(excess_failures) as fake_client, _PatchedSleep() as fake_sleep:
        try:
            pillar_shared.call_analysis_model("system", "user", 0.0)
        except openai.APIConnectionError:
            pass
        else:
            raise AssertionError("Expected a connection error to be raised after exhausting attempts")

    expect(
        fake_client.calls == pillar_shared.MAX_ATTEMPTS,
        f"Expected the loop to stop at exactly MAX_ATTEMPTS ({pillar_shared.MAX_ATTEMPTS}) calls "
        f"regardless of how many failures were queued, got {fake_client.calls}",
    )
    expect(
        len(fake_client._side_effects) == 5,
        f"Expected exactly 5 unconsumed queued failures left over (MAX_ATTEMPTS + 5 queued - "
        f"MAX_ATTEMPTS consumed), got {len(fake_client._side_effects)}",
    )
    expect(
        len(fake_sleep.delays) == pillar_shared.MAX_ATTEMPTS - 1,
        f"Expected exactly MAX_ATTEMPTS - 1 sleeps, got {fake_sleep.delays}",
    )


def test_is_transient_openai_error_classifies_correctly() -> None:
    """Direct classification-table test, independent of the retry loop
    itself -- every failure class this module treats as retryable vs.
    permanent, asserted explicitly."""
    transient = [
        _connection_error(),
        _timeout_error(),
        _rate_limit_error(),
        _server_error(),
        _status_error(openai.ConflictError, 409),
        _status_error(openai.InternalServerError, 503),
    ]
    permanent = [
        _auth_error(),
        _bad_request_error(),
        _status_error(openai.PermissionDeniedError, 403),
        _status_error(openai.NotFoundError, 404),
        _status_error(openai.UnprocessableEntityError, 422),
        ValueError("not an OpenAI error at all"),
    ]

    for error in transient:
        expect(
            pillar_shared._is_transient_openai_error(error),
            f"Expected {type(error).__name__} to be classified transient (retryable)",
        )

    for error in permanent:
        expect(
            not pillar_shared._is_transient_openai_error(error),
            f"Expected {type(error).__name__} to be classified permanent (not retried)",
        )


TESTS = [
    test_successful_first_attempt_makes_exactly_one_call,
    test_transient_failure_then_success,
    test_retry_exhaustion_raises_the_last_transient_error,
    test_permanent_failure_is_not_retried,
    test_backoff_is_exponential_and_capped_without_real_sleeping,
    test_no_calls_ever_exceed_max_attempts_even_on_repeated_transient_failure,
    test_is_transient_openai_error_classifies_correctly,
]


def main() -> None:
    print("\nAI Request Reliability tests")
    print("-" * 72)

    failures: list[str] = []

    for test in TESTS:
        name = test.__name__

        try:
            test()
        except AssertionError as error:
            print(f"FAIL  {name}\n      {error}")
            failures.append(name)
        else:
            print(f"PASS  {name}")

    print("-" * 72)
    print(f"{len(TESTS) - len(failures)}/{len(TESTS)} passed")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
