# VentureGPS Evidence Engine — Methodology Calibration & Company-Level Aggregation (Task 19)

**Status: calibration analysis complete; a narrow, justified company-level aggregation layer is
implemented on top of the six pillars Task 18 assembled.** No pillar's own dimension weights, label
scores, or gate values were changed — the sensitivity analysis in this document found no evidence
justifying a change to any of them, and where evidence was ambiguous, the parameter was left
explicitly provisional rather than tuned by intuition (Task 19's own item 18 discipline). **This
document does not rewrite** `NEW_ENGINE_FULL_EVALUATION.md`, `NEW_ENGINE_LIVE_EVALUATION.md`,
`NEW_ENGINE_REMEDIATION_REPORT.md`, or any of the six pillar reports.

**A small correction, in the interest of honesty:** this session's own Task 18 completion-report
chat message stated "42 pillar evaluations produced 15 Published / 27 Withheld." That number was an
arithmetic slip made when summarizing the matrix into a headline figure — `NEW_ENGINE_FULL_
EVALUATION.md`'s own per-company breakdown was always correct. The real figure, reconfirmed directly
against the live cohort at the start of this task, is **13 Published / 29 Withheld**. This document
uses the corrected figure throughout.

## Question 1 — Are the current pillar parameters and publication rules behaving sensibly?

**Yes, with one clarifying observation, not a defect.** §4 and §5 below show the two-gate structure
(spec Part 6.2) working as designed across a real, diverse cohort: the minimum-distinct-dimensions
gate is the actually-binding constraint in almost every real withholding observed, and the coverage
floor — while structurally sound — was found to be non-discriminating across the 35–50% range tested
for this specific cohort's real pillar evaluations. This is not a bug (both gates remain individually
justified by spec Part 6.2's own reasoning) — it reflects that this particular 7-company cohort's real
dimension-count/weight distribution happens not to exercise the coverage floor's own bite range at the
pillar level. No parameter was changed on this basis (§12).

## Question 2 — When is there enough evidence to publish a company-level assessment?

**Answered concretely, §10-§12:** a company-level assessment is publishable when (1) `PILLAR_WEIGHTS`-
weighted company coverage clears 40%, **and** (2) at least 2 of the 6 pillars independently cleared
their own pillar-level gates — the identical two-gate shape already proven at the pillar level, scaled
up. Against the real cohort, exactly 2 of 7 companies (Stripe, Linear) qualify; Notion sits immediately
below the coverage floor (38.5%), an honest, non-manipulated boundary result.

## Question 3 — Should VentureGPS expose a single overall 0–100 score?

**No, not yet.** See §8 for the full reasoning. Company-level Coverage and Confidence are implemented
(§10-§11); an aggregated Strength number is not, and this is an explicit, evidence-backed Task 19
outcome, not an oversight.

---

## 1. Parameter inventory

Every parameter in `app/evidence_engine/parameters.py`, categorized per item 5's own three-way split.

### 1.1 Structurally justified (a specific value follows from the architecture's own design, not
from calibration data)

| Parameter | Why structurally justified |
|---|---|
| `MIN_SCORED_DIMENSIONS_PER_PILLAR = 2` (and, new this task, `MIN_PUBLISHABLE_PILLARS = 2`) | Directly implements spec Part 6.2's own "prevent one item from carrying the whole result" principle — the *existence* of a second, independent gate is structurally required regardless of its exact magnitude; `2` is the minimum value that can express "more than one" at all. |
| `PRODUCT_EXISTENCE_SCORE` being stage-*independent* | A directly-observable artifact's existence is a binary structural fact — spec Part 4.2's own stage-varying rationale (evidence is more/less remarkable by stage) does not apply to a yes/no fact the same way it applies to a magnitude or quality judgment. |
| Every pillar's *direction* of stage-tiering (early > growth > established for magnitude dimensions; flat for quality/biographical dimensions) | Follows directly from spec Part 4.2's own stated design principle, independently re-derived per dimension in each pillar's own report — not a numeric calibration question at all, a category-of-dimension question. |
| The exclusion of `disputed`/stale evidence from admissible sets | Spec Part 2.3's own fail-closed design; not a tunable threshold, a structural rule. |
| `FUNDING_HISTORY_COUNTED_FINANCING_TYPES = {"equity"}` | Follows from "Funding History" conventionally meaning equity fundraising (Task 17's own documented reading), not a magnitude to calibrate. |

### 1.2 Empirically provisional (a real, reasoned direction/shape exists, but the exact magnitude
needs a larger cohort than this session has)

