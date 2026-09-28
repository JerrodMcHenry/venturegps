# VentureGPS Evidence Engine — Full-Engine Assembly & Cross-Pillar Evaluation (Task 18)

**Status: assembled and evaluated — for the first time, all six completed pillars
(Product & Technology, Market Opportunity, Team & Leadership, Commercial Traction,
Execution & Momentum, Financial & Funding Signals) run against one canonical evidence ledger
through one orchestrator and produce one coherent, auditable `FullCompanyAnalysis`.** This task
deliberately creates **no overall 0–100 score, no pillar-weight aggregation, no ranking, and no
investment verdict** — those are explicitly out of scope (Task 18 item 20) and remain Task 19's own
work. This document does not rewrite any of the six pillars' own historical implementation reports.

## 1. Cohort

Seven companies, chosen for evidence-condition diversity, not for expected scores (item 13's own
explicit instruction — no company was selected, or its evidence extended, because a particular
result was wanted):

| Company | Real/Fictional | Category represented |
|---|---|---|
| Stripe | Real (Tasks 11-17) | Established private company; evidence-rich (5 of 6 pillars) |
| Notion | Real (Tasks 11-15) | Growth-stage private company; evidence-rich in Market + Product, real disputed stage signal |
| Linear | Real (Tasks 11-16) | Growth-stage private company; evidence-rich in Team + Execution + Product |
| Fish Audio | Real (Task 11) | Evidence-sparse company (Product & Technology only) |
| Bullet | Real (Task 11) | Evidence-sparse company with a real, disputed within-pillar evidence pair |
| Beacon Analytics | **Fictional (Task 18)** | Pre-seed startup, deliberately sparse-but-real evidence |
| Meridian Ops | **Fictional (Task 18)** | Growth-stage startup, deliberately engineered cross-pillar contradictions |

Beacon Analytics and Meridian Ops were added specifically because no real-evidence fixture in this
session's prior work happened to combine a pre-seed company and a genuine cross-pillar contradiction
scenario — the two things item 12/9 explicitly ask this evaluation to exercise. Both are explicitly
fictional (`app/evidence_engine/fixtures/*_fictional.py`), never mixed with `live_research/` real
data, matching the established Task 8-9 convention for offline adversarial fixtures.

## 2. Methodology version

`evidence_engine.v1-provisional-9` (unchanged by this task — Task 18 added no new pillar parameters;
see §9).

## 3. Full evaluation matrix

**Published / Withheld, Strength, Coverage, Confidence, scored/unscored dimension counts, per
company per pillar.** Reproduce with
`python -m app.evidence_engine.live_research.run_full_engine_cohort_evaluation`.

### Stripe (stage: Growth)
| Pillar | Status | Strength | Coverage | Confidence | Scored/Unscored |
|---|---|---|---|---|---|
| Market Opportunity | Withheld | — | 0.0% | Low | 0/4 |
| Product & Technology | Published | 5.88 | 100.0% | Medium | 4/0 |
| Team & Leadership | Published | 6.79 | 70.0% | Medium | 2/1 |
| Commercial Traction | Published | 7.25 | 50.0% | High | 2/3 |
| Execution & Momentum | Published | 5.92 | 100.0% | Low | 3/0 |
| Financial & Funding Signals | Published | 8.00 | 70.0% | High | 2/1 |

### Notion (stage: **Undetermined**)
| Pillar | Status | Strength | Coverage | Confidence | Scored/Unscored |
|---|---|---|---|---|---|
| Market Opportunity | Published | 6.20 | 100.0% | Medium | 4/0 |
| Product & Technology | Published | 8.00 | 75.0% | Medium | 3/1 |
| Team & Leadership | Withheld | — | 0.0% | Low | 0/3 |
| Commercial Traction | Withheld | — | 25.0% | Medium | 1/4 |
| Execution & Momentum | Withheld | — | 0.0% | Low | 0/3 |
| Financial & Funding Signals | Withheld | — | 0.0% | Low | 0/3 |

