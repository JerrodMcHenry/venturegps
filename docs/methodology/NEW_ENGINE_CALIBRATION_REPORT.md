# VentureGPS Evidence Engine — Product & Technology Calibration Report

**Task 9, updated by Task 10 (Part 10 below).** Companion to `docs/methodology/
NEW_ENGINE_CALIBRATION.md` (the plan). This is the report: what was actually run, against what
fixtures, what it showed, and exactly which parameters remain provisional pending a real, larger
calibration cohort. Parameters below reflect `evidence_engine.v1-provisional-2` (Task 9); Part 10
covers what Task 10 changed (`-provisional-3`: provenance-verified corroboration counting,
classification recovery) and reviews the stage-tiered tables' own rationale as instructed.

**No company in this report has a predetermined target score.** What follows for each company
is: coverage, confidence, scoreability, the actual (provisional-parameter) scores produced, and
— for every withheld dimension — the specific, honest reason. Read a low or withheld result as
"this is what the mechanism produced against these parameters and this evidence," never as "this
company is weak."

## 1. Fixture roster (5 companies, up from 3)

| Company | Real/fictional | Stage (determined, not asserted) | Purpose |
|---|---|---|---|
| Notion | Real | Growth (round-type signal: "growth-stage financing") | Fully scorable, established-tier baseline |
| Linear | Real | Series B+ (round-type signal: "Series B") | Partially scorable, thinner real public footprint |
| Pathlight | Fictional | Pre-Seed (founding-year fallback: 2024) | Sparse-but-real early-stage evidence; the stage-sensitivity comparison case |
| DupliCo | Fictional | Series A (round-type signal) | Duplicated-evidence robustness (5 raw claims, 1 real fact) |
| Auroraflow | Fictional | Undetermined (no stage signal at all) | Unsupported/fabricated claims, contradictory sources, fully withheld pillar |

Stage determination is evidence-driven (`app/evidence_engine/stage.py::determine_stage`),
never asserted for a fixture — confirmed by a dedicated test per company
(`test_stage_aware_evaluation.py`).

## 2. Per-company results

### Notion — Growth / established tier

| Dimension | Availability | Label | Score | Confidence |
|---|---|---|---|---|
| Product Existence & Maturity | Scorable | — | 7.0 | Medium |
| Differentiation Claim Corroboration | Scorable | CORROBORATED | 6.0 (established tier) | Medium |
| Technical Depth Signal | Scorable | SUBSTANTIAL (3 distinct facts) | 7.0 (established tier) | Medium |
| Defensibility Signal | Scorable | CORROBORATED_MOAT | 6.0 (established tier) | Medium |

**Pillar: Strength 6.5, Coverage 100%, Confidence Medium, Publishable.**

### Linear — Series B+ / growth tier

| Dimension | Availability | Label | Score | Confidence |
|---|---|---|---|---|
| Product Existence & Maturity | Scorable | — | 7.0 | Medium |
| Differentiation Claim Corroboration | **Unscored (uncorroborated)** | UNCORROBORATED | — | — |
| Technical Depth Signal | Scorable | SOME (1 distinct fact) | 5.5 (growth tier) | Medium |
| Defensibility Signal | **Unscored (no evidence)** | NONE_DISCLOSED | — | — |

**Pillar: Strength 6.25, Coverage 50%, Confidence Medium, Publishable.**
Withheld-dimension explanations: Differentiation's only claim is the company's own product copy
("built for speed") with no independent comparison on record — correctly excluded from scoring
rather than counted as a demonstrated weakness. Defensibility has no claim tagged at all in this
fixture — genuinely no public evidence gathered, not a negative finding.

### Pathlight (fictional) — Pre-Seed / early tier

| Dimension | Availability | Label | Score | Confidence |
|---|---|---|---|---|
| Product Existence & Maturity | Scorable | — | 7.0 | Medium |
| Differentiation Claim Corroboration | Scorable | CORROBORATED | **8.0 (early tier)** | Medium |
| Technical Depth Signal | Scorable | SOME (1 distinct fact) | 6.5 (early tier) | Medium |
| Defensibility Signal | **Unscored (no evidence)** | NONE_DISCLOSED | — | — |

