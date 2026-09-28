# Provider Adapters & Acquisition Call Budget (Task 21)

**Status: real (but never-invoked) provider adapters for all three Task 20 Protocols now exist
(`app/evidence_engine/acquisition/providers_live.py`), plus batching, dedup, deterministic source-type
classification, bounded concurrency, and stronger structured-extraction validation on top of Task 20's
pipeline. 91 new tests (53 provider/isolation/efficiency tests below + extended `test_acquisition_
pipeline.py` coverage), 432 total across 21 files, all passing against deterministic fakes and mocked
SDK clients only. No Tavily call, no OpenAI call, no live HTTP fetch, and no analysis of a real company
was performed or attempted at any point in this task.**

This document does not restate `EVIDENCE_ACQUISITION_PIPELINE.md` (Task 20's own pipeline-stage
reference, still accurate and updated in place where this task changed a stage's shape) or
`NEW_ENGINE_E2E_EVALUATION.md` (Task 20's own scenario/readiness record, superseded only in its §5/§7
live-run figures, updated there). This document covers what is genuinely new: the three real adapters,
the efficiency work around them, and the call-graph/model/readiness accounting item 21's own instructions
require.

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

Source attribution is preserved by construction: `_parse_batch_response()` groups parsed candidates by
`source_id`, drops anything whose `source_id` does not belong to a request in that specific batch (so a
model hallucinating or a malicious page trying to attribute a candidate to a *different* source in the
batch is caught the same way `UNKNOWN_SOURCE_ID` already catches it for a single-source call), and returns
one `ExtractionResponse` per input request in the SAME order as `requests` -- proven end-to-end (not just
at the `extract_many()` unit level) by
`test_acquisition_efficiency.py::test_batching_preserves_per_source_attribution_with_distinct_facts`,
which runs 4 batched sources each carrying a genuinely distinct fact through the real pipeline and confirms
every fact traces back to its own, correct source URL.

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

## 10. Retry ownership audit (item 15)

| Retry class | Owner | Bound |
|---|---|---|
| Search (transient provider failure) | `pipeline.py::_search_one()`, one query's own loop | `budget.max_search_retries` (default 1) => up to 2 attempts/query |
| Retrieval (transient fetch failure) | `pipeline.py::_retrieve_one()`, one source's own loop | `budget.max_retrieval_retries` (default 1) => up to 2 attempts/source |
| Extraction grounding-only retry (candidate proposed but ungrounded) | `extraction.py::extract_with_recovery()` / `extract_many()`'s batch branch | `budget.max_extraction_retries` (default 1) => up to 2 attempts/source-or-batch |
| OpenAI transient HTTP failure (connection/timeout/429/5xx) | `providers_live.py::OpenAIEvidenceExtractor._call_with_retry()`, its own internal loop, BELOW the grounding-retry layer above | `EXTRACTION_MAX_ATTEMPTS = 3` (1 + 2), independent of the grounding-retry count |
| OpenAI SDK's own built-in retry | Explicitly disabled (`max_retries=0`) | N/A -- one retry policy, one place, mirroring `pillar_shared.py`'s own documented reasoning |
| Tavily client's own built-in retry | Not disabled (no equivalent flag exposed by `tavily-python`); `TavilySearchProvider` itself adds no retry of its own | Bounded entirely by `pipeline.py`'s own `_search_one()` retry loop above -- whatever the underlying `requests`-based HTTP call does internally is opaque but still wrapped by exactly one outer bound |

**Worst-case real external attempts for one company, default budget:** search up to `12 queries x 2
attempts = 24`; retrieval up to `24 sources x 2 attempts = 48`; extraction up to `6 batches x 2 grounding
attempts x 3 OpenAI-transient attempts = 36` (in practice far lower -- the 3-attempt OpenAI retry only
fires on an actual transient HTTP failure, not on every call). No retry class is multiplicatively stacked
with another beyond what this table states explicitly.

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

## 13. Token/cost accounting (item 19)

- **Tokens:** `OpenAIEvidenceExtractor` records `response.usage.total_tokens` -- real, provider-reported
  data, never estimated. `TavilySearchProvider`/`HttpSourceRetriever` record `tokens=None` (neither call is
  token-metered).
- **Cost:** `ExternalCallRecord.cost_usd` stays `None` by default. `providers_live.py::ProviderPricing` is
  an OPTIONAL, explicitly-constructed dataclass (`tavily_cost_per_search_usd`, `openai_cost_per_input_
  token_usd`, `openai_cost_per_output_token_usd`) a caller may pass to any adapter; if supplied, a labeled
  ESTIMATE is computed from real call/token counts. No price is hardcoded anywhere in this codebase, and no
  adapter invents a cost figure when `pricing` is left unset (`HttpSourceRetriever` is the one exception:
  `cost_usd=0.0`, not `None`, because bandwidth cost genuinely is zero-dollar for this engine's purposes --
  a stated fact, not an estimate).
- **Latency:** every adapter measures its own real wall-clock `duration_seconds` via `time.monotonic()`
  around the actual call, recorded on every `ExternalCallRecord` regardless of success/failure.
- **`sources_covered`** (new field on `ExternalCallRecord`): 1 for search/retrieval and for a
  non-batching extractor, >1 for a real batched `OpenAIEvidenceExtractor` call -- so a call-graph report
  built from real telemetry can honestly state "N calls covering M sources" rather than assuming
  one-call-per-source always holds.

## 14. Call-graph report (item 23)

| Provider | Task 20's own worst case | This task's worst case (default budget) | Reduction driver |
|---|---|---|---|
| Tavily search | <=12 | <=12 (unchanged) | Query count was already consolidated (§4); no further reduction found without losing recall |
| Website fetch (HTTP) | <=24 | <=24 (unchanged) | Retrieval is inherently one fetch per distinct retained source; dedup (§5) reduces which sources get this far, not the per-source cost once retained |
| OpenAI extraction | <=24 | **<=6** (`ceil(24 / 4)`) | Batching (§3), default `max_sources_per_batch=4` |

**Expected-normal case** (a real company with typical result density, not the worst case above): search
and retrieval both frequently terminate early via `budget.max_total_sources` (24) before exhausting every
query's own `max_sources_per_query`; cross-query URL dedup (§5) typically removes some overlap between
topics researching a related fact (e.g. funding and stage-signal queries both surfacing a TechCrunch
funding article); extraction batches at less-than-maximum size whenever fewer than 24 sources survive
retrieval. A realistic expected-normal run is closer to 6-10 search calls, 10-18 retrieval calls, and 3-5
extraction calls -- an estimate, not a measurement (§16's own "no real run happened" caveat applies here
too), reasoned from the budget arithmetic and the historical live-evidence sanity checks' own typical
source-yield-per-query observed across Tasks 11-17's real research (never more than 3-5 genuinely useful
sources per query in practice).