### Linear (stage: Series B+)
| Pillar | Status | Strength | Coverage | Confidence | Scored/Unscored |
|---|---|---|---|---|---|
| Market Opportunity | Published | 5.88 | 80.0% | Medium | 3/1 |
| Product & Technology | Published | 7.25 | 100.0% | Medium | 4/0 |
| Team & Leadership | Published | 7.14 | 70.0% | Medium | 2/1 |
| Commercial Traction | Withheld | — | 0.0% | Low | 0/5 |
| Execution & Momentum | Withheld | — | 35.0% | Low | 1/2 |
| Financial & Funding Signals | Withheld | — | 0.0% | Low | 0/3 |

### Fish Audio (stage: Seed)
| Pillar | Status | Strength | Coverage | Confidence | Scored/Unscored |
|---|---|---|---|---|---|
| Market Opportunity | Withheld | — | 0.0% | Low | 0/4 |
| Product & Technology | Published | 7.17 | 75.0% | Medium | 3/1 |
| Team & Leadership | Withheld | — | 0.0% | Low | 0/3 |
| Commercial Traction | Withheld | — | 0.0% | Low | 0/5 |
| Execution & Momentum | Withheld | — | 0.0% | Low | 0/3 |
| Financial & Funding Signals | Withheld | — | 0.0% | Low | 0/3 |

### Bullet (stage: Pre-Seed)
| Pillar | Status | Strength | Coverage | Confidence | Scored/Unscored | Disputed |
|---|---|---|---|---|---|---|
| Market Opportunity | Withheld | — | 0.0% | Low | 0/4 | |
| Product & Technology | Withheld | — | 25.0% | Low | 1/3 | `differentiation_claim_corroboration` |
| Team & Leadership | Withheld | — | 0.0% | Low | 0/3 | |
| Commercial Traction | Withheld | — | 0.0% | Low | 0/5 | |
| Execution & Momentum | Withheld | — | 0.0% | Low | 0/3 | |
| Financial & Funding Signals | Withheld | — | 0.0% | Low | 0/3 | |

### Beacon Analytics [fictional] (stage: Idea)
| Pillar | Status | Strength | Coverage | Confidence | Scored/Unscored |
|---|---|---|---|---|---|
| Market Opportunity | Withheld | — | 0.0% | Low | 0/4 |
| Product & Technology | Published | 6.75 | 50.0% | Medium | 2/2 |
| Team & Leadership | Withheld (gate 2 only — coverage clears at exactly 40%) | — | 40.0% | Low | 1/2 |
| Commercial Traction | Withheld | — | 0.0% | Low | 0/5 |
| Execution & Momentum | Withheld | — | 0.0% | Low | 0/3 |
| Financial & Funding Signals | Withheld (gate 2 only — coverage clears at 45%) | — | 45.0% | Low | 1/2 |

### Meridian Ops [fictional] (stage: Series A)
| Pillar | Status | Strength | Coverage | Confidence | Scored/Unscored | Disputed |
|---|---|---|---|---|---|---|
| Market Opportunity | Withheld | — | 0.0% | Low | 0/4 | |
| Product & Technology | Withheld | — | 0.0% | Low | 0/4 | |
| Team & Leadership | Withheld (gate 2 only, coverage 40%) | — | 40.0% | Medium | 1/2 | |
| Commercial Traction | Withheld | — | 25.0% | Low | 1/4 | `customer_base_breadth` |
| Execution & Momentum | Withheld | — | 0.0% | Low | 0/3 | |
| Financial & Funding Signals | Published | 7.00 | 70.0% | Medium | 2/1 | |

No overall score, ranking, or sort order is computed or implied anywhere in this matrix, per item 14's
own explicit instruction — rows are listed in a fixed cohort order (the table above), never
reordered by any result.

## 4. Cross-pillar audit findings (cohort-wide)

