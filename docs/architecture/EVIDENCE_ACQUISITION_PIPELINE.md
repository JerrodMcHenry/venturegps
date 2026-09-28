# VentureGPS Evidence Acquisition Pipeline (Task 20)

**Status: implemented, offline-tested (22 tests), never executed against a real network or paid
API.** This is the bridge from a raw company identity/website to the canonical `EvidenceLedger`
every one of the six pillars already consumes (Tasks 8-19) — `app/evidence_engine/acquisition/`,
a new subpackage inside the existing isolated evidence engine. **Not production integration** — no
production route, no frontend change, no connection to VentureGPS's existing user-facing reports.

**Task 21 update:** real (but still never-invoked) provider adapters, batching, bounded concurrency,
dedup, and deterministic source-type classification were added on top of this pipeline —
`PROVIDER_ADAPTERS_AND_CALL_BUDGET.md` is the record of that work; this document's own stage-by-stage
description below remains accurate (updated in place at §15/§16 where this task changed the picture) and
is not restated there.

**The one rule this pipeline exists to enforce structurally:** AI helps discover and structure
evidence; deterministic software decides what that evidence means under the methodology. No stage
in this pipeline ever asks a model for a score, a label the methodology doesn't define, or a
subjective quality judgment — extraction produces typed claim *candidates*; grounding validation,
canonical identity, contradiction detection, and ledger construction are all pure, deterministic
Python, exactly the same "AI extracts, code decides" boundary every pillar's own
`classify_with_recovery()`/`extract_with_recovery()` already enforces (Tasks 8-17).

## 1. Pipeline stages

```
1. Input normalization         -- pipeline.py::_normalize_input()          (deterministic)
2. Research planning           -- research_plan.py::build_research_plan()  (deterministic)
3. Source discovery/retrieval  -- pipeline.py::_retrieve_sources()          (SearchProvider / SourceRetriever)
4. Evidence extraction         -- extraction.py::extract_with_recovery()    (EvidenceExtractor)
5. Evidence normalization      -- claim_identity.py::finalize_claim()      (deterministic)
6. Provenance/independence     -- claim_identity.py::compute_independence_group_id()  (deterministic)
7. Contradiction/duplicate     -- contradiction.py::detect_contradictions() (deterministic)
8. Evidence Ledger construction -- EvidenceLedger.from_list()              (existing, unmodified)
9. Stage resolution            -- full_analysis.py::assemble_full_analysis() (existing, unmodified)
10. Six-pillar evaluation      -- (same call)
11. Cross-pillar audit         -- (same call)
12. Company-level Coverage/Confidence/publication -- (same call)
13. Final FullCompanyAnalysis  -- (same call)
```

**Stages 9-13 are not reimplemented.** `full_analysis.py::assemble_full_analysis()` (Tasks 18-19)
already does exactly this, already proven against 357 prior tests and six real companies. This
pipeline's own responsibility ends at producing a correct, canonical `EvidenceLedger`; everything
downstream of that is the existing, unmodified engine, called exactly as every pillar's own
sanity-check script already calls it.

## 2. Typed contracts

All in `acquisition/models.py`:

| Contract | Kind | Purpose |
|---|---|---|
| `CompanyAnalysisInput` | Pydantic | The one supported input: `company_name`, `website_url`, optional `company_ref`/`as_of`. Deliberately narrow (item 3) — no PDF/deck support. |
| `ResearchTopic`, `ResearchQuery`, `ResearchPlan` | Enum / frozen dataclass | The deterministic, bounded research plan (§4). |
| `SearchResult` | Pydantic | One search-engine hit — explicitly NOT yet evidence (item 6). |
| `RetrievedSource` | Pydantic | A source actually fetched and inspected — carries every field spec Part 2.1/2.2 requires a `Claim` to trace back to (URL, publisher, source_type, dates, raw content). |
| `ExtractedClaimCandidate` | Pydantic | What an `EvidenceExtractor` may produce — deliberately NOT a `Claim` yet (must pass grounding validation and identity assignment first). Never carries its own `source_publisher`/`source_type`/dates — those always come from the `RetrievedSource` its `source_id` references, never re-asserted by the model. |
| `ClaimRejectionReason`, `RejectedClaimCandidate` | Enum / dataclass | The five grounding-rejection reasons (§6), each one preserved and countable. |
| `AcquisitionBudget` | frozen dataclass | Every configurable limit item 5 asks for (§5). |
| `AcquisitionTelemetry`, `StageTelemetry`, `ExternalCallRecord`, `AcquisitionQualityFinding` | frozen dataclasses | Observability (§13) and the acquisition-vs-methodology distinction (§14). |

