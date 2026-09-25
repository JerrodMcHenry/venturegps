"""
Low-level helpers shared by the evidence-extraction stage
(app/ai/evidence_extraction.py), the scoring stage
(app/ai/pillar_scoring.py), and the orchestrator (app/ai/analyze_pillar.py).

Pulled into its own module so the two pipeline stages can both depend on
it without depending on each other or on the orchestrator, avoiding a
circular import.
"""

import json
import os
import random
import re
import time
from typing import Any

import openai
from dotenv import load_dotenv
from openai import OpenAI

from app.ai.scoring_methodology import SCORING_METHODOLOGY


load_dotenv()

# ---------------------------------------------------------------------------
# Portfolio Release Task 2 -- AI Request Reliability.
#
# call_analysis_model() previously made exactly one attempt: any OpenAI
# failure -- a rate limit, a dropped connection, a slow response, a
# transient 500 -- propagated straight out of this module, through the
# pillar's evidence/scoring call, through analyze_pillar(), through
# run_due_diligence(), and failed the ENTIRE six-pillar analysis (already
# several completed, paid LLM calls deep) with a clean but unhelpful 502
# (app/api.py's own try/except around run_due_diligence()). One transient
# blip anywhere in a ~10-call pipeline could -- and, per the portfolio
# audit, was flagged as likely to -- waste an entire run.
#
# Scope: retries live ENTIRELY inside this one function, around EXACTLY
# the OpenAI request. Nothing upstream changes -- analyze_pillar() and
# run_due_diligence() are untouched, no pillar is ever re-run, and a
# pillar that already completed successfully is never repeated because a
# later pillar's own call needed a retry. JSON parsing
# (parse_json_from_response, below) and evidence-validation/scoped-
# correction (app/ai/evidence_extraction.py, app/ai/pillar_scoring.py)
# both happen entirely OUTSIDE this function's retry loop and are
# unaffected by it -- a malformed model ANSWER is not a failed API CALL,
# and this file has no opinion on it; that is what the existing per-
# dimension scoped-correction pass already exists to handle, and it
# remains the only mechanism that does.
#
# Only genuinely transient failures are retried -- see
# _is_transient_openai_error() below: connection-level failures
# (including timeouts) and server responses OpenAI's own client already
# classifies as retryable (408, 409, 429, any 5xx). Authentication,
# permission, not-found, bad-request, and unprocessable-entity failures
# raise on the FIRST attempt, unretried -- no retry can fix a bad API key
# or a malformed request.
CALL_TIMEOUT_SECONDS = 60.0
MAX_ATTEMPTS = 3  # 1 initial attempt + up to 2 retries -- bounded, small
INITIAL_BACKOFF_SECONDS = 1.0
BACKOFF_MULTIPLIER = 2.0
MAX_BACKOFF_SECONDS = 8.0
# +/- up to 25% jitter around each computed backoff -- enough to
# meaningfully de-synchronize concurrent callers retrying at once, without
# materially changing the bound below.
JITTER_FRACTION = 0.25
# Worst-case ADDED latency from retrying, on top of the attempts
# themselves: two backoff waits, capped at MAX_BACKOFF_SECONDS each
# (their exact values are INITIAL_BACKOFF_SECONDS and
# INITIAL_BACKOFF_SECONDS * BACKOFF_MULTIPLIER = 1s and 2s here, both
# already under the cap) -- at most ~3s of intentional waiting, plus up to
# MAX_ATTEMPTS * CALL_TIMEOUT_SECONDS = 180s if every attempt hangs for
# the full per-call ceiling before failing. Both numbers are small
# relative to the six-pillar pipeline's own total run time (each pillar
# already makes multiple sequential calls; a few pillars retrying at all
# is the expected case, not the norm).
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 429})