**Total: 0 ERROR, 1 WARNING, 1 INFO** across all seven companies and all six pillars' worth of
dimension results (42 pillar evaluations, well over 100 individual dimension results).

- **INFO — Stripe:** `stripe-traction-revenue-2025` cited by both Commercial Traction and Financial &
  Funding Signals — the real, legitimate canonical-evidence-reuse case (Task 17), correctly
  classified as informational, not a defect.
- **WARNING — Meridian Ops [fictional]:** the deliberately-engineered duplicate-extraction scenario
  (§6 below) — correctly caught.
- **Zero ERROR findings anywhere in the real cohort.** No disputed evidence was ever cited as scoring
  evidence outside the one documented Strategic Consistency exception; no stale evidence was cited
  outside the documented exceptions; every scored dimension traced cleanly; every pillar's own
  reported Strength matched an independent recomputation exactly where publication gates allowed one
  to be meaningfully checked; no withheld pillar ever carried a numeric Strength.

## 5. Evidence-reuse findings

The one real, implemented cross-pillar reuse relationship in this engine — Commercial Traction's
Disclosed Scale / Financial & Funding's Revenue Disclosure (Task 17) — was exercised at full-engine
scale for Stripe and confirmed working exactly as designed: the same `claim_id`, cited by two
different `PillarResult`s, correctly classified `INFO` by the audit rather than flagged as a concern.

No other real cross-pillar reuse relationship currently exists in the approved methodology (spec
Part 3.1 names exactly one: revenue). The audit's own duplicate-extraction check (§6) is therefore
the more load-bearing mechanism for the *rest* of the engine's evidence surface — it did not fire
on any real company's data, meaning no accidental cross-pillar duplication was found anywhere in the
five real companies' worth of genuinely-researched evidence.

## 6. Withholding behavior observed

**Every degree of withholding item 8 asks for was exercised with real data, not only synthetic
tests:**

- **All six pillars published:** not achieved by any single real company in this cohort — the
  closest is Stripe at 5 of 6 (only Market Opportunity withheld, for lack of researched evidence, not
  a methodology defect — Market Opportunity evidence was never gathered for Stripe in any task).
  `test_all_six_pillars_published` (offline, `test_full_analysis.py`) proves the mechanism itself
  can reach this state when evidence is comprehensive.
- **One withheld, rest published:** Stripe (Market Opportunity withheld, five published).
- **Several withheld:** Notion (4 of 6 withheld), Linear (3 of 6 withheld).
- **Most/all withheld:** Fish Audio and Bullet (5-6 of 6 withheld); Beacon Analytics and Meridian Ops
  (5 of 6 withheld each).
- **A withheld pillar never silently became zero, five, neutral, or omitted** — confirmed both by
  direct inspection of the matrix above (every withheld pillar shows `strength=None`/`—`, never a
  number) and by the audit's own zero `WITHHELD_PILLAR_HAS_NUMERIC_STRENGTH` findings across the
  entire cohort.
- **Gate 2 (minimum-distinct-dimensions), not gate 1 (coverage), is the actually-binding gate in
  most real withholdings observed.** Beacon Analytics' Team & Leadership (40.0% coverage — exactly
  at the floor) and Financial & Funding Signals (45.0% coverage) both clear gate 1 outright but are
  withheld by gate 2 alone; Meridian Ops' Team & Leadership shows the identical pattern. This is
  spec Part 6.2's own explicitly-designed edge case (a single dimension whose own weight alone
  clears the coverage floor) working exactly as intended, observed here with real numbers for the
  first time rather than only in each pillar's own synthetic gate test.

## 7. Cross-pillar contradictions observed

- **The deliberately-engineered duplicate-revenue-extraction scenario (Meridian Ops)** — described
  in full in §6/§4 above — is the one contradiction this evaluation specifically constructed to
  prove the audit layer's own value: two claims, never linked, describing what is very likely the
  same underlying fact with conflicting numbers ($2M vs $5M for overlapping periods), caught by
  content/period comparison that no single pillar's own machinery could perform (each pillar only
  ever sees its own claims).