**Pillar: Strength 7.17, Coverage 75%, Confidence Medium, Publishable.**
**The core stage-sensitivity result:** Pathlight's CORROBORATED differentiation claim scores
**8.0** (early tier) versus Notion's identical CORROBORATED label scoring **6.0** (established
tier) — the same kind of evidence, worth more at the stage where it is less expected, per Design
Principle 8 and the explicit "no automatic bonus to established companies" instruction (if
anything, the established company faces the higher bar for the identical evidence). Verified as
an automated regression test
(`test_identical_corroborated_evidence_scores_higher_at_an_earlier_stage`), not just this
report's own observation.

### DupliCo (fictional) — Series A / growth tier

| Dimension | Availability | Label | Score | Confidence |
|---|---|---|---|---|
| Product Existence & Maturity | Scorable | — | 7.0 | Medium |
| Differentiation Claim Corroboration | **Unscored (no evidence)** | NONE_DISCLOSED | — | — |
| Technical Depth Signal | Scorable | **SOME**, not SUBSTANTIAL | 5.5 (growth tier) | Medium |
| Defensibility Signal | **Unscored (no evidence)** | NONE_DISCLOSED | — | — |

**Pillar: Strength 6.25, Coverage 50%, Confidence Medium, Publishable.**
**The duplicated-evidence result:** 5 raw claims exist for Technical Depth Signal, all restating
one real underlying integration announcement (one `independence_group_id`). The classifier's
distinct-fact count is 1, correctly landing on SOME rather than SUBSTANTIAL (which requires 3
distinct facts) — verified as a regression test
(`test_duplicate_sources_do_not_inflate_technical_depth_past_its_real_distinct_fact_count`).

### Auroraflow (fictional) — Undetermined stage

| Dimension | Availability | Label | Score |
|---|---|---|---|
| Product Existence & Maturity | Unscored (uncorroborated) | — | — |
| Differentiation Claim Corroboration | Unscored (uncorroborated) | UNCORROBORATED | — |
| Technical Depth Signal | **Unscored (disputed)** | DISPUTED | — |
| Defensibility Signal | Unscored (no evidence) | NONE_DISCLOSED | — |

**Pillar: Strength WITHHELD (None), Coverage 0%, Confidence Low, Not publishable.**
Withheld because: weighted coverage 0.0% < 40.0% floor, AND 0 scored dimensions < 2 floor (both
gates fail independently). Withheld-dimension explanations: Product Existence and
Differentiation are each backed only by an unverifiable company self-claim, with no
independently-observable/independently-sourced evidence — correctly excluded, not scored low.
Technical Depth's two candidate claims directly contradict each other (patents filed vs. not
filed) and neither source-type precedence nor recency breaks the tie, so both remain excluded
per the fail-closed conflicting-evidence rule. Defensibility has no claim at all.

## 3. Dimension weights and label-to-score mappings — evaluation

The four Product & Technology dimension weights (0.25 each) were **not changed** in this pass.
The expanded fixture set did not surface a case where equal weighting produced an obviously
wrong relative outcome (e.g. a company whose single strongest dimension was structurally
under-weighted relative to the others) — but this is a five-company, entirely-offline check, not
a real calibration finding; equal weighting remains a placeholder pending
`NEW_ENGINE_CALIBRATION.md`'s real cohort, not a validated conclusion.

**What did change:** every Classified dimension's label→score mapping is now stage-indexed
(Part 6 below), replacing the flat single table from the first vertical slice. This is a direct
response to Task 9's own "test whether stage changes scoring appropriately" requirement and is
verified structurally (`test_every_stage_tier_table_is_monotonically_non_increasing_early_to_
established`), not just spot-checked per company.

## 4. Minimum evidence coverage and distinct-dimension requirements — evaluation

`MIN_PILLAR_COVERAGE_PCT` (40.0%) and `MIN_SCORED_DIMENSIONS_PER_PILLAR` (2) were re-tested
against the expanded roster and left unchanged. Notable boundary case actually produced by a real
fixture: Linear, Pathlight, and DupliCo all land at exactly 50% or 75% coverage with exactly 2 or
3 scored dimensions — comfortably clearing both gates without being close enough to the floor to
suggest the floor itself needs adjusting from this data alone. Auroraflow (0%, 0 dimensions)
remains the only withheld case in this roster; no fixture currently exercises the "close to the
floor" boundary precisely (e.g. exactly 40% coverage with exactly 2 dimensions) — flagged as a
gap in this offline roster's coverage of the parameter space, worth adding in a future pass
rather than silently left untested.

## 5. Confidence calculations and source reliability — what changed