Three Protocols (`acquisition/providers.py`), mirroring `classification.py`'s own
`ClassificationModel`/`ExtractionModel` pattern exactly:

```python
class SearchProvider(Protocol):
    def search(self, query: ResearchQuery) -> tuple[SearchResult, ...]: ...

class SourceRetriever(Protocol):
    def retrieve(self, result: SearchResult, retrieved_at: date) -> RetrievedSource | None: ...

class EvidenceExtractor(Protocol):
    def extract(self, request: ExtractionRequest) -> ExtractionResponse: ...
```

## 3. External I/O boundary

**Every network/model call in this pipeline goes through exactly one of the three Protocols above.**
No domain-logic module (`research_plan.py`, `extraction.py`, `claim_identity.py`,
`contradiction.py`, `pipeline.py`'s own orchestration) imports a search client, an HTTP library, or
a model client directly — item 20's own "keep external I/O at the boundary" instruction, satisfied
structurally, not by convention: `grep -rn "^from app\.\|^import app\." app/evidence_engine/ | grep
-v app.evidence_engine` remains empty after this task (reconfirmed), and a separate check —
`grep -rn "^import requests\|^import httpx\|tavily\|openai" app/evidence_engine/acquisition/*.py`
— finds nothing outside `providers.py`'s own docstring (which only *describes*, never imports, what a
real provider would need).

**No real (networked) provider is implemented in this task.** `providers.py::NotConfiguredProvider`
is the only built-in default anywhere in this package — every one of its three methods raises
`ProviderNotConfiguredError` immediately, so a caller can never mistake "no provider was ever wired
in" for "research found no evidence." §15 describes exactly what a real provider would need to do;
writing that (untested, since no paid call was made this task) implementation is deliberately left
for a future task with explicit approval.

**Item 1's isolation decision, stated explicitly:** `app/website_scrapper.py` and
`app/pdf_extractor.py` are NOT imported here, even though `NEW_ENGINE_ARCHITECTURE.md` Part 2.1
already permits reusing them for the legacy-adjacent Research step. This task instead follows that
same document's OWN precedent for the Tavily step specifically — "modeled on, not importing" — and
applies it uniformly to every external dependency in this pipeline, keeping `acquisition/` inside
the exact same zero-legacy-import boundary the rest of `app/evidence_engine/` already guarantees,
verified by the identical `grep` check used throughout this engine since Task 8. This is the more
conservative choice: it avoids any risk of `website_scrapper.py` itself transitively importing
something from `app.ai`/`app.database` that would silently break the isolation boundary's own
zero-match guarantee.

## 4. Research plan (item 4)

One `ResearchTopic` per pillar (`research_plan.py`), each with a small, fixed table of query
templates and the dimensions each query is intended to support — a direct, reviewable restatement
of spec Part 3.3's own six pillars as a bounded plan, never an LLM-authored "tell me everything"
search:

| Topic | Query templates | Target dimensions |
|---|---|---|
| Product & Technology | "{company} product features integrations"; "{company} review comparison independent" | product_existence_maturity, technical_depth_signal, differentiation_claim_corroboration, defensibility_signal |
| Market & Competition | "{company} market size industry category"; "{company} competitors competitive landscape" | market_definition_size, market_growth_signal, competitive_landscape_position, timing_catalyst |
| Team & Leadership | "{company} founder co-founder background"; "{company} executive team leadership hires" | team_identity, founder_relevant_experience, leadership_composition, public_track_record |
| Traction & Customers | "{company} customers revenue users"; "{company} growth retention case study" | disclosed_scale, customer_base_breadth, growth_trajectory, retention_renewal_signal, commercial_validation |
| Execution & Shipping | "{company} changelog product launch release"; "{company} partnership sales go-to-market" | shipping_velocity, gtm_motion_evidence, strategic_consistency |
| Funding & Financials | "{company} funding round investors raised"; "{company} valuation financials margin" | funding_history, stage_signal, capital_efficiency |

**Deliberately no separate revenue query.** Financial & Funding Signals' own Revenue Disclosure
dimension never independently researches revenue (spec Part 3.1, Task 17) — it reuses whatever
Traction & Customers' own query already discovered, via the automatic cross-pillar tagging rule
in §9.

`build_research_plan()` is a pure function: identical `CompanyAnalysisInput` + `AcquisitionBudget`
always produces an identical plan, truncated to the budget's own limits in the same fixed topic
order every time — never randomly sampled, never LLM-authored.

## 5. Call budgets (item 5)