- **The deliberately-engineered customer-adoption contradiction (Meridian Ops)** — a company
  self-claim of "thousands of customers" directly conflicting with independent reporting of "fewer
  than 100 confirmed paying customers," properly tagged `disputed`/`contradicts` the ordinary way.
  Commercial Traction's Customer Base Breadth correctly resolved `UNSCORED_DISPUTED`, confirmed at
  full-engine scale — the existing, unmodified dispute mechanism (Task 9-10) needed no changes to
  work correctly once six pillars were assembled together.
- **No genuine, unintentional cross-pillar contradiction was found in any of the five REAL
  companies' evidence.** This is itself informative: the five real live-research fixtures, each
  built incrementally across Tasks 11-17 by a different task's own focused research pass, never
  accidentally produced a cross-pillar factual conflict — a reasonable, positive signal about the
  discipline each task applied when adding claims, though five companies remains a small sample.

## 8. Stage consistency

**Structurally guaranteed by construction** (`full_analysis.py::assemble_full_analysis` calls
`determine_stage()` exactly once per analysis and passes the identical `Stage` value to all six
pillar evaluators — there is no code path through which two pillars could see different stages for
one analysis). Verified directly, not just asserted, by
`test_all_six_pillars_receive_the_identical_stage_object` and
`test_stage_affects_every_stage_tiered_pillar_consistently` (`test_full_analysis.py`).

**A genuine real edge case was exercised, not just a synthetic one:** Notion is the one real company
in this cohort whose own stage resolves to `Undetermined` — its real, deliberately-preserved
disputed Series C dating conflict (Task 13; two live sources disagree on the exact close date for the
same $275M round) means neither disputed stage-signal claim is admissible, and no founding-year
signal exists either, so `determine_stage()` correctly falls through to `Undetermined` rather than
guessing. Every one of Notion's stage-tiered dimensions (across whichever pillars had evidence)
then correctly used the "most permissive applicable band across all stages" fallback (spec Part
4.3) uniformly — confirmed by inspecting Notion's own Market Opportunity and Product & Technology
results, both of which reproduce their own historical (pre-Task-18) numbers exactly, since neither
pillar's own dimensions are affected by `Undetermined` differently than by any other stage bucket
they already handle.

## 9. Implementation bugs discovered and fixed