Confidence (`app/evidence_engine/confidence.py`) now explicitly weighs source reliability, not
just support-status mix and corroboration count: `SOURCE_RELIABILITY_WEIGHT` ranks independent
reporting/public filings above product documentation, above aggregator/directory restatements,
above company disclosure. Every dimension result across all five fixtures in this report reached
**Medium**, never **High** or **Low** — worth stating honestly as a limitation rather than a
success: with `CONFIDENCE_MIN_CORROBORATION_GROUPS_FOR_HIGH = 2`, no single dimension across any
fixture happens to combine ≥2 distinct corroborating events AND 100% directly-supported evidence
AND ≥0.9 average reliability simultaneously (Notion's Technical Depth Signal comes closest, with
3 distinct independent-reporting/product-documentation facts, but its reliability mix — one
product-documentation claim at 0.8 weight alongside two independent-reporting claims at 1.0 —
averages to 0.87, just under the 0.9 HIGH floor). This is either a sign the HIGH bar is
appropriately strict, or a sign it is calibrated slightly too strict to ever be reached by
realistic evidence — genuinely ambiguous from five fixtures, explicitly flagged as
**CALIBRATION REQUIRED**, not resolved here.

## 6. Sensitivity to missing, contradictory, stale, and duplicated evidence — findings

- **Missing:** consistently produces `Unscored (no evidence)`, never a low score, across every
  fixture and every adversarial-model test.
- **Contradictory:** Auroraflow's disputed technical-depth claims are excluded before any
  classification model is even called (`test_disputed_evidence_short_circuits_before_any_
  model_is_called`) — a structural guarantee, not merely an outcome of the well-behaved mock's
  own good behavior.
- **Stale:** unchanged mechanism from the first vertical slice, re-verified; a claim older than
  its dimension's staleness bound is excluded and separately reported from "no evidence" or
  "disputed."
- **Duplicated:** DupliCo's result (Part 2 above) is the direct finding — 5 restatements of one
  fact never exceed what 1 real fact should support.

## 7. Gate sensitivity (spec Part 6.2's two gates, re-examined)

