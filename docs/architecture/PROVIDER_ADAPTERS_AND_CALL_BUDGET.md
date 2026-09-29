# Provider Adapters & Acquisition Call Budget (Task 21, hardened by Task 21A)

**Status: real (but never-invoked) provider adapters for all three Task 20 Protocols exist
(`app/evidence_engine/acquisition/providers_live.py`), now including a deterministic batch
character-budget enforcer, an explicit OpenAI output-token ceiling, API-enforced JSON-schema
structured output (replacing free-form `.create()` + `json.loads()`), and a single combined
OpenAI retry-attempt owner (worst case cut from 36 to 12 real HTTP attempts). 445 tests across 21
files, all passing against deterministic fakes and mocked SDK clients only. No Tavily call, no
OpenAI call, no live HTTP fetch, and no analysis of a real company was performed or attempted at
any point in either task.**

This document does not restate `EVIDENCE_ACQUISITION_PIPELINE.md` (Task 20's own pipeline-stage
reference, still accurate) or `NEW_ENGINE_E2E_EVALUATION.md` (Task 20's own scenario/readiness
record). Sections 1-9, 11-12, 16-17 below are Task 21's own original record, left as written except
where a cross-reference to §0 was added. **§0 is Task 21A's own addendum** — a read-only preflight
review of Task 21's committed configuration surfaced five concrete provider-boundary gaps (an
unenforced character budget, no output-token ceiling, free-form JSON parsing where the installed
SDK actually supports schema-enforced structured output, and an excessive 36-call retry worst
case); §0 records exactly what changed to close them. §10 (retry ownership), §13 (token/cost
accounting), §14 (call-graph), and §15 (live-run readiness) are updated in place with the new
figures; every other section describes Task 21's original, still-accurate work.

## 0. Task 21A addendum — live-run preflight hardening

A read-only preflight review (no code change, no network call) of the Task 21 configuration as
committed found five gaps worth closing before any live run: (1) a declared but unenforced batch
character budget; (2) no output-token ceiling on the OpenAI request at all; (3) free-form
`.create()` + regex/`json.loads()` parsing where the installed SDK cleanly supports API-enforced
structured output; (4) a 36-real-call worst case per full run from two independently-multiplying
retry layers; (5) no per-batch usage/truncation/attempt telemetry. All five are now fixed,
`app/evidence_engine/parameters.py` (methodology) was not touched, and nothing else about Task 21's
own scope (the 12-query research plan, Tavily configuration, retrieval cap, source prioritization,
source classification, concurrency caps, pillar behavior, publication gates, scoring, or company
aggregation) was changed. Full detail in each updated section below (§10/§13/§14/§15) and item-by-
item in the Task 21A completion report delivered alongside this document.

## 1. Infrastructure inspected and reuse decisions (item 1)

