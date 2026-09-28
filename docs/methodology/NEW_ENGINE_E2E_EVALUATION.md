# VentureGPS Evidence Engine — End-to-End Acquisition Evaluation (Task 20)

**Status: 22 offline end-to-end tests, all passing, against deterministic fakes only. No live run
was performed — see §5 for the readiness assessment and exactly what approval would be needed
before one could happen.** This document does not rewrite `NEW_ENGINE_FULL_EVALUATION.md` or
`NEW_ENGINE_CALIBRATION_RESULTS.md` — those remain the record of the six-pillar engine's own
cohort evaluation and calibration analysis, unaffected by this task (no pillar file was touched;
see §4).

## 1. What was tested and why

`test_acquisition_pipeline.py` runs the REAL pipeline code
(`pipeline.py::run_acquisition_pipeline`) end-to-end — input → research plan → search → retrieval →
extraction → grounding validation → canonical claim construction → contradiction detection → ledger
→ `assemble_full_analysis()` → a real `FullCompanyAnalysis` — against deterministic, offline fakes
(`acquisition/fakes.py`). Nothing here re-tests any individual pillar's own dimension-level scoring
logic (357 prior tests already do that); this suite tests only what is genuinely new: can the
acquisition layer construct a *correct* ledger from raw, untrusted, sometimes-failing external
input, and does that ledger drive the existing engine to the same honest results it always has.

## 2. Scenarios (item 21's own required list) and results