The synthetic test case from the first vertical slice (a single 0.45-weight dimension clearing
the 40% coverage floor alone, still correctly withheld by the distinct-dimension-count gate) was
re-run unchanged and still passes. No fixture in the expanded, real-evidence roster happens to
produce this exact shape naturally (Product & Technology's four dimensions are all equally
weighted at 0.25, so no single dimension can clear a 40% floor alone under real fixture weights)
— the synthetic test remains the only direct proof gate 2 is load-bearing under this pillar's
actual weight configuration; it would become load-bearing in practice only once a future pillar
(e.g. Financial & Funding Signals' 0.45-weight Funding History dimension, spec Part 3.3) is
built.

## 8. Provisional parameters carried forward, unresolved, or newly introduced

| Parameter | Status |
|---|---|
| `MIN_PILLAR_COVERAGE_PCT` (40.0), `MIN_SCORED_DIMENSIONS_PER_PILLAR` (2) | Unchanged, re-tested, still CALIBRATION REQUIRED |
| Dimension weights (0.25 each) | Unchanged, still CALIBRATION REQUIRED |
| `PRODUCT_EXISTENCE_SCORE` (flat 7.0, not stage-indexed) | Unchanged; reasoning restated in `parameters.py` |
| `DIFFERENTIATION_LABEL_SCORES` / `TECHNICAL_DEPTH_LABEL_SCORES` / `DEFENSIBILITY_LABEL_SCORES` | **New this pass** — stage-tiered, monotonically descending early→established. Exact numeric spread (8.0/7.0/6.0 etc.) is a reasoned placeholder demonstrating the *direction and shape* required, not a calibrated magnitude. |
| `SOURCE_RELIABILITY_WEIGHT` | **New this pass.** Ordering (independent/filing > documentation > aggregator > company disclosure) is reasoned; exact numeric weights are placeholders. |
| `CONFIDENCE_MIN_RELIABILITY_FOR_HIGH` / `_FOR_MEDIUM` | **New this pass.** Part 5 above found the HIGH bar may be uncalibrated-strict; flagged, not adjusted without real data. |
| Founding-age stage bands (`stage.py::_FOUNDING_AGE_BANDS`) | **New this pass**, explicitly reasoned placeholders, never exercised against a real company's actual founding date in this offline roster. |

## 9. What remains a known limitation (stated, not hidden)

- **Five fixtures is not a calibration cohort.** This report validates that the *mechanism*
  behaves correctly (gates, stage direction, dedup, dispute-exclusion, graceful failure) — it
  does not and cannot validate that any specific number is *right*. `NEW_ENGINE_CALIBRATION.md`'s
  much larger, real cohort is still the actual calibration plan.
  - **Scale-based stage fallback is not implemented** — stage determination supports only
  round-type and founding-age signals (spec Part 4.1 items 1-2); the scale-based fallback (item
  2 of the fuller design) needs Commercial Traction's Disclosed Scale, not yet built.
- ~~**`independence_group_id` correctness is assumed, not verified.**~~ **Closed by Task 10** —
  see Part 10.1 below. A residual limitation remains (Part 10.5).
- **No pillar other than Product & Technology exists**, so the overall (cross-pillar)
  publication gate (spec Part 6.5) remains untestable in this codebase today.

---

## Part 10 — Task 10: Evidence Reliability & Validation

Parameter version `evidence_engine.v1-provisional-3`. New code:
`app/evidence_engine/provenance.py`; extensions to `classification.py` (`classify_with_recovery`/
`extract_with_recovery`, `requires_minimum_distinct_facts` upgraded), `confidence.py`
(corroboration now provenance-verified). Three new test files (25 tests):
`test_provenance_verification.py` (9), `test_classification_recovery.py` (5),
`test_coverage_boundaries.py` (8), plus 3 new tests threaded into the existing suite total —
**77 tests across 7 files**, up from 55.

### 10.1 Evidence independence, closed

The exact gap Part 9 flagged is closed: `verify_independence()` re-derives distinct-fact counting
from each claim's own content and provenance (an exact `source_url` match, or a Jaccard
token-overlap ratio over `excerpt`/`claim_text` against two thresholds — ≥0.75 similarity is
judged `LIKELY_DUPLICATE`, ≥0.40 is `UNKNOWN`, below is `INDEPENDENT`) rather than trusting each
claim's self-declared `independence_group_id`. Verified directly
(`test_verify_independence_folds_a_syndicated_restatement_under_a_different_declared_group`): three
claims tagged for Technical Depth Signal, each given a **different** declared group id, where two
are a near-identical (syndicated) restatement — verification still folds them to 2 confirmed-
distinct facts, and the SUBSTANTIAL threshold (which the naive, group-id-trusting default
classifier would have believed it cleared) is correctly rejected by the now-provenance-aware
validator. Per the task's explicit instruction, ambiguous cases (`UNKNOWN`) are never counted as
an additional distinct fact — confirmed by
`test_unknown_independence_claims_are_not_counted_as_distinct`. Confidence's corroboration input
was updated identically (`confidence.py`), verified by
`test_confidence_corroboration_uses_verified_not_declared_distinct_count`.