| Existing infrastructure | Inspected | Reuse decision |
|---|---|---|
| `app/website_scrapper.py::extract_text_from_website` | Read in full (335 lines) | **Imported directly.** One of the four architecture-approved legacy imports; SSRF-hardened (DNS-pinned connection, redirect re-validation, size/timeout caps) with nothing to add or weaken. `HttpSourceRetriever` wraps it unchanged. |
| `app/ai/concurrency.py::run_concurrently` | Read in full (64 lines) | **Imported directly**, wrapped by `acquisition/concurrency_helpers.py::run_concurrently_with_containment`. The wrapper exists because `run_concurrently`'s own documented contract is "fails loud, never partial" (correct for its existing legacy callers) -- exactly backwards from this pipeline's own Task 20 graceful-degradation guarantee. Each task callable is wrapped to catch its own exception and return an `Outcome`, so `run_concurrently`'s fail-loud branch never actually triggers; its own deterministic, insertion-order-keyed result shape is otherwise untouched. |
| `app/pdf_extractor.py` | Confirmed present (191 lines), not read in full | **Not used.** `CompanyAnalysisInput` (Task 20 item 3) is deliberately narrow -- company name + website URL only; PDF ingestion stays out of scope, unchanged from Task 20's own decision. |
| `app/auth.py` | Confirmed present (277 lines) | **Not used.** No auth concern exists inside this offline-only, never-invoked adapter layer. |
| `app/ai/research_enrichment.py` (Tavily call shape) | Read (`search_web()`, lines ~120-160) | **Modeled, not imported** -- lives under the forbidden `app.ai.*` umbrella (not one of the four approved exceptions). `TavilySearchProvider` constructs its own `TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))` against the same, already-a-dependency `tavily-python` package, calling `.search(query=..., search_depth="basic", max_results=..., include_answer=False)` -- the same shape, `include_answer` deliberately flipped to `False` (§4 below). |
| `app/ai/pillar_shared.py` (OpenAI client + retry pattern) | Read in full (client construction, `call_analysis_model()`, `_is_transient_openai_error`, `_backoff_seconds`, `MAX_ATTEMPTS=3`, `CALL_TIMEOUT_SECONDS=60.0`, `PILLAR_ANALYSIS_MODEL="gpt-4.1-mini"`) | **Modeled, not imported** -- also outside the four approved exceptions. `OpenAIEvidenceExtractor` reimplements the exact same retry/backoff/transient-classification shape locally (`providers_live.py::_is_transient_openai_error`/`_backoff_seconds`), and reuses the SAME model choice (§6). SDK auto-retry is disabled the same way (`max_retries=0`) for the same documented reason: one retry policy, one place, never two compounding ones. |
| `httpx` (requirements.txt dependency) | Confirmed installed, grepped for existing usage | Not used anywhere in `app/` outside `app/v2/tests` and `app/tests/test_ai_request_reliability.py`; `website_scrapper.py` uses `urllib3` directly instead. No new HTTP client introduced by this task -- `HttpSourceRetriever` uses the existing `website_scrapper.py` fetch path exclusively. |
| `tiktoken` (requirements.txt dependency) | Confirmed installed, grepped for existing usage | Not used anywhere in `app/` (only referenced by `app/v2`'s own architecture-scanner tests, unrelated). No pillar or prior acquisition code tokenizes text. Token/cost accounting here (§9) uses only the REAL `response.usage.total_tokens` OpenAI's own API returns, never a locally-computed token estimate -- item 19's own "no invented numbers" is satisfied without needing `tiktoken` at all. |
| Structured-output helpers (`response_format`/`.parse()`) | Grepped across `app/` | **None exist.** Every legacy AI call (`pillar_shared.py`, `research_enrichment.py`, etc.) uses plain `client.chat.completions.create(...)` and parses `response.choices[0].message.content` as JSON by hand. `OpenAIEvidenceExtractor` follows the same established convention (§5), not a new pattern. |
| Secret handling (`os.getenv("...API_KEY")`) | Grepped across `app/ai/*.py` | Same convention reused exactly: every adapter reads its key via `os.getenv(...)` at construction, accepts an explicit override only for tests, and never logs, prints, or includes a key in any exception message anywhere in `providers_live.py`. |

## 2. The three real adapters (item 2)

All three live in `app/evidence_engine/acquisition/providers_live.py`. Each implements exactly the
Task 20 Protocol it targets (`providers.py`), plus the same small `_CallLogger` composition (a
thread-safe append-only list, drained by `providers.py::drain_call_log()`) so `pipeline.py` can collect
real `ExternalCallRecord`s without depending on any of `providers_live.py`'s own SDK imports (kept in the
neutral `providers.py` module specifically so every offline, fake-only test never has to import
`openai`/`tavily`/`app.website_scrapper` transitively).