`AcquisitionBudget` (all fields configurable, defaults shown):

| Field | Default | Governs |
|---|---|---|
| `max_topics` | 6 | How many of the six `ResearchTopic`s are planned at all |
| `max_queries_per_topic` | 2 | Query templates used per topic |
| `max_sources_per_query` | 3 | Search results retrieved per query |
| `max_total_sources` | 24 | Hard ceiling across the entire run, regardless of per-query counts |
| `max_extraction_calls` | 24 | One extraction call per retained source, capped independently |
| `max_extraction_retries` | 1 | Matches `classify_with_recovery()`'s own established retry count |
| `max_search_retries` / `max_retrieval_retries` | 1 each | Bounded, never recursive/unlimited (item 17) |

**Worked maximum external-call shape for one analysis, default budget:** up to **12 search calls**
(6 topics × 2 queries), up to **24 retrieval calls** (bounded by `max_total_sources`, not by
`12 × 3 = 36`), up to **24 extraction (AI) calls** (bounded independently by `max_extraction_calls`).
With retries exhausted in the worst case: up to 24/48/48 respectively. **The AI-call figure (24,
worst case 48) is the one comparable to "the old ~20-call sequential workflow" this task explicitly
warns against** — search and retrieval calls are non-AI (a search API call, an HTTP fetch) and are
budgeted separately for exactly this reason, so a reader comparing "call counts" is comparing the
right thing. This is presented honestly as *comparable to, not dramatically below*, the old
workflow's own AI-call count — a real, known tradeoff (§16), not overstated.

**Concurrency was NOT implemented in this task.** Every stage's own per-item work (each query, each
source, each extraction) is already structurally independent of every other, and nothing in this
design precludes adding bounded concurrent dispatch later — but per item 5's own "do not optimize
prematurely" instruction, and given this task's own isolation-boundary decision not to import the
existing `run_concurrently` utility (§3), this task's own pipeline runs every stage sequentially.
Flagged as a known limitation (§16), not an oversight.

## 6. Evidence-extraction contract and grounding validation (items 8-9)

`ExtractionRequest(source, target_dimensions, company_name) -> ExtractionResponse(candidates)`.
Every `ExtractedClaimCandidate` must pass `extraction.py::validate_candidate()` before it can
become a real `Claim` — the five conditions item 9 lists, each with its own `ClaimRejectionReason`:

| Reason | Condition |
|---|---|
| `NO_SOURCE_ID` | Candidate carries no `source_id` at all |
| `UNKNOWN_SOURCE_ID` | `source_id` does not match any source actually retrieved this run |
| `EMPTY_EXCERPT` | No excerpt, or a blank one |
| `EXCERPT_NOT_GROUNDED_IN_SOURCE` | The excerpt (normalized whitespace/case only — no paraphrase tolerance) is not verbatim-present in the source's own retrieved content |
| `NO_RECOGNIZED_DIMENSION` | `assessment_criteria` names no dimension the methodology actually defines (checked against the same dimension-name set `cross_pillar_audit.py` already builds from `parameters.py`) |
| `MALFORMED_STRUCTURED_FACT` | A `structured_fact` is present but carries no `kind` |

**The grounding rule is not a new, stricter standard invented for this task** — spec Part 2.1
already defined `Claim.excerpt` as "the verbatim source text... never paraphrased." This is that
same, already-approved rule, checked mechanically for the first time because acquisition is the
first place an excerpt is ever machine-proposed rather than human-copied.