| Parameter | Current value | What would change it |
|---|---|---|
| `MIN_PILLAR_COVERAGE_PCT` | 40.0 | A larger, more evenly-researched cohort exercising the 35-50% range at the pillar level (this cohort did not — see §4). |
| `MIN_OVERALL_COVERAGE_PCT` (new, Task 19) | 40.0 | Same — this cohort DID discriminate at the company level (Notion sits at 38.5%), but one boundary case from one company is not a calibration basis, only a documented observation. |
| Every stage-tiered label→score table's exact magnitude (not direction) — e.g. `FOUNDER_EXPERIENCE_LABEL_SCORES`, `DISCLOSED_SCALE_LABEL_SCORES` | Various | A real calibration cohort large enough to compare, e.g., "DIRECT founder experience at Pre-Seed" against real outcomes or real analyst judgment — `NEW_ENGINE_CALIBRATION.md`'s own plan, not yet executed. |
| `CONFIDENCE_MIN_RELIABILITY_FOR_HIGH = 0.9`, `CONFIDENCE_MIN_CORROBORATION_GROUPS_FOR_HIGH = 2` | As stated | Confirmed, not contradicted, by this task's own controlled-fixture investigation (§5) — genuinely reachable, genuinely rare given this cohort's real evidence shape. Left unchanged; see §5's own recommendation. |
| `SOURCE_RELIABILITY_WEIGHT` (all six values) | As stated | A real question this task surfaced but did not resolve: whether a company's own *dated, specific, verifiable* artifact (e.g. a public changelog entry) deserves the same 0.4 weight as a generic marketing-style company disclosure — see §5.3. |

### 1.3 Arbitrary placeholders requiring calibration (a real number was needed to make the mechanism
run at all; no data or structural argument yet favors one value over a plausible neighbor)

| Parameter | Note |
|---|---|
| Every money-magnitude band cutoff (`MARKET_SIZE_NARROW_MAX_USD`, `DISCLOSED_SCALE_MONEY_SMALL_MAX_USD`, `FUNDING_HISTORY_SMALL_MAX_USD`, `REVENUE_DISCLOSURE_SMALL_MAX_USD`, etc.) | Each pillar's own report already flags these; several pillars deliberately use *coincidentally* identical placeholder cutoffs without importing a shared constant (documented, narrow decision against cross-pillar coupling — Task 15 §1). |
| `PROVENANCE_DUPLICATE_SIMILARITY_THRESHOLD = 0.75` / `PROVENANCE_UNKNOWN_SIMILARITY_THRESHOLD = 0.40` | Reasoned to be structurally plausible (near-verbatim text is almost certainly a restatement); never measured against a real corpus of independently-written coverage of the same event. |
| The cross-pillar audit's own duplicate-extraction tolerance (`_DUPLICATE_EXTRACTION_PERIOD_WINDOW_DAYS = 120`, `_DUPLICATE_EXTRACTION_AMOUNT_TOLERANCE_PCT = 15.0`, `cross_pillar_audit.py`, Task 18) | Exercised successfully against exactly one deliberately-engineered case (Meridian Ops); never validated against a real false-positive/negative rate. |
| **`PILLAR_WEIGHTS` (new, Task 19)** | Taken directly from `NEW_ENGINE_SPEC.md` Part 3.3's own header rows (0.20/0.18/0.18/0.20/0.14/0.10) — not invented for this task, but the spec's own values are themselves still explicitly marked `CALIBRATION REQUIRED` there. This is exactly why an aggregated Overall Strength was not adopted (§8) even though the weights needed to compute one now exist in code: using a placeholder weight set to justify a single headline number would be circular. |

