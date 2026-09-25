# AI Request Reliability

**Added:** Portfolio Release Task 2 (following Task 1, `docs/portfolio/CI.md`).
**Scope:** `app/ai/pillar_shared.py::call_analysis_model()` only — the shared OpenAI call every one of the
six SIE pillar analyses (market, team/founder, product, execution, traction, financial health) goes through
via `app/ai/analyze_pillar.py`. See "What this does *not* cover" below for the parts of the pipeline this
task deliberately left untouched.

## The problem

`call_analysis_model()` previously made exactly one attempt per call, with no retry and no exception
handling of its own:

```python
def call_analysis_model(system_content, user_content, temperature):
    response = client.chat.completions.create(...)
    return response.choices[0].message.content or ""
```

A transient OpenAI failure anywhere in that call — a rate limit, a dropped connection, a slow response, a
momentary 500 — propagated straight up through the pillar's evidence/scoring call, through
`analyze_pillar()`, through `run_due_diligence()`, and failed the **entire six-pillar analysis** (already
several completed, paid LLM calls deep) with a clean but unhelpful `502` (the generic
`except Exception` around `run_due_diligence()` in `app/api.py`). One transient blip anywhere in the
pipeline wasted the whole run and its cost — flagged as a concrete gap in the earlier portfolio audit
(`docs/portfolio/VENTUREGPS_READINESS_AUDIT.md`, §4.3: *"No per-call timeout/retry tuning... A single
transient failure anywhere in the ~20-call chain fails the entire multi-minute, already-expensive
pipeline"*).

## The fix

`call_analysis_model()` now retries **bounded**, with exponential backoff plus jitter, but **only for
genuinely transient failures**:

| Constant | Value | What it bounds |
|---|---|---|
| `MAX_ATTEMPTS` | `3` | 1 initial attempt + up to 2 retries, total |
| `INITIAL_BACKOFF_SECONDS` | `1.0` | Delay before the 2nd attempt (before jitter) |
| `BACKOFF_MULTIPLIER` | `2.0` | Exponential growth factor per retry |
| `MAX_BACKOFF_SECONDS` | `8.0` | Hard cap on any single backoff delay |
| `JITTER_FRACTION` | `0.25` | ±25% randomization applied to each computed delay |
| `CALL_TIMEOUT_SECONDS` | `60.0` | Per-attempt ceiling (was previously the SDK's own 600s default) |

**Worst-case added latency from retrying** (excluding the attempts themselves): two backoff waits at 1s
and 2s (both already under the 8s cap) — at most ~3 seconds of intentional waiting. **Worst-case total time**
if every attempt hangs for the full per-call ceiling before failing: `MAX_ATTEMPTS × CALL_TIMEOUT_SECONDS`
= 180 seconds — small relative to the six-pillar pipeline's own total run time (the real cohort run measured
in the earlier audit was 230.5 seconds for the *entire* ~20-call pipeline; 180s is the worst case for a
single one of those calls retrying to exhaustion, not the expected case).

### What counts as "transient" (retried) vs. "permanent" (fails immediately)

`_is_transient_openai_error()` classifies every OpenAI SDK exception:

| Retried (transient) | Not retried (permanent — fails on the first attempt) |
|---|---|
| `openai.APIConnectionError` (dropped connection, DNS failure) | `openai.AuthenticationError` (401 — bad API key) |
| `openai.APITimeoutError` (a subclass of the above) | `openai.PermissionDeniedError` (403) |
| `openai.RateLimitError` (429) | `openai.NotFoundError` (404) |
| `openai.ConflictError` (409 — lock timeout) | `openai.BadRequestError` (400 — malformed request) |
| Any `openai.APIStatusError` with `status_code >= 500` | `openai.UnprocessableEntityError` (422) |
| Request-timeout responses (408) | Anything that isn't an OpenAI SDK error at all |

This is deliberately the **same set of status codes OpenAI's own client already treats as retryable**
internally (`openai._base_client.BaseClient._should_retry`: 408, 409, 429, 5xx) — no new judgment call about
what's "retryable," just OpenAI's own existing classification, reimplemented in application code so it can
be unit-tested without needing to trigger real HTTP status codes.

**Malformed model *output* (as opposed to a failed API *call*) is never retried by this function, by
construction.** `call_analysis_model()` only ever returns the raw response text or raises an SDK exception —
JSON parsing (`parse_json_from_response`) and evidence-validation/scoped-correction
(`app/ai/evidence_extraction.py`, `app/ai/pillar_scoring.py`) both happen entirely in the *caller*, after
this function has already returned successfully, so they're structurally outside this retry loop. That
existing per-dimension scoped-correction pass remains the *only* mechanism for handling a malformed/invalid
model answer — this task did not touch it, and requirement 2's "do not retry evidence-validation failures
without a separately justified policy" is satisfied by scope, not by an added check.

### Respecting the OpenAI SDK's own existing retry behavior

The OpenAI SDK (`openai==2.37.0`) already retries transient failures internally by default —
`max_retries=2` (i.e. up to 3 total HTTP attempts per logical call), with its own exponential backoff and
jitter (`openai._base_client.BaseClient._calculate_retry_timeout`), for exactly the same status-code set
listed above. Left at that default, the new application-level retry loop would sit *on top of* the SDK's
own — each of our attempts silently triggering up to 3 real HTTP calls of its own, for up to
`MAX_ATTEMPTS × 3` = 9 total requests per logical call, governed by two independent, uncoordinated backoff
schedules.

The `OpenAI` client is now constructed with `max_retries=0`, turning the SDK's own automatic retry **off**.
Retry policy now lives in exactly one place — `call_analysis_model()`'s own loop — which is how this
implementation satisfies "respect existing client retries to avoid multiplying attempts unintentionally":
by ensuring only one retry mechanism is ever active, not by leaving both on.

### What this does *not* cover

This task's scope was explicitly `app/ai/pillar_shared.py::call_analysis_model()` — the function the six
pillar analyses share. Several **other** OpenAI/Tavily calls in the same `run_due_diligence()` pipeline each
construct their **own separate** `OpenAI(...)` client and have **no retry logic of their own**, unchanged by
this task:

- `app/ai/summarize.py`, `app/ai/risk_analysis.py`, `app/ai/memo_generator.py`,
  `app/ai/competitor_anlalysis.py`, `app/ai/structured_analysis.py` — the five narrative/summary calls
  `run_due_diligence()` also makes.
- `app/ai/research_enrichment.py` — both its own OpenAI calls and its Tavily search calls.

A transient failure in any of these still fails the whole analysis on the first attempt, exactly as before
this task. This is a known, deliberately out-of-scope gap, not an oversight — extending the same pattern to
these call sites would be a natural, mechanically similar follow-up (each already has its own
`client = OpenAI(api_key=...)` and its own inline `client.chat.completions.create(...)`, so the same
`_is_transient_openai_error()`/backoff/`max_retries=0` treatment would apply directly), but is not part of
this change.

## Testing

`app/tests/test_ai_request_reliability.py` — 7 new tests, fully offline (no real network/API call), no real
sleeping:

| Test | Proves |
|---|---|
| `test_successful_first_attempt_makes_exactly_one_call` | The common case: one call, no retry, no sleep |
| `test_transient_failure_then_success` | One retryable failure, then success — exactly 2 calls, 1 sleep |
| `test_retry_exhaustion_raises_the_last_transient_error` | `MAX_ATTEMPTS` consecutive failures → the last error raised, exactly `MAX_ATTEMPTS` calls made |
| `test_permanent_failure_is_not_retried` | Auth/bad-request failures raise on attempt 1, zero sleeps |
| `test_backoff_is_exponential_and_capped_without_real_sleeping` | Exact delay values (with `random.random()` pinned), growing exponentially |
| `test_no_calls_ever_exceed_max_attempts_even_on_repeated_transient_failure` | Far more queued failures than `MAX_ATTEMPTS` — the loop still stops exactly at the bound, never exceeds it |
| `test_is_transient_openai_error_classifies_correctly` | Direct classification-table test for every named exception class |

`time.sleep` and `random.random` are monkeypatched at the `app.ai.pillar_shared` module level (the same
manual-patch convention every other test file in this directory already uses, e.g.
`test_website_url_security.py`'s `ws.socket.getaddrinfo`/`ws.urllib3.HTTPSConnectionPool` patches) — no test
in this file waits for real, and backoff delays are asserted as exact computed values, not "eventually small
enough."

### Results (this task, local verification)

- `app/tests/test_ai_request_reliability.py`: **7/7 passed**.
- Relevant existing AI/pillar/scoring tests (21 files, run individually — the ones that actually exercise
  `analyze_pillar()`/pillar analysis/scoring with mocked model calls, most of which mock
  `call_analysis_model()` itself at the *consumer* module level, e.g.
  `patch("app.ai.evidence_extraction.call_analysis_model", ...)`, so this change's own retry logic never
  executes inside them — they simply confirm the change is transparent to every existing caller):
  `test_scoped_correction`, `test_evidence_scoring_pipeline`, `test_evidence_validator`,
  `test_public_evidence_consistency`, `test_sps_v3_adapter`, `test_sps_v3_finalization`,
  `test_methodology_v2_1`, `test_provenance`, `test_scoring_weights`, `test_sie_v2_anchors`,
  `test_sie_v2_customer_demand_lifecycle`, `test_sie_v2_deterministic_integration`,
  `test_sie_v2_evidence_semantics`, `test_sie_v2_methodology`, `test_sie_v2_psc_integration`,
  `test_vps_determinism_and_calibration`, `test_vps_final_integrity_audit`, `test_vps_intelligence_reset`,
  `test_vps_scoring_correctness`, `test_stage_extraction` — **all 21 files pass** (293 individual tests
  total).
- All 105 legacy core-journey tests (`docs/portfolio/CI.md`'s `backend-legacy-core-journey` job: auth,
  unified analyze, unified analyze concurrency, PDF ingestion, website URL security, saved startups,
  security hardening) — **all 105 pass**, unaffected (none of them exercise the pillar-analysis pipeline
  directly).
- **Not run:** `python -m app.calibration.run_calibration` (the scoring-calibration suite) — it makes real,
  paid OpenAI/Tavily calls against benchmark companies, explicitly forbidden by this task's "no real paid AI
  calls during testing" constraint. This change doesn't touch scoring, prompts, or evidence rules (the
  calibration suite's own stated scope — see `app/calibration/README.md`), so it wasn't expected to need
  re-running here regardless.

## Design tradeoffs (explicit)

- **Fixed attempt/backoff constants, not configurable via environment variable.** Simpler, and matches this
  module's existing style (`PILLAR_ANALYSIS_MODEL`, `MAX_PDF_BYTES`, etc. are all fixed module constants,
  not env-configurable). Revisit if real production data ever suggests the bounds need tuning.
- **No `Retry-After` header honoring.** OpenAI's own SDK retry (now disabled here) parses a `Retry-After`
  header on a 429 and waits that long if reasonable (≤60s); this implementation's own backoff is a fixed
  exponential schedule regardless of what the server suggested. Simpler and still bounded, at the cost of
  occasionally retrying a little earlier or later than the server's own hint. A `Retry-After`-aware version
  would be a small, isolated follow-up if real rate-limit-heavy production behavior ever warrants it.
  Kept unimplemented here per "no unrelated complexity."
- **`print()`-based warnings, not the `logging` module.** Matches this exact codebase's existing convention
  for this kind of message — `app/ai/evidence_extraction.py` and `app/ai/pillar_scoring.py` already use
  `print(f"\nWARNING: ...")` for their own scoped-correction failures; introducing Python's `logging` module
  into `app/ai/` here would be an unrelated framework change. Every retry/failure message logs only the
  exception's *type name*, the attempt number, and the computed backoff delay — never `system_content`,
  `user_content`, the API key, or any part of a model response (requirement 5).
- **Narrow scope (this function only), by design.** See "What this does *not* cover" above — extending the
  same treatment to the five narrative-generation calls and to `research_enrichment.py`'s OpenAI/Tavily
  calls is a natural follow-up, not attempted here.