def _is_transient_openai_error(error: Exception) -> bool:
    """
    True only for failure classes a retry can plausibly fix.

    - openai.APIConnectionError (and openai.APITimeoutError, a subclass
      of it per the SDK's own hierarchy): no HTTP response was ever
      received at all -- a dropped connection, DNS failure, or a timeout.
    - openai.APIStatusError whose status_code is 408 (request timeout),
      409 (conflict / lock timeout), 429 (rate limit), or any 5xx (server
      error) -- the exact set OpenAI's own client already retries
      internally (openai._base_client.BaseClient._should_retry).

    Everything else is False, in particular every OTHER APIStatusError
    subclass -- AuthenticationError (401), PermissionDeniedError (403),
    NotFoundError (404), BadRequestError (400), UnprocessableEntityError
    (422) -- none of which fall in the retryable status-code set above, so
    none need their own explicit branch. Anything that isn't an OpenAI SDK
    error at all is also False; this function is never even reached for a
    JSON-parsing failure, since that happens in the caller, after this
    function has already returned successfully.
    """
    if isinstance(error, openai.APIConnectionError):
        return True

    if isinstance(error, openai.APIStatusError):
        return error.status_code in _RETRYABLE_STATUS_CODES or error.status_code >= 500

    return False


def _backoff_seconds(attempt_number: int) -> float:
    """
    attempt_number is 1 for the delay before the SECOND attempt, 2 before
    the third, etc. -- never called before the first attempt, which has no
    preceding delay. Exponential, capped at MAX_BACKOFF_SECONDS, then
    jittered by +/- JITTER_FRACTION. Deliberately reimplemented here
    (rather than reusing the OpenAI SDK's own equivalent) since that lives
    on the SDK's internal, non-public base client class.
    """
    base = min(
        INITIAL_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER ** (attempt_number - 1)),
        MAX_BACKOFF_SECONDS,
    )
    jitter = 1 - JITTER_FRACTION * random.random()
    return base * jitter


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    # The SDK itself already retries transient failures internally by
    # default (max_retries=2, its own exponential backoff + jitter -- see
    # openai._base_client.BaseClient._calculate_retry_timeout) for exactly
    # the classes call_analysis_model() below also retries. Left at that
    # default, OUR retry loop would sit ON TOP of it -- each of our
    # attempts silently triggering up to 3 real HTTP calls of its own, for
    # up to MAX_ATTEMPTS * 3 total requests per logical call, with two
    # independent, uncoordinated backoff schedules. max_retries=0 turns
    # the SDK's own automatic retry off so retry policy lives in exactly
    # one place (call_analysis_model()'s own loop below) -- this is how
    # this file "respects" the SDK's existing retry behavior: by not
    # letting it compound with a second one, not by leaving both active.
    max_retries=0,
    # A single attempt's own ceiling, deliberately far below the SDK's
    # 600-second default read timeout -- a pillar's evidence/score call
    # returns one bounded JSON object, not a long completion. Failing a
    # hung attempt at CALL_TIMEOUT_SECONDS (as an openai.APITimeoutError,
    # one of the transient classes retried below) costs far less of the
    # analysis's total time budget than letting a single stuck attempt run
    # for up to ten minutes.
    timeout=CALL_TIMEOUT_SECONDS,
)
# ---------------------------------------------------------------------------


# Provenance constants (SIE Scoring Reliability sprint, Phase 5; kept
# here as the single source of truth after the Evidence/Scoring
# Separation sprint split analyze_pillar.py into multiple files).
#
# PILLAR_ANALYSIS_MODEL is the model every pillar-pipeline call actually
# uses -- stamped onto every new analysis's analysis_context.model_identifier.
#
# PILLAR_PROMPT_VERSION identifies the current prompt architecture.
# Bumped for this sprint since the pipeline is now two stages instead of
# one, a materially different prompt shape from v1.0.
PILLAR_ANALYSIS_MODEL = "gpt-4.1-mini"
# Bumped for Methodology V2.1 (Phase 10.8B): the scoring-stage prompt rules
# changed materially (the "do not lower a score for sparse evidence" rule
# was removed and replaced -- see app/ai/pillar_scoring.py), and evidence
# extraction is now followed by a deterministic provenance guard
# (app/ai/evidence_provenance.py). See docs/validation/
# SPS_METHODOLOGY_V2_1_CHANGELOG.md.
PILLAR_PROMPT_VERSION = "2.1"