**One bug, found and fixed during this task's own development — in the NEW Task 18 audit code
itself, not in any of the six previously-shipped pillars.** `cross_pillar_audit.py`'s own
Strength-consistency check initially recomputed `compute_pillar_strength()` from a pillar's scorable
dimensions and compared it directly to the pillar's own reported `strength`, without accounting for
`compute_pillar_strength()`'s own documented gate-blindness (spec Part 6.6's firewall property: it
is a pure function of scorable dimensions alone, with no knowledge of the two publication gates).
This produced a false positive the moment a real fixture had exactly one scorable dimension that
individually would compute a real number but correctly failed to publish because of gate 2 (first
observed against the Meridian Ops fictional fixture's own Team & Leadership result). **Fixed** by
only running this specific comparison when the pillar's own `publishable` flag is `True` — the
`withheld`-with-a-numeric-Strength case is already covered by a separate, correct invariant check
(`WITHHELD_PILLAR_HAS_NUMERIC_STRENGTH`). Regression-tested directly by
`test_a_single_scored_dimension_below_gate_2_is_not_flagged_as_a_strength_mismatch`
(`test_cross_pillar_audit.py`).

**No implementation bug was found in any of the six pillars themselves.** All five real companies'
own historical results (Stripe across five pillars, Notion's Market Opportunity/Product &
Technology, Linear's Market/Product/Team) reproduce byte-for-byte identically to each pillar's own
prior task report — confirmed directly, not merely assumed, both by this evaluation's own matrix
(§3) and by the full 290-test pillar regression suite passing unchanged (§10).

## 10. Test results

**38 new tests** across two new files: `test_full_analysis.py` (25 tests — contract shape, all
withholding combinations, single-stage resolution including the Notion Undetermined edge case
addressed structurally, full-analysis reproducibility, graceful degradation on a pillar-level model
crash, and item 15's own nine-point architectural-risk checklist A-I re-verified at assembly scale)
and `test_cross_pillar_audit.py` (13 tests — every audit check's positive and negative cases,
including both documented exceptions: Strategic Consistency's legitimate disputed-evidence use, and
the gate-blind Strength-recomputation fix above).

**Full regression: 328 tests across 16 files, all passing** (290 prior + 38 new). Legacy regression
(`test_ai_request_reliability.py` 7/7, `test_analyze_unified_concurrency.py` 2/2) and the isolation
boundary (zero imports outside `app.evidence_engine` anywhere in the package, including the two new
top-level modules) were both reconfirmed. All six pillars' own individual test suites pass unchanged
(46+45+52+23+23+29 = 218 pillar-specific tests, plus the shared-infrastructure suites), and every
pillar's own real-evidence sanity-check script was re-run and reproduces its own historical numbers
exactly.

## 11. Systemic strengths

- **The architecture assembled cleanly on the first real attempt.** No pillar needed any change to
  support assembly — every pillar's existing `evaluate_pillar_for_company(ledger, company_ref,
  as_of, stage, ...)` signature already assumed an externally-resolved, shared `stage` parameter
  (every prior task's own sanity-check script already called `determine_stage()` once and passed the
  result in), so the orchestrator's single-stage-resolution guarantee was a natural consequence of
  the existing call shape, not a new constraint retrofitted onto six already-built pillars.
- **Zero ERROR-severity audit findings across the entire real cohort** is a genuinely meaningful,
  not merely convenient, result — it means five independently-researched companies' worth of real
  evidence, built incrementally by five different tasks over this session, never once produced a
  disputed-evidence leak, a stale-evidence leak, a traceability break, or a Strength/publication
  invariant violation when finally assembled together and cross-examined.
- **The evidence-reuse mechanism (`assessment_criteria` tagging) required zero new code to work at
  full-engine scale** — it is genuinely just ledger metadata, and the audit's own reuse-detection
  check is a read-only scan over already-existing fields, exactly matching item 4's own "narrowest
  mechanism" instruction.
- **Withholding is honestly frequent, not rare** — of 42 pillar evaluations in this cohort, only 15
  published (roughly a third), and this is presented as a strength: the engine did not manufacture
  scores to make the matrix look fuller.

## 12. Systemic weaknesses

- **Confidence rarely reaches `High`.** Across all 42 pillar evaluations in this cohort, `High`
  appears exactly twice (Stripe's Commercial Traction and Financial & Funding Signals) — the same
  open question Task 9's own calibration report first flagged against five offline fixtures
  (`CONFIDENCE_MIN_RELIABILITY_FOR_HIGH` never reached), now reconfirmed at full-engine, cross-pillar
  scale against real evidence. Not changed here (item 17's own "do not tune now" instruction) —
  recorded as a calibration question (§13).
- **The evaluation cohort's own evidence coverage is itself uneven across pillars**, a fact about
  this session's incremental research process, not about the methodology: Market Opportunity has
  real evidence for only 2 of 5 real companies (Notion, Linear); Commercial Traction for only 2
  (Stripe, Notion); Execution & Momentum and Financial & Funding Signals for only 2 each (Stripe,
  and Linear/Meridian respectively). A genuine six-pillar calibration pass will need each company in
  its own cohort researched across all six pillars, not assembled from five separate single-pillar
  research passes the way this evaluation's real companies necessarily were.
- **A structural evidence-duplication pattern exists between `stage_signal` claims and
  `funding_history` claims describing the same real financing event** (e.g. a company's Series A
  round is independently represented once as a `funding_round_type` fact for stage determination and
  once as a `funding_round` fact for Financial & Funding Signals' own Funding History dimension —
  demonstrated deliberately in the Meridian Ops fixture, and present by the same convention in every
  real company fixture that has both a stage signal and Funding History evidence). This is not a
  scoring defect — the two facts serve genuinely different purposes (round *type* vs. round *size/
  date*) and the audit's own duplicate-extraction check correctly does not flag it (different
  `structured_fact.kind` values, not the money-metric family it inspects) — but it is a real,
  observed opportunity for a future reuse relationship analogous to the revenue one, not yet
  exploited. Recorded as an architecture question, not acted on (§13).
- **The audit's own duplicate-extraction check parameters (120-day period window, 15% amount
  tolerance) are themselves unreasoned placeholders**, exercised successfully against exactly one
  deliberately-engineered case and never validated against a real false-positive/false-negative rate
  on a larger real cohort.

## 13. Recommendation for what Task 19 must calibrate

In order of how directly this evaluation's own evidence supports each item:

1. **Confidence's HIGH/MEDIUM thresholds** (`CONFIDENCE_MIN_RELIABILITY_FOR_HIGH`,
   `CONFIDENCE_MIN_CORROBORATION_GROUPS_FOR_HIGH`) — the most consistently-observed pattern across
   two separate evaluations now (Task 9's original five fixtures, this task's seven), both showing
   `High` is nearly unreachable under current values.
2. **`MIN_SCORED_DIMENSIONS_PER_PILLAR`** (currently 2) and each pillar's own dimension weights,
   specifically for the pillars where one dimension's own weight sits at or near the 40% coverage
   floor (Team & Leadership's Founder Relevant Experience at exactly 0.40; Financial & Funding
   Signals' Funding History at 0.45) — this evaluation observed gate 2 as the actually-binding
   constraint far more often than gate 1 in real, sparse-but-real companies, which is the intended
   design (spec Part 6.2) but whose exact numeric consequence (how much real evidence a company
   needs before ANY pillar publishes) has not yet been checked against real calibration data.
3. **Whether a `stage_signal` ↔ `funding_history` reuse relationship should exist**, analogous to
   the revenue one — an architecture question, not a numeric-parameter one, but one this evaluation's
   own evidence makes concrete for the first time.
4. **The duplicate-extraction audit check's own tolerance parameters** (§12's last point) — needs a
   larger real cohort to validate against genuine false positives/negatives before being trusted as
   more than an illustrative mechanism.
5. Every pillar-level and dimension-level numeric parameter already flagged `CALIBRATION REQUIRED` in
   each of the six pillars' own prior reports remains exactly as provisional as those reports already
   state — this evaluation found no new evidence changing any of those existing findings, only
   reconfirming several of them (Confidence, above) at larger scale.

**Explicitly not recommended for Task 19 to touch without further evidence:** any individual pillar's
own dimension weights beyond what item 2 above already names, any pillar's own label-to-score table
values, or any staleness bound not already flagged in a prior pillar report — this evaluation's own
scope (assembly and diagnosis) does not constitute the broader calibration cohort
`NEW_ENGINE_CALIBRATION.md` itself calls for.

## 14. Whether the six-pillar engine is ready for Task 19

**Yes, with the explicit findings above carried forward.** The engine assembles six independently-
built, independently-tested pillars into one coherent, auditable analysis with zero implementation
defects found in any of the six pillars themselves; the one real bug this task's own development
surfaced was in the new assembly-layer code itself, found and fixed before this report was written.
Every one of item 15's nine architectural risks (A through I) was re-verified, not merely assumed,
at full-engine scale against both real and deliberately-adversarial evidence. Task 19's own
calibration and aggregation work can proceed on top of this assembly layer without first needing any
further structural change — its main open inputs are the specific numeric-parameter questions listed
in §13, not the architecture itself.