- **`TavilySearchProvider`** (`SearchProvider`). Constructs its own `TavilyClient`; maps `results` to
  `SearchResult`s; drops any result missing a `url`; records one `ExternalCallRecord` per call
  (`tokens=None` -- Tavily's search API is not token-metered). Deliberately requests
  `include_answer=False` (§4).
- **`HttpSourceRetriever`** (`SourceRetriever`). Calls `extract_text_from_website(url)` directly; returns
  `None` for empty/whitespace-only content (a genuine "nothing readable" outcome, not an error); truncates
  to `budget.max_chars_per_source`; assigns `source_type` via `source_classification.py` (§7), never from
  the fetched content; never fabricates `published_at` (`extract_text_from_website` exposes no date).
- **`OpenAIEvidenceExtractor`** (`EvidenceExtractor`). Implements both `.extract()` (the required Protocol
  method, delegating to a single-element batch) and `.extract_batch()` (the duck-typed extension
  `extraction.py::extract_many()` looks for -- §3). Builds a fixed system prompt plus one labeled
  `<source>` block per retained source; parses the model's JSON array response into
  `ExtractedClaimCandidate`s, dropping anything schema-invalid or attributed to a source outside the
  batch; records real `tokens` from `response.usage.total_tokens`.

None of the three is invoked by any test in this repository against a real endpoint. Provider-level tests
(`tests/test_provider_adapters.py`, 41 tests) construct each class with a fake API key and replace
`._client` with an in-memory stub after construction (neither SDK's constructor makes a network call --
verified directly against the installed packages before writing these tests), then exercise the adapter's
own logic: response mapping, malformed-input handling, retry classification, telemetry recording.

## 3. Batching (item 6)

**Before:** Task 20's `_extract_claims()` called `extract_with_recovery()` once per retained source -- up
to `budget.max_extraction_calls` (default 24) real extraction calls for a full run.

**After:** retained sources are grouped into fixed-size batches (`budget.max_sources_per_batch`, default
4) and handed to `extraction.py::extract_many()`, which checks whether the extractor exposes an
`extract_batch(requests) -> tuple[ExtractionResponse, ...]` method (duck-typed, not part of the
`EvidenceExtractor` Protocol itself, so every existing fake remains valid and untouched) and, if so, makes
exactly ONE real call per batch instead of one per source. With the defaults above: 24 sources -> 6
batches -> **at most 6 real extraction calls**, a **4x reduction** from Task 20's own worst case, before
any other efficiency measure in this document is even applied.

Source attribution is preserved by construction: the per-batch loop inside `OpenAIEvidenceExtractor.
extract_batch()` (Task 21A: `_schema_candidate_to_extracted()` plus its own `by_source` grouping,
superseding Task 21's original free-form `_parse_batch_response()` once structured output removed the
need for JSON-text parsing, §6a) groups parsed candidates by `source_id`, drops anything whose
`source_id` does not belong to a request in that specific batch (so a model hallucinating or a malicious
page trying to attribute a candidate to a *different* source in the batch is caught the same way
`UNKNOWN_SOURCE_ID` already catches it for a single-source call), and returns one `ExtractionResponse`
per input request in the SAME order as `requests` -- proven end-to-end (not just at the unit level) by
`test_acquisition_efficiency.py::test_batching_preserves_per_source_attribution_with_distinct_facts`,
which runs 4 batched sources each carrying a genuinely distinct fact through the real pipeline and confirms
every fact traces back to its own, correct source URL.

**Retry ownership within a batch (Task 21A item 4):** originally, `extract_many()` owned a grounding-retry
loop calling `extract_batch()` up to twice, each of THOSE calls internally retrying transient failures up
to three more times -- 6 real calls per batch. This is now ONE combined loop entirely inside
`extract_batch()` itself (§10), bounded at 2 real calls per batch regardless of which failure class
(transient or validation) triggered the retry.

**Per-source-failure isolation inside a batch (a real bug found and fixed during this task, not merely
anticipated):** the first version of `extract_many()`'s non-batching fallback path called
`extract_with_recovery()` per request in a plain loop -- if one request's own call raised (a source-level
failure, not a validation rejection), the exception propagated out of the WHOLE batch task, discarding
every sibling source's already-obtained result too. `test_one_failed_extraction_does_not_destroy_other_
sources` (Task 20's own regression test) caught this the first time the full suite was re-run after
batching landed. Fixed by isolating each request's own exception inside the fallback loop and returning it
in a new `errors_by_source: dict[str, Exception]` third return value, so `pipeline.py`'s own per-source
`AcquisitionQualityFinding` recording is unchanged in behavior -- one failed source among several batched
together still degrades gracefully, exactly as Task 20 guaranteed for the unbatched case.

## 4. Query consolidation (item 7)

**Before and after are the same 12 queries** (`research_plan.py::_TOPIC_QUERY_TEMPLATES`, unchanged by
this task -- 6 topics x 2 templates each). This was inspected specifically for this item and found already
consolidated: each topic's own two query templates were designed in Task 20 to surface evidence for
*several* dimensions each (e.g. `"{company} customers revenue users"` targets both `disclosed_scale` and
`customer_base_breadth`), and Funding & Financials already deliberately omits a third, separate revenue
query in favor of the cross-pillar reuse rule (§9 below). No further consolidation was found that would
not measurably reduce recall for a genuinely distinct topic. The one real change in this area is
`TavilySearchProvider`'s own `include_answer=False` (§2) -- not a query reduction, but a per-call payload
reduction: Tavily's synthesized "answer" field is itself an AI summary, not a source-attributed page, and
was never something this engine's own `Claim` model could trace to a real source anyway (spec Part 2.1).
Requesting it would have been pure waste, not evidence.

## 5. Deterministic prioritization and dedup (items 8-9)

New module `acquisition/dedup.py`, wired into `pipeline.py::_retrieve_sources()` in the item-9 order:

1. **`dedup_search_results()`** -- runs ONCE across every query's combined results (not per query),
   collapsing exact duplicate URLs (after normalizing scheme case, trailing slash, and known tracking
   query parameters via `normalize_url()`) and keeping the first (highest-relevance) occurrence. A URL two
   different topic queries both happen to surface now costs one retrieval+extraction slot instead of two.
   `budget.max_sources_per_query` is then re-applied to what survives, so no single query can crowd out
   another's share purely because it had more raw duplicates.
2. **`dedup_retrieved_content()`** -- implemented and unit-tested (`test_provider_adapters.py`, 2 tests)
   but **deliberately NOT wired into the default pipeline**. It collapses byte-identical fetched content
   across different URLs -- which directly conflicts with an already-approved, already-tested spec
   decision: `claim_id` is defined (Part 2.1, Task 20) as inherently per-source, and
   `test_duplicate_syndicated_reporting_does_not_inflate_evidence` exists specifically to prove five
   outlets restating one fact survive to the ledger as five distinct, individually-provenanced claims
   (collapsing only at scoring time, via one shared `independence_group_id`). Wiring content-dedup into
   the default flow would silently destroy exactly that multi-outlet observability. This is a deliberate,
   documented scope decision (`dedup.py`'s own module docstring carries the same reasoning), not an
   oversight -- left available as a utility for a caller who has *already* established out-of-band that
   two specific sources are the same wire copy.

Prioritization itself stays "keep the provider's own relevance order, drop exact duplicates" -- never a
second, independently-invented ranking heuristic (item 8's own "deterministic, not opaque").

## 6. Model decision (item 20)

`EXTRACTION_MODEL = "gpt-4.1-mini"` -- the same model `app/ai/pillar_shared.py::PILLAR_ANALYSIS_MODEL`
already uses for this project's own structured pillar-evidence calls. Not a default-to-cheapest or
default-to-priciest choice: this project has already validated, across five prior scoring-sprint prompt
generations, that this exact model reliably produces schema-conforming JSON from messy source text -- the
extraction task here (read text, propose typed candidates, cite evidence, never score) is materially the
same shape. Using the project's own already-configured convention, rather than picking a new model for one
subsystem, keeps exactly one model-choice decision to reason about cost/quality for across the whole
codebase (item 20's own instruction). `providers_live.py::OpenAIEvidenceExtractor(model=...)` accepts an
override for a future task that wants to benchmark an alternative, but the shipped default is this one,
with this rationale recorded in the module's own docstring.

**Task 21A update:** the call mechanism changed (§below), the model did not. `EXTRACTION_MODEL`
is still `"gpt-4.1-mini"`; `client.chat.completions.parse(model=self._model, ...)` uses the exact
same configured model, just through the structured-output method instead of free-form `.create()`.

## 6a. Structured output mechanism (Task 21A item 3)

**Investigated, implemented, no network call.** Local introspection of the installed `openai==2.37.0`
SDK (confirmed via `inspect`, not the live API) found `client.chat.completions.parse()` available,
accepting a Pydantic model as `response_format` and returning a typed `.message.parsed`, plus two
real, locally-confirmed exception classes for its own documented non-success outcomes:
`openai.LengthFinishReasonError` (output cut off by the token ceiling, §13/§6a below) and
`openai.ContentFilterFinishReasonError` (refused by a content filter). Both are caught inside
`OpenAIEvidenceExtractor._call_once()` and treated as legitimate, telemetry-recorded degradations
(never a crash, never a pointless identical retry), not exceptions that propagate.

`ExtractedClaimCandidate`'s own `structured_fact: dict[str, str] | None` field is NOT directly
usable as a strict-mode schema (a free-form dict has no fixed key set, which OpenAI's strict
structured-outputs mode requires). A narrower, strict-mode-compatible schema
(`_StructuredFactSchema`/`_CandidateSchema`/`_ExtractionResponseSchema`, all in
`providers_live.py`) restates the exact same contract with `structured_fact` as a fixed set of
optional named fields matching `ALLOWED_STRUCTURED_FACT_FIELDS` exactly, converted back into a
real `ExtractedClaimCandidate` (`_schema_candidate_to_extracted()`) before `validate_candidate()`
ever runs -- so downstream grounding validation is completely unaware anything changed.

**What is NOT verified, and why:** whether the OpenAI server actually accepts this schema for
`gpt-4.1-mini` specifically cannot be confirmed without a live call, which this task makes none of.
What IS verified, locally: the installed SDK does not reject the model/parameter combination
client-side, and the schema itself uses only documented Structured-Outputs-compatible constructs.
This is the same category of "cannot verify without a live call" already named in Task 20's own
live-run readiness section, now narrowed to one specific, well-defined question a future approved
dry run would answer directly.

## 7. Deterministic source-type classification (item 13)

New module `acquisition/source_classification.py::classify_source_type(url, company_website_url)`. A pure
function of two URLs -- structurally incapable of reading page content, because it is never given any
(`test_source_type_classification_ignores_page_content_entirely` asserts this against the function's own
signature, not merely by example). Rules, in order: same registered domain as the company -> `COMPANY_
DISCLOSURE` (or `PRODUCT_DOCUMENTATION` for a `docs./developer./help./support./api.` subdomain of it);
known regulator/filing domain -> `PUBLIC_FILING`; known aggregator/directory domain -> `AGGREGATOR_OR_
DIRECTORY`; known open-community domain -> `COMMUNITY_COMMENTARY`; otherwise -> `INDEPENDENT_REPORTING`
(the same conservative default a human pasting a news URL into the legacy pipeline was always making by
hand). `HttpSourceRetriever` calls this and stamps `RetrievedSource.source_type` BEFORE any extraction call
ever runs -- `ExtractedClaimCandidate` (Task 20) has no `source_type` field at all, so a candidate
structurally cannot assert or override one, regardless of what its own source content claims.

**Known limitation, documented rather than silently assumed away:** registered-domain extraction uses a
simple "last two DNS labels" heuristic, not a Public Suffix List -- wrong for a domain like `company.co.uk`
(no current fixture or real cohort company exercises this; `tldextract` would be the fix, not currently a
dependency).

## 8. Early stopping (item 11) -- explicitly deferred

**Not implemented.** Task 20's own `AcquisitionQualityFinding`/coverage-gate machinery already exists, but
using it to stop acquisition EARLY (e.g. "Product & Technology already has enough for a High-confidence
publish, stop researching that topic") was judged unsafe to do conservatively within this task's own scope:
the coverage/gate/confidence thresholds are pillar-evaluation-time concepts computed AFTER a dimension's
full admissible evidence set is known, not signals available mid-acquisition without either (a) re-running
`assemble_full_analysis()` partway through a single company's own research loop (expensive, and a
methodology-adjacent change to when/how those functions are invoked that this task's own item 24
explicitly forbids reasoning about under acquisition-efficiency pressure), or (b) inventing a SEPARATE,
acquisition-only sufficiency heuristic not grounded in the methodology's own definitions -- exactly what
item 11 itself says to avoid ("using only methodology-defined evidence-sufficiency concepts, or explicitly
defer if unsafe"). Deferred, not attempted.

## 9. Bounded concurrency (item 10)

`acquisition/concurrency_helpers.py::run_concurrently_with_containment()` (reusing `app.ai.concurrency.
run_concurrently`, §1) is now used at three points in `pipeline.py`:

| Stage | Bound (budget field, default) | What runs concurrently |
|---|---|---|
| Search | `max_concurrent_searches` (3) | One task per research query |
| Retrieval | `max_concurrent_retrievals` (4) | One task per (deduped) search result |
| Extraction | `max_concurrent_extraction_batches` (2) | One task per extraction batch |

Every bound is explicit and always real -- no unbounded `gather`. Determinism is preserved exactly the
way `run_concurrently`'s own docstring already guarantees: every result list `pipeline.py` builds is
constructed by iterating a FIXED, already-known sequence (`plan.queries`, `bounded_results`, `batches`) and
looking up that sequence's own outcome by key, never by iterating the outcome map itself or appending
inside a concurrently-run task body. `test_acquisition_efficiency.py::
test_sequential_and_concurrent_budgets_produce_identical_results` runs the identical fixture through a
fully-sequential budget (every concurrency cap set to 1) and a fully-concurrent one and asserts identical
`claim_id`s, `company_coverage_pct`, and `company_publishable` -- the specific equivalence test item 18
asks for.

## 10. Retry ownership audit (item 15, revised by Task 21A item 4)

**Task 21's original design had two independently-multiplying layers for extraction** (a
grounding-retry loop in `extract_many()` wrapping a separate transient-retry loop inside
`OpenAIEvidenceExtractor`) -- 2 x 3 = 6 real calls per batch, 36 across 6 batches. Task 21A's own
preflight review flagged this as excessive ("a logical extraction batch should not be able to
silently trigger six provider calls through stacked retry loops unless there is an exceptionally
strong reason") and it was replaced with ONE combined owner:

| Retry class | Owner | Bound |
|---|---|---|
| Search (transient provider failure) | `pipeline.py::_search_one()`, one query's own loop | `budget.max_search_retries` (default 1) => up to 2 attempts/query |
| Retrieval (transient fetch failure) | `pipeline.py::_retrieve_one()`, one source's own loop | `budget.max_retrieval_retries` (default 1) => up to 2 attempts/source |
| Extraction (BOTH transient HTTP failure AND validation/grounding-driven re-attempt, combined) | `providers_live.py::OpenAIEvidenceExtractor.extract_batch()`, ONE loop, the single owner of every real OpenAI HTTP attempt for a batch | `EXTRACTION_MAX_PROVIDER_ATTEMPTS_PER_BATCH = 2` -- covers EITHER failure class, never multiplied by a second independent layer |
| `extraction.py::extract_many()`'s own grounding-retry loop | **Removed for the batch-capable path** -- now calls `extract_batch()` exactly once, re-runs `validate_candidate()` on the result (item 3's own "do not weaken downstream validation"), never loops itself. Still governs the FALLBACK (non-batch-capable) path unchanged, via `budget.max_extraction_retries`. | N/A for the batch path |
| OpenAI SDK's own built-in retry | Explicitly disabled (`max_retries=0`) | N/A -- one retry policy, one place, mirroring `pillar_shared.py`'s own documented reasoning |
| Tavily client's own built-in retry | Not disabled (no equivalent flag exposed by `tavily-python`); `TavilySearchProvider` itself adds no retry of its own | Bounded entirely by `pipeline.py`'s own `_search_one()` retry loop above -- whatever the underlying `requests`-based HTTP call does internally is opaque but still wrapped by exactly one outer bound |

**New formula and worst case:** `6 batches x EXTRACTION_MAX_PROVIDER_ATTEMPTS_PER_BATCH (2) = 12`
real OpenAI HTTP attempts absolute maximum for a full run -- down from 36 (a 3x reduction), directly
verified by `test_openai_extractor_worst_case_matches_the_documented_formula`. Search remains up to
`12 queries x 2 attempts = 24`; retrieval remains up to `24 sources x 2 attempts = 48` (both
unchanged -- Task 21A item 7 explicitly leaves the retrieval cap and Tavily configuration alone).
Recovery is not removed: a genuine transient blip OR a genuinely-correctable grounding issue still
gets one real second chance, within the same small combined budget, per batch --
`test_openai_extractor_transient_failure_then_success_uses_two_attempts` and `..._validation_
failure_then_success_uses_two_attempts` both prove recovery still works; `..._validation_failure_
plus_transient_failure_still_bounded` proves the two failure classes never independently stack past
2 attempts even when a batch hits both in sequence.

## 11. Structured-extraction validation, extended (item 14)

`extraction.py::validate_candidate()` gained two new checks this task, both fed by a single-source-of-truth
vocabulary rather than a second, driftable list:

- **`INVALID_FACT_KIND`** -- `structured_fact.kind` must be one of `claim_identity.py::IDENTITY_KEY_
  FIELDS`'s own 17 keys (made a public name this task specifically so `extraction.py` could import it as
  the one real "known kinds" source of truth, rather than re-deriving a second copy).
- **`DISALLOWED_FACT_FIELD`** -- every OTHER key in `structured_fact` must be one of the 13 value fields
  any pillar in this engine actually reads (`kind`, `amount`, `currency`, `financing_type`, `metric`,
  `named_entity`, `period_date`, `person_id`, `role`, `round_date`, `status`, `value`, `value_type`,
  `topic` -- verified by grepping every `pillars/*.py` file's own `fact.get(...)`/`fact[...]` accesses, not
  assumed). This is what structurally rejects a `"score"`/`"rating"`/`"grade"`/`"confidence"` field even
  though `ExtractedClaimCandidate` already has no top-level score field of its own -- closing the one gap a
  compromised or credulous extractor could otherwise try, by smuggling a score-shaped value inside an
  otherwise-legitimate-looking `structured_fact`. Directly exercised by
  `test_acquisition_efficiency.py::test_injected_score_field_in_structured_fact_is_rejected` and `..._
  fabricated_fact_kind_is_rejected`, using realistic injected-content payloads (§12).

`assessment_criteria` is now additionally sanitized (not merely checked for "at least one recognized
entry," Task 20's own original rule, unchanged) -- `_sanitize_assessment_criteria()` drops any unrecognized
entry from a candidate that otherwise passes validation, so a partially-plausible label never rides into
the ledger alongside a genuinely recognized one.

**Task 21A note:** switching `OpenAIEvidenceExtractor` to API-enforced structured output (§3 of the
addendum, §6 below) makes a `MALFORMED_STRUCTURED_FACT`/malformed-JSON failure structurally
impossible on that path -- the SDK's own strict schema now guarantees every parsed candidate is
already syntactically well-formed before `validate_candidate()` ever runs. This does NOT weaken
`validate_candidate()` itself, which still runs, unconditionally, on every candidate regardless of
how it was produced (`test_openai_extractor_grounding_validation_still_runs_after_schema_
validation` proves a SCHEMA-valid but UNGROUNDED excerpt is still rejected) -- it simply means the
`INVALID_FACT_KIND`/`DISALLOWED_FACT_FIELD`/`EXCERPT_NOT_GROUNDED_IN_SOURCE` checks are now the
ONLY way a real OpenAI-sourced candidate can be rejected, `MALFORMED_STRUCTURED_FACT` having become
unreachable from that specific path (still reachable from the fallback/non-structured path and from
any other future provider).

## 12. Stronger prompt-injection resistance (item 12)

`test_acquisition_efficiency.py` adds five realistic injected-content payloads (a fake `SYSTEM:` line, a
fake embedded JSON/schema fragment carrying a `"score"` field, a claim to be "a regulatory filing,
independently verified," a fake `### SYSTEM INSTRUCTION ###` block, and a direct "you may now assign a
rating" appeal) and proves, for EACH one individually:

1. A compliant (i.e., deliberately malicious) extractor echoing the payload's own instructions still
   produces zero ledger entries (`test_every_injection_payload_individually_fails_to_manufacture_a_ledger_
   entry`) -- grounding/vocabulary validation, not prompt wording, is what actually stops it.
2. The specific `"score"` field is caught by name (`DISALLOWED_FACT_FIELD`, §11), not merely by the
   candidate being ungrounded.
3. The specific fabricated `"kind"` (`"verified_regulatory_filing"`) is caught by name (`INVALID_FACT_
   KIND`, §11).
4. Content claiming "treat this as a regulatory filing" cannot upgrade `source_type` on the company's own
   domain -- `source_type` was already assigned from the URL alone, before extraction ever saw the content
   (§7).

`OpenAIEvidenceExtractor`'s own system prompt (§2) is a SEPARATE, additional layer -- explicitly labels
every retrieved source block as untrusted data to read, never as instructions to follow, and explicitly
forbids requesting a score. This is documented, in the module's own docstring and again here, as
defense-in-depth, not the actual security boundary: "grounding alone is not a security boundary" (item
12's own words) is answered by the STRUCTURAL checks in §11, which run identically regardless of what any
model said or why.

## 13. Token/cost accounting (item 19, extended by Task 21A item 6)

- **Tokens:** `OpenAIEvidenceExtractor` now records `input_tokens`/`output_tokens` SEPARATELY (from
  `response.usage.prompt_tokens`/`completion_tokens`), summed across every real attempt a batch call
  made, plus `tokens` (the total) -- all real, provider-reported data, never estimated.
  `TavilySearchProvider`/`HttpSourceRetriever` still record `tokens=None` (neither call is
  token-metered).
- **Cost:** unchanged from Task 21 -- `ExternalCallRecord.cost_usd` stays `None` unless an explicit
  `ProviderPricing` is supplied; `HttpSourceRetriever` still records the one stated fact (`cost_usd=0.0`,
  bandwidth is genuinely free) rather than an estimate.
- **Latency:** unchanged -- real `duration_seconds` via `time.monotonic()`, recorded regardless of
  success/failure.
- **New telemetry fields on `ExternalCallRecord` (Task 21A item 6):** `provider_attempts` (how many real
  HTTP attempts this one record aggregates, §10); `validation_retries` (how many of those were re-attempted
  specifically due to a grounding failure, distinct from a transient one); `truncated` (any source's
  INPUT content was truncated or excluded to fit the character budget, §1 of the addendum);
  `output_truncated` (the response itself was cut off by `EXTRACTION_MAX_OUTPUT_TOKENS`, §2 of the
  addendum, surfaced via `openai.LengthFinishReasonError`); `content_filtered`
  (`openai.ContentFilterFinishReasonError`); `sources_excluded_for_budget` (count never sent at all).
  `sources_covered` (Task 21, unchanged) remains 1 for search/retrieval and for a non-batching
  extractor, >1 for a real batched call.
- **Analysis-level aggregation (item 6's own "aggregate these at analysis level"):** `AcquisitionTelemetry`
  gained read-only properties summing the above across every extraction call in a run --
  `total_extraction_tokens`/`_input_tokens`/`_output_tokens`, `total_extraction_provider_attempts`,
  `total_extraction_validation_retries`, `extraction_batches_with_input_truncation`/
  `_output_truncation`, `total_sources_excluded_for_budget` -- computed from `external_calls`, not a
  second, separately-maintained running total that could drift from it.

## 14. Call-graph report (item 23, batch/attempt figures revised by Task 21A)

| Provider | Task 20's own worst case | Task 21's worst case | Task 21A's worst case | Reduction driver |
|---|---|---|---|---|
| Tavily search | <=12 | <=12 (unchanged) | <=12 (unchanged) | Query count already consolidated; Task 21A item 7 leaves this alone |
| Website fetch (HTTP) | <=24 | <=24 (unchanged) | <=24 (unchanged) | Task 21A item 7 leaves the retrieval cap alone |
| OpenAI extraction BATCHES | <=24 (one call/source) | **<=6** (`ceil(24/4)`) | <=6 (unchanged -- batch count, not attempts, is untouched) | Batching, `max_sources_per_batch=4` |
| OpenAI extraction real HTTP ATTEMPTS | <=24 | <=36 (2 grounding x 3 transient, stacked) | **<=12** (`6 batches x 2` combined attempts) | Task 21A item 4's single combined retry owner (§10) |

**Expected-normal case** (unchanged reasoning from Task 21, batch-count figures untouched by 21A): a
realistic expected-normal run is closer to 6-10 search calls, 10-18 retrieval calls, and 3-5 extraction
BATCH calls -- an estimate, not a measurement, reasoned from budget arithmetic and Tasks 11-17's own
typical real source-yield-per-query. The corresponding expected-normal real OpenAI HTTP ATTEMPT count is
typically equal to the batch count (1 attempt per batch, since most real batches should succeed on the
first attempt) -- worse only when a batch genuinely needs its one allowed retry.

**Compared to the legacy workflow:** unchanged from Task 21 -- see that section's own reasoning; Task
21A only changed the OpenAI ATTEMPT multiplier, not the batch/query/retrieval counts this comparison is
based on.

## 15. Live-run readiness (item 22 update to `NEW_ENGINE_E2E_EVALUATION.md` §5/§7, revised by Task 21A)

**Still not ready to run -- no credentials, no approval, no attempt.** What changed since Task 21: the
batch character budget is now actually enforced (never silently exceeded); an explicit output-token
ceiling is set (`EXTRACTION_MAX_OUTPUT_TOKENS = 4096`, §2 of the addendum); the extraction call now uses
API-enforced structured output (§6a) rather than free-form JSON parsing; and the worst-case real OpenAI
HTTP attempt count is 12, not 36. What a small, approved live dry run would need is otherwise unchanged
from Task 21:

- `TAVILY_API_KEY` and `OPENAI_API_KEY` set in the environment (never hardcoded).
- Explicit approval, before either key is ever actually used.
- Expected calls for 1-2 real companies, default budget: <=12 Tavily search, <=24 HTTP fetch, <=6 OpenAI
  extraction BATCH calls (<=12 real HTTP attempts including retries, §10), model `gpt-4.1-mini` (§6),
  each request bounded to <=20,000 input characters (§1 of the addendum) and <=4,096 output tokens (§2).
- No cost figure is given beyond the same "token-metered, no invented dollar figure" rule as Task 21 --
  an actual estimate requires either real historical token counts (none exist yet) or an explicitly-
  configured `ProviderPricing`.
- **One additional, still-open question a dry run would specifically answer (§6a):** whether the real
  OpenAI API actually accepts this schema for `gpt-4.1-mini` as structured output, verified so far only
  by local SDK introspection, never a live call.

**This task stops here, before any such call, pending explicit approval -- exactly as Task 20 and Task
21 both did.**

## 16. Known limitations and assumptions awaiting a first real run

Carried forward from `EVIDENCE_ACQUISITION_PIPELINE.md` §16 where still true, updated where this task
changed the picture:

- **Resolved by this task:** "no concurrency" (now bounded concurrency exists, §9); "AI-call budget
  comparable to, not dramatically below, the legacy workflow" (extraction calls now materially lower via
  batching, §14, though search/retrieval call counts are structurally similar by design -- six
  independently-evidence-gated pillars need more distinct research surface area than one generic search).
- **Still open, unchanged:** real-world `source_type` classification is implemented (§7) but genuinely
  untested against real page content -- no live fetch has ever run through it; the registered-domain
  heuristic's `.co.uk`-style limitation (§7) is untested against any real non-`.com` company; the
  contradiction-tolerance parameter (`CONTRADICTION_AMOUNT_TOLERANCE_PCT`, Task 20) remains an unvalidated
  placeholder, unchanged by this task (methodology parameters are explicitly out of scope here, item 24);
  PDF/deck ingestion remains out of scope; early stopping remains explicitly deferred (§8); no real
  cost/token data exists yet -- every figure in §13-15 is either a real-code-path capability description or
  an arithmetic estimate, never a measurement.
- **New assumption this task introduces, awaiting a first real run to confirm:** the OpenAI extraction
  prompt (§2, §12) has never been sent to a real model -- its actual reliability at producing
  schema-conforming, well-grounded candidates from real (messier than any fixture) web page text is
  unverified. `test_provider_adapters.py`'s own mocked tests prove the PARSING/validation code handles
  malformed output correctly; they cannot prove the real model's OUTPUT will usually be well-formed. This
  is exactly the open question §15's own proposed dry run exists to answer.

## 17. Implementation status ledger (this task's own completion-report requirement)

| Component | Status |
|---|---|
| `source_classification.py` | Implemented, unit-tested (9 tests) |
| `dedup.py` | Implemented, unit-tested (6 tests); `dedup_retrieved_content()` deliberately not wired into the default pipeline (§5) |
| `concurrency_helpers.py` | Implemented, unit-tested (3 tests) |
| `providers_live.py` (all 3 adapters) | Implemented, mocked/unit-tested (36 tests, Task 21A: batching/budget/retry/structured-output tests added, old free-form-JSON tests superseded); **never invoked against a real endpoint** |
| `extraction.py` extensions (`INVALID_FACT_KIND`/`DISALLOWED_FACT_FIELD`/`extract_many`/sanitization) | Implemented, tested via `test_provider_adapters.py` and `test_acquisition_efficiency.py` |
| **Batch character-budget enforcement** (Task 21A item 1) | Implemented (`_render_batch_request`/`_allocate_content_budget`), unit-tested (7 tests: never-exceeds-budget, overhead accounting, deterministic truncation, attribution preserved, water-filling redistribution, safe exclusion, telemetry) |
| **Explicit OpenAI output-token ceiling** (Task 21A item 2) | Implemented (`EXTRACTION_MAX_OUTPUT_TOKENS = 4096`, passed as `max_completion_tokens`), tested (`test_openai_extractor_passes_the_explicit_output_token_ceiling`) |
| **API-enforced structured output** (Task 21A item 3) | Implemented (`client.chat.completions.parse()` + typed schema), tested (8 tests); real server-side acceptance for `gpt-4.1-mini` unverified without a live call (§6a) |
| **Single combined OpenAI retry owner** (Task 21A item 4) | Implemented (`EXTRACTION_MAX_PROVIDER_ATTEMPTS_PER_BATCH = 2`), tested (7 tests covering every required failure-combination scenario) |
| **Extraction usage telemetry** (Task 21A item 6) | Implemented (`ExternalCallRecord` extended, `AcquisitionTelemetry` aggregation properties), tested |
| `pipeline.py` batching/concurrency/dedup integration | Implemented; full offline E2E re-verified (22 Task-20 tests unchanged + 9 efficiency tests unchanged) |
| Isolation-boundary AST scanner | Implemented, automated (3 tests) -- previously a manual, per-task-restated check |
| Live provider behavior against real data | **Not yet tested -- no live run performed** (§15/§16) |