# Deterministic terms indicating the supplied company information likely
# contains a concrete, disclosed quantitative or operational signal.
# Used only to decide whether an Inferred or Private dimension marked
# Unavailable deserves a second look via scoped correction -- never to
# assign a score or evidence_status directly. See
# app/ai/evidence_extraction.py::validate_dimension_evidence.
QUANTITATIVE_DISCLOSURE_TERMS = (
    "arr",
    "burn",
    "cac",
    "cash",
    "churn",
    "customer concentration",
    "customers",
    "funding",
    "gross margin",
    "grr",
    "ltv",
    "margin",
    "mrr",
    "nrr",
    "raised",
    "retention",
    "revenue",
    "runway",
    "series a",
    "series b",
    "series c",
    "shipped",
)


def call_analysis_model(
    system_content: str,
    user_content: str,
    temperature: float,
) -> str:
    """
    Make one model call and return response text.

    Retries up to MAX_ATTEMPTS times total, with exponential backoff plus
    jitter, but ONLY for genuinely transient failures (see
    _is_transient_openai_error above) -- authentication, permission,
    not-found, bad-request, and unprocessable-entity failures raise
    immediately on the first attempt, unretried. See the "Portfolio
    Release Task 2" comment above this function for the full design
    record and the client construction's own comment for why the SDK's
    own automatic retry is disabled in favor of this loop.

    Never logs system_content, user_content, the API key, or any part of
    a model response -- only the failure class name, attempt number, and
    computed backoff delay, and only on a retry or a final failure.
    """
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.chat.completions.create(
                model=PILLAR_ANALYSIS_MODEL,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                ],
                temperature=temperature,
            )

            return response.choices[0].message.content or ""
        except Exception as error:  # noqa: BLE001 -- classified immediately below, never swallowed
            last_error = error

            if not _is_transient_openai_error(error):
                print(
                    f"WARNING: call_analysis_model: permanent failure "
                    f"({type(error).__name__}), not retrying."
                )
                raise

            if attempt == MAX_ATTEMPTS:
                print(
                    f"WARNING: call_analysis_model: exhausted {MAX_ATTEMPTS} attempts, "
                    f"last failure {type(error).__name__}."
                )
                raise

            delay = _backoff_seconds(attempt)
            print(
                f"WARNING: call_analysis_model: transient failure "
                f"({type(error).__name__}) on attempt {attempt}/{MAX_ATTEMPTS}, "
                f"retrying in {delay:.2f}s."
            )
            time.sleep(delay)

    # Unreachable: every path through the loop above either returns or
    # raises (the last iteration always does one or the other). Kept as a
    # defensive fallback, not a real code path, so this function's return
    # type stays honest even if MAX_ATTEMPTS were ever misconfigured to 0.
    raise last_error or RuntimeError("call_analysis_model: no attempt was made.")  # pragma: no cover


def parse_json_from_response(content: str) -> dict[str, Any]:
    """
    Parse a JSON object from a model response.

    The model is instructed to return JSON only, but this fallback
    handles responses that accidentally include surrounding text.
    """
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", content, re.DOTALL)

    if not match:
        raise ValueError("No JSON object found in model response.")

    return json.loads(match.group(0))


def get_methodology_by_name(pillar: str) -> dict[str, Any]:
    """Return the configured scoring dimensions indexed by dimension name."""
    return {
        dimension.name: dimension
        for dimension in SCORING_METHODOLOGY.get(pillar, [])
    }