`extract_with_recovery()` mirrors `classify_with_recovery()`'s own shape: at most `1 +
max_extraction_retries` calls to the same extractor for the same source, every attempt validated
identically (never relaxed), rejected candidates from the final attempt preserved for telemetry.

## 7. Canonical claim identity and deduplication (items 11-12)

**`claim_id` and `independence_group_id` are two different identities, per spec Part 2.1 (unchanged,
not reinterpreted):**

- `claim_id = hash(normalized_claim_text + source_url)` — inherently per-SOURCE, exactly spec's own
  definition. The same real fact reported by five outlets legitimately produces five different
  `claim_id`s.
- `independence_group_id` — computed by `claim_identity.py::compute_independence_group_id()` from
  the FACT itself (company + `structured_fact.kind` + a per-kind table of normalized identifying
  sub-fields, e.g. `metric`+`period_date` for a `traction_metric`, `round_date`+`financing_type` for
  a `funding_round`), **never from the source URL** (item 11's own explicit instruction). Five claims
  about one real event, from five different sources, all resolve to the SAME `independence_group_id`
  — which is exactly what makes the already-existing, unmodified `resolve_dimension_evidence()`
  (declared-group dedup, spec Part 2.3) and `provenance.py::verify_independence()` (content-based
  safety net, Task 10) work correctly on freshly-acquired evidence with **zero new deduplication
  code** (item 12's own "reuse the existing... logic rather than inventing a parallel system").

A per-kind table (not a generic "hash the whole dict" rule) is used deliberately — a generic hash
would treat two claims differing only in `amount` (the actual point of disagreement contradiction
detection needs to compare, §8) as different facts entirely, defeating both mechanisms at once.

## 8. Contradiction handling (item 13)

`contradiction.py::detect_contradictions()` groups already-finalized claims by `(company_ref,
independence_group_id)` and, for a small table of kinds with a natural comparable value field
(`traction_metric`/`funding_round` → numeric `amount`, tolerance `CONTRADICTION_AMOUNT_TOLERANCE_
PCT = 15.0`; `customer_band`/`capital_efficiency_signal` → categorical `value`), marks genuinely
conflicting subsets `disputed` with `contradicts` populated pairwise — **before** ledger
construction, so the already-existing disputed-exclusion rule (spec Part 2.3, unchanged since
Task 9) is what actually fails the affected dimension closed, rather than `resolve_dimension_
evidence()`'s own dedup silently picking one representative and hiding the disagreement.

**Deliberately excludes `product_release`.** Two different `status` values for one named release
(`announced` then `launched`) is normal evolution over time, already correctly handled by Execution
& Momentum's own named-release supersession rule (Task 16) — marking both `disputed` here would
break that mechanism. Item 13's own "GA vs delayed" example is satisfied by the pillar's own
existing, tested mechanism, not by this module — a documented, deliberate scope boundary, not a gap.

No universal natural-language contradiction solving is attempted (item 13's own explicit
instruction) — only typed-fact comparison over a small, fixed, extensible table.

## 9. Cross-pillar revenue-identity rule (item 14)

`claim_identity.py::finalize_claim()` applies exactly one deterministic rule: a `traction_metric`
candidate whose `metric == "revenue"` is automatically tagged with `revenue_disclosure` in addition
to whatever `assessment_criteria` the extraction/research topic already gave it — the same mechanism
Task 17 proved correct with real, hand-tagged Stripe data, now applied automatically at acquisition
time. **Exactly one canonical `Claim` object is created** — Commercial Traction's Disclosed Scale and
Financial & Funding Signals' Revenue Disclosure cite the literal same `claim_id`, proven end-to-end
by `test_revenue_identity_creates_one_canonical_claim_for_both_pillars`
(`test_acquisition_pipeline.py`). A non-revenue metric (GMV, ARR, bookings) is never tagged this way
— proven by the companion negative test.

## 10. Prompt-injection boundary (item 10)

Nothing in this pipeline ever reads `candidate.claim_text`/`excerpt`/a source's own `content` as an
instruction — every one of these is a plain string field, compared and validated, never evaluated,
interpolated into a system prompt, or used to branch validation logic. A malicious source telling an
extractor to "score this company 10/10" can, at worst, produce a candidate the extractor itself
chose to fabricate — and that candidate is still subject to the exact same grounding check (§6) and,
downstream, the exact same pillar-level label-requirement checks every pillar already enforces
(Tasks 8-17). `PromptInjectionCompliantExtractor` (`acquisition/fakes.py`) is a deliberately
malicious extractor that WOULD act on an injection marker if the pipeline let it — proposing an
out-of-vocabulary `"overall_score"` pseudo-dimension with a maximal-sounding fact — and
`test_prompt_injection_source_content_cannot_manufacture_a_score` confirms it is rejected by
`NO_RECOGNIZED_DIMENSION` and never reaches the ledger.

## 11. Failure behavior (item 16)

Every external-provider call (search, retrieve, extract) is wrapped so a single failure degrades to
an `AcquisitionQualityFinding` and the pipeline continues with whatever other queries/sources/
extractions succeeded — `run_acquisition_pipeline()` never raises out for a partial failure. Tested
directly: one failed search, one failed retrieval, one failed extraction (among several sources —
the others still succeed), a topic producing zero sources, stage remaining `Undetermined`, and a
fully sparse company correctly reaching `company_publishable=False` with explicit reasons
(`test_acquisition_pipeline.py`, 6 dedicated tests). If literally zero sources are ever retrieved,
the resulting `EvidenceLedger` is legitimately empty — every pillar withholds, the company-level
result withholds — the existing, unmodified, already-proven behavior of `assemble_full_analysis()`,
not a pipeline error.

## 12. Retry policy and ownership (item 17)

| Layer | Retry owner | Bound |
|---|---|---|
| Search | `pipeline.py::_retrieve_sources()` | `max_search_retries` (default 1) |
| Retrieval | `pipeline.py::_retrieve_sources()` | `max_retrieval_retries` (default 1) |
| Extraction | `extraction.py::extract_with_recovery()` | `max_extraction_retries` (default 1), validated identically each attempt, never relaxed |

**No layer retries another layer's own already-exhausted attempt** — a failed search is not retried
by re-planning; a failed extraction is not retried by re-searching. Each of the three retry loops
owns exactly one stage, preventing the "multiple layers accidentally multiply retries" failure mode
item 17 explicitly warns against.

## 13. Telemetry (item 18)

`AcquisitionTelemetry` (one per run, `run_id` = a random 12-hex-character identifier — not a secret,
not derived from any company-identifying value) carries: per-stage `StageTelemetry` (name, duration,
a small integer-only detail dict — e.g. `{"sources_retrieved": 7}`); `queries_issued`,
`sources_retrieved`, `claims_extracted`, `claims_rejected`, `claims_deduplicated` (informational —
real dedup happens at scoring time via `independence_group_id`, §7), `claims_disputed`; a tuple of
`AcquisitionQualityFinding`s (§14); and (via `ExternalCallRecord`, currently unpopulated since no
real provider was invoked this task) a slot for per-call type/provider/duration/tokens/cost once a
real provider is wired in. **No secrets, no full raw source content, are ever logged** — `StageTelemetry.
detail` is deliberately typed `dict[str, int]`, structurally incapable of carrying a content string.

## 14. Acquisition quality vs. methodology quality (item 23)

`AcquisitionQualityFinding(stage, description, topic)` is a structured, first-class record —
**never used to justify loosening a publication gate or changing a score mapping.** When a pillar
withholds because research found little, the honest question this pipeline is built to let a human
ask separately is: *did the methodology correctly withhold given genuinely-absent evidence, or did
acquisition fail to find evidence that was actually available?* This task's own offline tests
exercise the SECOND question directly (six dedicated partial-failure scenarios, §11) without ever
touching a single pillar-level parameter to compensate — no gate was loosened, no label mapping was
changed, anywhere in this task.

## 15. Real provider implementations (Task 21 — superseded, kept for history)

**This section originally described what a future task would need to build. That task has happened.**
`app/evidence_engine/acquisition/providers_live.py` now implements all three adapters exactly as
anticipated here (Tavily search, hardened HTTP fetch via `app/website_scrapper.py`, OpenAI structured
extraction) — plus batching, bounded concurrency, deterministic domain-based `source_type` classification,
and stronger structured-extraction validation, none of which this section originally scoped. See
`PROVIDER_ADAPTERS_AND_CALL_BUDGET.md` for the full record: what was reused vs. newly implemented (§1),
each adapter's own responsibilities (§2), and the current implementation-status ledger (§17). **Still true,
unchanged since Task 20:** no test in this repository invokes any of the three against a real endpoint, no
paid call has been made, and no live run has happened — that document's own §15 states exactly what an
explicitly-approved dry run would require.

## 16. Known limitations

Several of Task 20's own original limitations were addressed by Task 21 — see
`PROVIDER_ADAPTERS_AND_CALL_BUDGET.md` §16 for the current, up-to-date list (concurrency now exists; the
extraction-call budget is materially reduced via batching; `source_type` classification is now
implemented, though still genuinely untested against real page content). Still true, unchanged:

- **Contradiction detection's own tolerance (`CONTRADICTION_AMOUNT_TOLERANCE_PCT = 15.0`) is an
  unvalidated placeholder**, deliberately kept identical to `cross_pillar_audit.py`'s own private
  constant (Task 18) for consistency, not because either has been measured against a real corpus.
- **PDF/pitch-deck ingestion is out of scope**, per item 3's own instruction — this pipeline handles
  website/company-name input only.
- **No real cost/token accounting exists yet** — `ExternalCallRecord` now has real fields a real
  adapter populates (`tokens` from OpenAI's own `response.usage`, `cost_usd` only via an explicitly
  supplied `ProviderPricing`), but no test or run has ever exercised this against a real call, so no
  real number exists anywhere in this repository yet (item 19's own "do not invent a cost number").
- **Early stopping remains explicitly deferred** (Task 21 item 11) — judged unsafe to implement
  conservatively within that task's own scope; see `PROVIDER_ADAPTERS_AND_CALL_BUDGET.md` §8.