**This is a conservative safety net, not a redesign of the independence concept**: verification
can only ever fold groups together or mark them Unknown — it can never split a declared group
into more distinct facts than were actually supplied
(`test_verification_never_increases_the_declared_distinct_count`). The real fixture roster
(Notion's three genuinely-distinct technical facts) is unaffected — re-verified passing after this
change.

### 10.2 Classification recovery

`classify_with_recovery()`/`extract_with_recovery()` (`classification.py`) retry exactly once,
feeding the first attempt's violations back to the model as `ClassificationRequest.
validation_feedback`/`ExtractionRequest.validation_feedback`. Both attempts are validated by the
exact same `validate_classification()`/`validate_extraction()` call — there is no relaxed check on
the second attempt (`test_recovery_never_relaxes_citation_validation_on_the_second_attempt`
constructs a model that "corrects" its label but fabricates a citation on retry, and confirms this
is still rejected). A model that ignores the feedback and repeats itself fails closed to
`Unscored (extraction_failed)` after exactly 2 attempts, never an exception
(`test_second_invalid_attempt_fails_closed_to_unscored`). A model that already succeeds on
attempt 1 is never retried (`test_a_model_that_is_correct_on_the_first_attempt_is_never_retried`,
asserting the call count directly). The two mechanisms compose exactly as designed: the same
provenance-driven SUBSTANTIAL rejection from 10.1, given to a model that reads the feedback and
correctly drops the flagged duplicate, recovers to a valid `SOME` on the second attempt
(`test_second_attempt_succeeds_when_the_model_reads_feedback_and_corrects`).

### 10.3 Coverage-boundary testing

`test_coverage_boundaries.py` constructs the exact 40.0% coverage value and the values immediately
above/below it, confirming the floor is inclusive (`coverage_pct < floor` is the only failing
condition — exactly 40.0% passes). The two-scored-dimension minimum is tested independently of
coverage twice: once with a single 0.70-weight dimension (coverage far above the floor, only the
count gate fails) and once with a single dimension weighted at **exactly** the coverage floor
(0.40) — both fail only the count gate, confirmed by asserting the withhold reason names the
dimension-count floor and *not* coverage. `test_missing_evidence_for_the_weak_dimensions_cannot_
surface_the_strong_one_alone` directly reconfirms the anti-gaming property: a lone 9.0-scoring
dimension with its three siblings missing computes a raw renormalized value of 9.0 internally, but
the published `PillarResult.strength` is `None` — the gates, not the math, are what stand between
a cherry-picked high scorer and the product showing it as the pillar's real Strength.

### 10.4 Stage-specific label-to-score tables — rationale review (no values changed)

Per the task's explicit instruction, this section documents *why* the current numbers are what
they are and what would need real-world data to move them — it does not adjust any value.

**The direction (early > growth > established, strictly descending) is well-justified
structurally**, independent of any specific magnitude: it is the direct implementation of Design
Principle 8 ("company stage affects the criteria used for assessment") combined with the explicit
instruction not to grant established companies an automatic bonus. A model in which the identical
evidence scored the same regardless of stage would fail to distinguish "remarkable for this stage"
from "an unremarkable baseline for this stage"; a model in which it scored *higher* at a later
stage would be the literal automatic bonus the task forbids. Descending is therefore the only
direction consistent with both constraints, and this is verified structurally, not just for the
three tables that happen to exist
(`test_every_stage_tier_table_is_monotonically_non_increasing_early_to_established`).

**The magnitude (a uniform 1.0-point gap per tier: 8.0/7.0/6.0, 9.0/8.0/7.0, 6.5/5.5/4.5,
8.0/7.0/6.0) is NOT independently justified and is exactly the kind of value the task asks to be
identified rather than invented further.** Three specific open questions, none answerable without
real outcome data:

- **Is a uniform 1.0-point gap the right shape at all?** It was chosen for legibility while
  building the mechanism, not derived from any signal about how much more (or less) remarkable
  identical evidence actually is one stage earlier. The true gap could be non-uniform (e.g. a
  larger gap between Early and Growth than between Growth and Established, if the evidence bar
  actually jumps more sharply early on), or could differ by dimension (Technical Depth Signal's
  gap need not equal Defensibility Signal's).
- **Is the SAME gap size appropriate across all three currently-tiered dimensions?**
  Differentiation, Technical Depth, and Defensibility all use exactly ±1.0/tier today purely
  because that was the simplest placeholder to reason about consistently, not because there is any
  basis to believe these three dimensions should move together.
- **Should Product Existence & Maturity remain the one dimension with NO stage index at all?**
  Part 2.5 of the original spec reasoned this is a binary structural fact ("does an
  independently-observable artifact exist") whose meaning doesn't obviously vary by stage. This
  reasoning has not been tested against real data and could be wrong — e.g., a real, working
  product might be a more remarkable signal at Idea/Pre-Seed (where many companies have nothing
  shippable yet) than the current flat treatment implies.

**What would resolve this:** real calibration against the cohort `NEW_ENGINE_CALIBRATION.md`
describes, specifically designed to surface whether stage-tier gaps should differ by dimension or
by tier-pair — not addressable by reasoning further from five offline fixtures, and not addressed
here per the task's own instruction to keep all numerical parameters provisional rather than
invent new ones.

### 10.5 Residual limitation, honestly restated

Provenance verification (10.1) is a text/URL-based heuristic, not true fact-verification — two
claims describing the *same real fact* in genuinely different, independently-written prose will
correctly register as `INDEPENDENT` (this is by design; independent authors writing about the same
true event are exactly what real corroboration looks like), while two claims that happen to use
similar phrasing for *different* facts could, in principle, be wrongly folded together. The
Jaccard-similarity thresholds (0.75/0.40) are reasoned placeholders (parameters.py), not derived
from a labeled corpus of real syndicated-vs-independent article pairs — flagged as
**CALIBRATION REQUIRED**, consistent with every other threshold in this system.