| # | Scenario | Result |
|---|---|---|
| 1 | Evidence-rich fixture (Product & Technology + Funding, 3 claims from 2 sources) | Product & Technology publishes (`test_evidence_rich_fixture_multiple_pillars_publish`) |
| 2 | Sparse private startup (1 claim, 1 source) | ≤1 pillar published; every withheld pillar carries `strength=None`; company-level withholds (`test_sparse_fixture_most_pillars_withhold_none_fabricated`) |
| 3 | Contradictory fixture ($2M vs $9M revenue, same period, two sources, two different pillars' own tags) | Both claims marked `disputed`/`contradicts`; Disclosed Scale correctly `Unscored`, not the larger figure; zero cross-pillar audit `ERROR`s (`test_contradictory_fixture_reaches_ledger_and_audit_correctly`) |
| 4 | Duplicate/syndicated fixture (5 outlets, 1 real $500K round) | 5 distinct `claim_id`s (spec Part 2.1's own per-source rule) but exactly 1 shared `independence_group_id`; Funding History totals $500K (`SMALL`), never $2.5M (`test_duplicate_syndicated_reporting_does_not_inflate_evidence`) |
| 5 | Prompt-injection fixture (`SYSTEM OVERRIDE` text, a malicious extractor that would comply) | Zero claims reach the ledger; the injected candidate is counted `rejected`, never silently dropped; company-level result honestly withholds (`test_prompt_injection_source_content_cannot_manufacture_a_score`) |
| 6 | Partial-failure fixture (failing search / failing retrieval / one-of-two extractions failing / a zero-result topic) | Four dedicated tests; the surviving evidence is always still used; failures are recorded as `AcquisitionQualityFinding`s, never raised out of the pipeline |
| 7 | Revenue-reuse fixture (one revenue claim, two consuming pillars) | Exactly 1 `Claim` object; `assessment_criteria` auto-tagged with both `disclosed_scale` and `revenue_disclosure`; both pillars cite the literal same `claim_id` (`test_revenue_identity_creates_one_canonical_claim_for_both_pillars`); a non-revenue metric (GMV) is confirmed NOT auto-tagged this way (companion negative test) |
| 8 | Identity invariance ("FamousCo" vs. "ObscureCo," identical evidence shape) | Identical `Strength` and identical `company_coverage_pct` regardless of company name (`test_identity_invariance_company_name_does_not_change_results`) |

**Additional coverage beyond item 21's own list**, directly required by other task items:

- Grounding rejection: unsupported excerpt, unrecognized dimension, reference to a nonexistent
  source (3 tests, item 9).
- Budget enforcement: research-plan topic/query truncation, total-source ceiling across queries
  (2 tests, item 5).
- Extraction recovery: a deliberately-ungrounded first attempt, corrected on retry (item 17).
- Canonical independence-group-id determinism: the same fact from two candidates produces the same
  group id; two different periods produce two different group ids (2 tests, item 11).
- Stage resolution honestly reaching `Undetermined` when no stage signal was discovered (item 15).

## 3. Exact test results

**22 new tests, `test_acquisition_pipeline.py`, all passing.**

**Full regression: 379 tests across 18 files, all passing** (357 prior + 22 new). Legacy regression
(`test_ai_request_reliability.py` 7/7, `test_analyze_unified_concurrency.py` 2/2) and the isolation
boundary (zero imports outside `app.evidence_engine` anywhere in the package, including the new
`acquisition/` subpackage) were both reconfirmed. All six pillars' own real sanity-check scripts
were re-run and reproduce their exact historical `Strength` values unchanged (8.0, 6.2, 6.79, 7.25,
5.92, 8.0).

## 4. Changes to existing engine behavior

**None.** No pillar file (`pillars/*.py`), no `scoring.py`, `confidence.py`, `stage.py`,
`provenance.py`, `ledger.py`, `classification.py`, `cross_pillar_audit.py`, or `full_analysis.py`
was modified. The only change to a previously-existing file is one additive constant in
`parameters.py` (`CONTRADICTION_AMOUNT_TOLERANCE_PCT`, used only by the new
`acquisition/contradiction.py` module) plus the version bump every task in this engine's own history
has made. `pipeline.py` *calls* `full_analysis.py::assemble_full_analysis()` exactly as every prior
sanity-check script already has — it does not alter it.

## 5. Live-run readiness assessment (item 22)

**The offline pipeline is structurally ready. No live call was made or attempted this task.**

### What is ready

- The full stage sequence (input → ledger → six-pillar evaluation → `FullCompanyAnalysis`) runs
  correctly end-to-end against deterministic fakes, with 22 tests covering the scenarios item 21
  requires.
- Every external-I/O boundary is a Protocol (`SearchProvider`/`SourceRetriever`/`EvidenceExtractor`)
  — a real provider only needs to implement three small interfaces, described concretely in
  `EVIDENCE_ACQUISITION_PIPELINE.md` §15, to slot into the identical pipeline code path already
  tested here.
- Budgets, retries, grounding validation, contradiction detection, and failure containment are all
  already real, tested code — a live run would exercise the SAME logic paths these 22 tests already
  exercise, just with real data on one side of each Protocol boundary instead of a fake.

### What is NOT ready, and why no live call was made

- **No real `SearchProvider`/`SourceRetriever`/`EvidenceExtractor` implementation exists.**
  `providers.py::NotConfiguredProvider` is the only built-in default, and it raises immediately by
  design. Building a real one requires: a Tavily API key and a paid Tavily call per query; an HTTP
  fetch per retrieved source (free, but real, external, uncontrolled traffic to third-party sites);
  and a paid OpenAI structured-extraction call per retained source.
- **This task was explicitly instructed not to make paid API calls without approval** (items 22/27).
  Tavily and OpenAI are both paid, configured providers for this project (per `CLAUDE.md`'s own
  `.env` requirements, `OPENAI_API_KEY`/`TAVILY_API_KEY`) — there is no free-tier path available that
  this task can verify is genuinely zero-cost, so per item 22's own "do not assume an API is free,"
  no live call was attempted.

### What a small, approved live dry run would look like

If explicitly approved, a minimal live run against 1-2 real companies (reusing the exact same
`run_acquisition_pipeline()` entry point, with real providers substituted for the fakes) would
invoke, per company, at the pipeline's own default budget:

| Provider | Calls | Cost driver |
|---|---|---|
| Tavily search | up to 12 | Paid, per-query |
| Website fetch (HTTP) | up to 24 | Free (bandwidth only), but real external traffic |
| OpenAI extraction | up to 24 | Paid, per-source, token-metered |

**What we would expect to measure:** whether real search results yield retrievable, gradeable
sources; whether a real extraction call reliably produces grounded, correctly-vocabularied
candidates (or how often grounding validation correctly rejects a real hallucination); whether the
resulting `FullCompanyAnalysis` for a real company looks like a plausible, honest reflection of
what public research actually supports (not compared against a target score — per this engine's own
standing "no reputation-based calibration" rule, unchanged); and real `ExternalCallRecord` data
(actual token counts, actual latency) to replace this document's own budget-based estimates.

**This task stops here, before any such call, pending explicit approval.**

## 6. Known acquisition limitations

Carried forward from `EVIDENCE_ACQUISITION_PIPELINE.md` §16 — no concurrency; the AI-call budget is
comparable to, not dramatically below, the legacy workflow's own call count; real-world `source_type`
classification is untested; the contradiction-tolerance parameter is an unvalidated placeholder;
PDF/deck ingestion is out of scope; no real cost/token data exists yet to populate telemetry.

## 7. Whether the pipeline is ready for explicit approval of a small live evaluation

**Yes, contingent on that explicit approval and on the three real provider implementations being
written first** (§5 — none exist yet; this task deliberately did not write them, since writing
untested networked code with no way to verify it in this session was judged a worse outcome than
leaving the Protocol boundary ready for a task that can actually exercise it). The offline
architecture itself needs no further change to support that next step.