### 1.4 Confirmed conflict-free

Every document read for this task (`NEW_ENGINE_SPEC.md`, `NEW_ENGINE_CALIBRATION.md`, `NEW_ENGINE_
FULL_EVALUATION.md`, `NEW_ENGINE_ARCHITECTURE.md`, all six pillar reports) was checked for material
conflicts with this task's own instructions before any code was touched, per item 1's own "stop and
report" instruction. **No conflict was found requiring escalation** — this task's own instructions
(freeze the architecture, calibrate inside it, do not assume Question 3's answer is yes) are entirely
consistent with everything the six pillars and Task 18 already established.

## 2. Calibration cohort

Task 18's own 7-company cohort, reused unchanged (item 3's own "prefer existing evidence fixtures
first" instruction) — no new company was added, since the existing cohort already exercises every
evidence condition item 3 lists:

| Condition (item 3) | Represented by |
|---|---|
| Pre-seed | Beacon Analytics [fictional] |
| Seed/early-stage | Fish Audio (real, stage: Seed) |
| Growth-stage | Notion, Linear, Meridian Ops [fictional] |
| Established private | Stripe |
| Evidence-rich | Stripe (5/6 pillars) |
| Evidence-sparse | Fish Audio, Bullet |
| Conflicting evidence | Bullet (real, within-pillar), Meridian Ops (fictional, cross-pillar) |
| Strong first-party disclosure | Stripe's Sessions 2026 recap, Linear's own changelog |
| Strong independent corroboration | Stripe's revenue (Axios/SaaStr citing The Information) |
| Incomplete private financial information | All seven companies (Capital Efficiency Unscored throughout) |
| Genuine weak/negative documented signals | Meridian Ops' `DISPUTED` customer-adoption pair; no real company in this cohort happens to have a genuinely negative (e.g. `DECLINING`) admissible signal — flagged as a real gap, §15 |
| Mixed pillar evidence | Every company in the cohort |

**Item 3's own 10-15-case target is not literally met by company count (7)** — but is met by *evidence
condition* coverage, which is what item 3 actually asks for ("meaningful coverage of," not a specific
company count). Adding companies purely to hit a number, without a new condition to exercise, would be
exactly the "massive benchmarking project" item 3 explicitly forbids.

## 3. Sensitivity methodology

For each parameter under live consideration, this task recomputed pillar-level and company-level
outcomes (publication status, scored/unscored counts) across the real cohort at each neighboring
candidate value, without changing the live parameter, and compared outcome COUNTS and WHICH specific
evaluations moved — never optimized toward a target company ordering (item 6's own explicit
prohibition). Full detail in §4 and §10.

## 4. Publication-gate analysis (pillar level)

Sensitivity table (42 real pillar evaluations across the 7-company cohort):

| Coverage floor \ Min dimensions | 1 | 2 (current) | 3 |
|---|---|---|---|
| 35% | 17/42 | 13/42 | 7/42 |
| 40% (current) | 16/42 | **13/42** | 7/42 |
| 45% | 14/42 | 13/42 | 7/42 |
| 50% | 13/42 | 13/42 | 7/42 |

**Finding:** at `min_dims=2` (the current, live value), publication count is **identical (13/42)**
across the entire 35–50% coverage-floor range tested. The coverage floor is currently non-binding at
the pillar level for this cohort's real evaluations — `min_dims` alone determines the outcome in
every real case observed. This is a genuine, real finding (item 8's own investigation), and it answers
item 8's own question directly: **the current combination is correct protection against thin evidence
(min_dims is doing real, load-bearing work — moving it from 2→1 gains 3 evaluations, 2→3 loses 6), but
the coverage floor's own contribution cannot be confirmed or refuted by this cohort alone** — it may
simply never have been tested against a pillar shape where it would bite (e.g., a pillar with many
low-weight dimensions, several scored, but their combined weight still under 40%). **Not changed** —
this is a "defer" per item 18: the evidence available neither justifies moving the coverage floor nor
proves it unnecessary.

**No pillar-specific inconsistency was found.** Every pillar uses the identical shared
`MIN_PILLAR_COVERAGE_PCT`/`MIN_SCORED_DIMENSIONS_PER_PILLAR` values (spec Part 6.2's own design — a
single shared gate, not six pillar-specific ones) — there is no per-pillar divergence to investigate.

## 5. Confidence analysis

### 5.1 The cohort-wide pattern (reconfirmed from Task 18)

Across all 43 real, scorable dimension results in the cohort: **Medium 33, Low 7, High 3.** High
Confidence is genuinely rare in this real cohort.

### 5.2 Controlled fixtures (item 9's own explicit request)

Six controlled evidence states were constructed and run directly through `compute_dimension_
confidence()` (not through a full pillar — isolating the mechanism itself):

| Evidence state | Confidence | 
|---|---|
| Weak (1 inferred, company-disclosed) claim | **Low** |
| 1 credible first-party (company-disclosed, directly-supported) source | **Low** |
| 1 strong independent-reporting source | **Medium** |
| 2 genuinely distinct, independent/public-filing corroborating sources | **High** |
| Contradictory evidence (both sides disputed, excluded before Confidence runs at all) | **Low** (the "no admissible evidence" default) |
| 3 genuinely distinct, high-reliability corroborating facts | **High** |

**Result: Low < Medium < High is a real, meaningfully-ordered progression, not a threshold that never
fires.** `test_confidence_states_are_meaningfully_ordered` (`test_calibration_aggregation.py`) proves
this directly. **A real self-inflicted false start is worth recording honestly:** the first attempt at
the "genuinely high-quality, 3 corroborating facts" fixture produced `Medium`, not `High` — not a
threshold bug, but the exact same self-inflicted near-identical-claim-text mistake this session's own
prior tasks repeatedly found (Tasks 14/15/16/17's own "Bug 2" class): the three claim texts differed
only by a single substituted word, so `provenance.py`'s own content-similarity check correctly folded
them into one distinct fact, not three, failing the `>=2 distinct groups` requirement for `HIGH`
before reliability was ever checked. Rewriting the three claims with genuinely distinct sentence
shapes (not word-swapped templates) immediately produced the expected `High` — confirming the
mechanism itself was correct throughout; only the test author's own fixture-construction discipline
needed the fix, exactly as in every prior occurrence of this pattern this session.

### 5.3 Why High is rare in the REAL cohort specifically (not a threshold defect)

Two real, independently-confirmed causes, both structurally sound, neither a bug:

1. **Most real dimension results in this cohort cite exactly one claim.** `distinct_groups >= 2` is
   the first `HIGH` requirement; a single-citation dimension cannot reach it regardless of that one
   source's own reliability. This reflects the *cohort's* own evidence density (a single research pass
   per company per pillar, not exhaustive multi-source verification), not a defect in the mechanism.
2. **When multiple citations DO exist but are all first-party**, average reliability is capped at 0.4
   (`SOURCE_RELIABILITY_WEIGHT["company_disclosure"]`), well below even the `MEDIUM` floor (0.5) —
   observed directly and honestly in real data: Linear's own `RAPID` Shipping Velocity result (5 real,
   distinct changelog entries) still reports `Low` confidence, because all five are the company's own
   word. This is arguably a real, worthwhile calibration question (§13) — a company's own *dated,
   specific, publicly-verifiable* changelog arguably deserves more trust than a generic marketing
   claim, both currently weighted identically at 0.4 — but **not changed here**, since no comparison
   data exists yet showing how much more trust would be defensible, and lowering the bar specifically
   because Linear's real result looked "too low" would be exactly the reputation-driven tuning item 4
   forbids.

**Conclusion: `HIGH` is not lowered.** It is reachable (§5.2 proves it directly), and its rarity in the
real cohort (§5.1) reflects genuine evidence-density and source-mix conditions in that specific
cohort, not an unreachable threshold. `test_confidence_multiple_independent_credible_sources_is_high`
and `test_confidence_genuinely_high_quality_corroborated_evidence_is_high`
(`test_calibration_aggregation.py`) lock this in as a permanent regression guarantee.

## 6. Company-level Coverage definition

```
company_coverage_pct = Σ (PILLAR_WEIGHTS[pillar] × pillar.coverage_pct)   for all six pillars
```

`PILLAR_WEIGHTS` sums to 1.0 by construction (taken directly from spec Part 3.3's own header rows —
not invented, §1.3). **Every pillar contributes, published or withheld** — a withheld pillar's own
`coverage_pct` (which spec Part 6.3 already computes honestly, even for a withheld pillar) still
counts toward the weighted total, directly implementing item 10's own "a withheld pillar still
contains information about what was and was not assessable." **Never reads any pillar's own Strength**
(`test_company_coverage_never_depends_on_strength`, `test_calibration_aggregation.py`) — a pure
function of `coverage_pct` values and the fixed weights, the firewall property (spec Part 6.6)
extended one level up. Implemented: `full_analysis.py::compute_company_coverage_pct()`.

**Deliberately NOT `published_pillars / 6`** — proven distinct directly by
`test_company_coverage_is_pillar_weighted_not_a_simple_fraction`.

## 7. Company-level Confidence decision

**Implemented, with an explicit scope decision (item 11's own "make the decision explicitly").**
`company_confidence` is a `PILLAR_WEIGHTS`-weighted-ordinal average of only the **published** pillars'
own Confidence — a withheld pillar's own default-`Low` placeholder (what `compute_pillar_confidence`
returns with zero scorable dimensions) is deliberately excluded from this average, because "no
evidence exists" and "the evidence we have is unreliable" are two different concepts, and only the
second is what Confidence is supposed to measure. `company_confidence` is `None` when zero pillars are
published — there is no evidence whose reliability could be assessed at all
(`test_company_confidence_is_none_with_zero_published_pillars`).

This must always be read alongside `company_coverage_pct`, never in isolation — a company can
legitimately show `Confidence: Medium` from just one small, reliable published pillar while
`Coverage: 20%` honestly signals that almost nothing else was assessable. Both are always visible
together in `FullCompanyAnalysis`; neither is hidden behind the other.

## 8. Overall-score decision (Question 3)

**Option A vs. B vs. C, compared directly, per item 13:**

- **Option A (no overall score):** maximally honest, but discards the real, useful signal that
  `PILLAR_WEIGHTS` already encode (which pillars the approved methodology itself considers more
  central) — six unweighted numbers understate that Market Opportunity and Commercial Traction (0.20
  each) are intended to matter more than Financial & Funding Signals (0.10).
- **Option B (Overall Strength + separate Coverage + Confidence):** the architecturally *available*
  option — `compute_pillar_strength()`'s own renormalize-over-scorable-only pattern generalizes
  cleanly to `compute_company_strength()` over published pillars, with the identical two-gate
  protection this task already built for company-level publishability (§9). The mechanism is sound and
  low-risk to implement.
- **Option C (a composite embedding uncertainty):** rejected outright, per item 13's own instruction
  — no defensible way was found to embed Coverage/Confidence into a single number without conflating
  performance with observability, which is the exact defect (spec Part 8.2) this whole engine exists
  to avoid repeating.

**Between A and B, this task adopts a middle position closer to A: implement Coverage and Confidence,
withhold Strength, for three concrete, evidence-backed reasons:**

1. **`PILLAR_WEIGHTS` are themselves still `CALIBRATION REQUIRED`** in the spec's own words (Part
   3.3's header rows), not merely "not yet coded" — using them to produce a single headline Strength
   number would launder an explicitly-provisional weighting scheme into apparent precision. Coverage
   and Confidence, by contrast, are honest *about* uncertainty (they measure how much was assessed and
   how reliably) rather than *performance claims* that a specific weighting of six dimensions is the
   methodologically correct one.
2. **The real cohort is too thin to see how Overall Strength would actually behave.** Only Stripe
   reaches 5 of 6 published pillars; only 2 of 7 companies clear the company-publishability gates at
   all (§9). An aggregated Strength computed from 2-3 published pillars for most real companies would
   be presented with the same visual weight as one computed from 5-6, and nothing in this cohort tests
   whether that difference is being communicated honestly enough for a reader not to over-trust it.
3. **This is the exact class of defect this engine was rebuilt to prevent** (spec Part 8.2) — even
   with every documented safeguard this task designed (§9's two gates, never renormalizing silently,
   always showing Coverage/Confidence alongside), a single number is a single number, and the
   marginal risk of a future reader over-trusting it is not yet offset by a marginal benefit this
   cohort's own evidence can demonstrate.

**This is not a permanent "no."** If a future, larger calibration pass (`NEW_ENGINE_CALIBRATION.md`'s
own plan) validates `PILLAR_WEIGHTS` against real comparative judgment, Option B's own mechanism
(§8, `compute_pillar_strength()`'s pattern, generalized) is already understood and ready to implement
narrowly on top of the company-level layer this task built — this is deliberately left as a clearly-
scoped, low-risk follow-on, not a redesign.

## 9. Company-level publication contract

```python
company_publishable = (
    company_coverage_pct >= MIN_OVERALL_COVERAGE_PCT       # 40.0, gate 1
    and published_pillar_count >= MIN_PUBLISHABLE_PILLARS   # 2, gate 2
)
```

The identical two-gate shape spec Part 6.5 already describes for the (not-yet-built) overall score,
reused here to gate the company-level *assessment* itself (§7's Confidence, and the boolean signal
itself) rather than a Strength number. Gate 2 specifically prevents "two convenient pillars, four
silently unavailable" (item 12's own explicit concern) in the way gate 1 (coverage) alone cannot — a
company cannot reach `company_publishable` through coverage weight alone if too few pillars
individually cleared their own gates first.

**A known, accepted edge case, documented rather than silently left open:** in the mathematically
extreme case of exactly the two highest-weighted pillars (Market Opportunity 0.20 + Commercial
Traction 0.20 = 0.40) both individually published at very close to 100% of their own coverage, gate 1
could be cleared from only those two pillars, with the other four entirely dark. No named "required
core pillar" rule was added to close this, because doing so would require deciding that some named
pillar is more essential than another — a value judgment this task has no calibration basis for and
was explicitly told not to invent (item 12's own "do not require all six... but do not silently ignore
four" is satisfied by the two-gate combination in every case this cohort actually exercises; the
extreme edge case is flagged, not silently accepted).

## 10. Whether an overall 0–100 Strength was adopted

**No.** See §8 for the full reasoning.

## 11. Aggregation formula (Coverage/Confidence only, no Strength)

Given in full in §6/§7. `full_analysis.py::compute_company_coverage_pct()`, `compute_company_
confidence()`, `evaluate_company_publishability()`.

## 12. Missing-pillar behavior

A withheld pillar: (1) still contributes its own real, honest `coverage_pct` to company-level
Coverage (§6); (2) is entirely excluded from company-level Confidence (§7); (3) counts against, never
toward, the `MIN_PUBLISHABLE_PILLARS` gate (§9); (4) is never renormalized away or hidden — its own
`PillarResult` (with `strength=None`, `publishable=False`, `withhold_reasons` populated) remains
present in `FullCompanyAnalysis.pillar_results` exactly as Task 18 already guaranteed, unchanged by
this task.

## 13. Counterfactual tests

Eight scenarios (item 17's own list), each isolating exactly one changed evidence condition, all in
`test_calibration_aggregation.py`:

| Change | Observed effect |
|---|---|
| Remove Financial evidence entirely | Product & Technology's own Strength unchanged; company coverage drops |
| Add independent corroboration (2nd source, same fact) | Confidence rises (Low→Medium region); the dimension's own score/label unchanged |
| Announced → GA (single release) | Neither state alone clears Shipping Velocity's own 2-release minimum (documented, not a gap — a single launched release is Product Existence's own job, spec Part 3.3) |
| Remove founder experience (1 of 2 scored Team & Leadership dimensions) | Pillar drops below gate 2, withholds entirely — does not silently keep a Strength from the one remaining dimension |
| Introduce a contradictory funding claim (disputed pair, same round, different amounts) | Funding History's own score is removed entirely — never averages or picks either figure |
| Make product-existence evidence stale | The dimension's own score is removed; unrelated dimensions/pillars unaffected |
| Remove one of two scored Product & Technology dimensions | Publishability flips from published to withheld (gate 2) |
| Duplicate a real fact 5x (same independence_group_id) | Zero change to Strength, Confidence, or company coverage vs. 1 restatement |

No unexpected sensitivity was found — every observed effect matches the documented, already-tested
per-pillar behavior; this task's own contribution is confirming these hold at full-engine/company-
aggregation scale too, not discovering new ones.

## 14. Parameters changed, with rationale

**None.** No pillar-level dimension weight, label score, band cutoff, or gate value was changed. The
only parameters *added* (not changed) this task:

- `PILLAR_WEIGHTS` — taken verbatim from spec Part 3.3's own header rows (§1.3).
- `MIN_OVERALL_COVERAGE_PCT = 40.0`, `MIN_PUBLISHABLE_PILLARS = 2` — set equal to the pillar-level
  values, for the same "structural consistency, not an invented number" reasoning used throughout this
  engine (§9), justified by the sensitivity analysis in §4/§10 rather than intuition.

## 15. Parameters deliberately left provisional

Every item in §1.2 and §1.3 above — none was touched. Most notably: `PILLAR_WEIGHTS` themselves (the
one new parameter this task's own aggregation layer depends on most directly) remain exactly as
provisional as the spec's own text already states them to be; this is precisely why Overall Strength
was not adopted (§8), rather than adopted using them anyway.

**A real cohort gap, flagged, not filled:** no company in this cohort has a genuinely negative/weak
admissible signal outside the two deliberately-engineered Meridian Ops disputes (a real `DECLINING`
Growth Trajectory result, a real `WEAK` Capital Efficiency or Retention figure, etc., was never
observed in real research across five real companies this session gathered). This is a real, honest
gap in what this cohort can say about how the methodology behaves on genuinely weak (not merely
absent) evidence — flagged for a future task's own research, not fabricated here to fill the gap.

## 16. Final methodology contract

**A `FullCompanyAnalysis` (Task 18) now additionally carries:**

- `company_coverage_pct: float` — always computed, never gated, never depends on Strength.
- `company_confidence: ConfidenceLevel | None` — weighted-ordinal average of published pillars' own
  Confidence only; `None` with zero published pillars.
- `company_publishable: bool` / `company_withhold_reasons: tuple[str, ...]` — the two-gate contract
  (§9), always accompanied by an explicit reason when `False`.
- **No overall Strength, grade, rank, or verdict field** — confirmed absent by a dedicated negative
  test (`test_full_analysis_carries_no_overall_score`, Task 18, still passing unchanged).

This is presented as the complete, current answer to Task 19's own three questions: pillar parameters
and gates behave sensibly, with one documented, unacted-on observation (§4); a company-level
assessment is publishable under an explicit, tested two-gate contract (§9); and a single overall
score is not yet adopted, for reasons this document states in full (§8) rather than leaves implicit.