**Compared to the legacy workflow** (`app/workflows/due_diligence_workflow.py`, pre-existing, unchanged):
that pipeline made a fixed ~4 Tavily searches (one generic query enriching all six pillars at once) plus
~11 OpenAI calls (six pillar analyses + five free-form summary/risk/memo/competitor/structured calls) per
company -- roughly 4 search + 11 model calls total, always, regardless of company complexity. This engine's
acquisition layer is NOT trying to undercut that count; it is trying to support six independently
evidence-gated pillars with dimension-level traceability the legacy single-generic-search design
structurally cannot provide, at a call count in the same order of magnitude (this task's own realistic
expected-normal figures above) rather than the naive 12+24+24 worst case Task 20 first estimated.

## 15. Live-run readiness (item 22 update to `NEW_ENGINE_E2E_EVALUATION.md` §5/§7)

**Still not ready to run -- no credentials, no approval, no attempt.** What changed since Task 20: real
adapter code now exists (§2) and is unit/mock-tested (§2, §11, §12); a live run's cost/latency/token
envelope can now be stated with real code behind it rather than only Protocol shape. What a small, approved
live dry run would need:

- `TAVILY_API_KEY` and `OPENAI_API_KEY` set in the environment (never hardcoded -- §1's own secret-handling
  discipline, unchanged).
- Explicit approval, per this task's own standing scope constraint, before either key is ever actually
  used.
- Expected calls for 1-2 real companies, default budget: <=12 Tavily search, <=24 HTTP fetch (free,
  bandwidth-only, but real external traffic to third-party sites), <=6 OpenAI extraction calls, model
  `gpt-4.1-mini` (§6). Retry envelope per §10's own table.
- No cost figure is given here beyond "OpenAI: token-metered, roughly 6 calls x prompt-plus-up-to-4-sources
  (<=6000 chars each, §16) plus completion" -- an actual dollar estimate requires either real historical
  token counts (none exist yet) or an explicitly-configured `ProviderPricing` the person running the dry
  run would supply, per item 19's own "never invent a cost figure" rule, unchanged from §13 above.

**This task stops here, before any such call, pending explicit approval -- exactly as Task 20 did.**

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
| `providers_live.py` (all 3 adapters) | Implemented, mocked/unit-tested (23 tests); **never invoked against a real endpoint** |
| `extraction.py` extensions (`INVALID_FACT_KIND`/`DISALLOWED_FACT_FIELD`/`extract_many`/sanitization) | Implemented, tested via both `test_provider_adapters.py` and the extended `test_acquisition_efficiency.py` |
| `pipeline.py` batching/concurrency/dedup integration | Implemented; full offline E2E re-verified (22 Task-20 tests unchanged + 9 new efficiency tests) |
| Isolation-boundary AST scanner | Implemented, automated (3 tests) -- previously a manual, per-task-restated check |
| Live provider behavior against real data | **Not yet tested -- no live run performed** (§15/§16) |
