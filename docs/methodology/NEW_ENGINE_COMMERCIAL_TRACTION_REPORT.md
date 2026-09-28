# VentureGPS Evidence Engine — Commercial Traction Pillar (Task 15)

**Status: implemented and tested — the fourth pillar in `app/evidence_engine/`, on the exact
architecture Product & Technology (Tasks 8-12), Market Opportunity (Task 13), and Team & Leadership
(Task 14) already validated.** No shared scoring philosophy, evidence ledger, classification system,
provenance system, confidence model, stage model, or publication gate was redesigned to build this.
This document does not rewrite `NEW_ENGINE_LIVE_EVALUATION.md`, `NEW_ENGINE_REMEDIATION_REPORT.md`,
`NEW_ENGINE_MARKET_OPPORTUNITY_REPORT.md`, or `NEW_ENGINE_TEAM_LEADERSHIP_REPORT.md` — all four of
the engine's prior historical reports are untouched by this task.

## 1. Implemented dimensions (spec Part 3.3, unmodified)

All five dimensions from the approved specification, exactly as weighted and staleness-bound there
— no dimension invented, renamed, or dropped:

| Dimension | Weight | Category | Staleness | Admissible evidence (spec) |
|---|---|---|---|---|
| Disclosed Scale | 0.25 | Computed | 18 months | One dated, disclosed absolute figure (revenue, GMV, ARR, active users, paying customers) |
| Growth Trajectory | 0.25 | Computed | Newer point ≤18 months | Two dated figures for the *same* metric, both confirmed actuals |
| Customer Base Breadth | 0.20 | Classified | 18 months | Named customer count/band + segment mix |
| Commercial Validation | 0.15 | Classified | 24 months | Named contracts, renewals, or enterprise-partnership announcements |
| Retention/Renewal Signal | 0.15 | Classified | 12 months | A specifically disclosed retention/renewal/churn figure |

**Two Computed dimensions, three Classified** — matching the spec's own table exactly. This is the
first pillar in this engine with more than one Computed dimension.

### 1.1 Computed dimensions are pure deterministic functions, no model call at all

Unlike Product & Technology's one Computed dimension (which goes through `ExtractionModel` because
its own fact is a simple boolean — "was an artifact observed"), Disclosed Scale and Growth
Trajectory read `Claim.structured_fact` directly and compute their score with plain Python (parse
amount/date → band/CAGR → score). `ExtractionResponse` (`classification.py`) is hardcoded to
`artifact_observed: bool` and was not generalized for this — extending it would have been a
shared-engine change affecting Product & Technology's own tested shape for no real benefit, since
spec Part 6.1's own worked example for Growth Trajectory (`f(point_a, point_b, window) -> CAGR ->
scale-tiered band -> score`) already describes a pure function with no model call in it at all. This
mirrors the precedent Market Opportunity already set for magnitude-bearing evidence (Task 13): the
"AI extraction" step is simulated, as everywhere else in this offline engine, by claims already
carrying their typed fact.

### 1.2 Existence vs. magnitude (item 5)

Customer Base Breadth's label set (`NOT_DISCLOSED` / `SMALL` / `MODERATE` / `LARGE`) encodes only
the narrowest claim the cited evidence supports — a named count/band, nothing about revenue
contribution, retention, or deployment breadth. A bare customer logo carries no `structured_fact`
and is structurally invisible to the classifier (falls through to `NOT_DISCLOSED`), directly
implementing item 7's "customer logos alone are weak evidence." The real Stripe sanity-check finding
below (§7) demonstrates this distinction concretely: a named enterprise relationship is admissible
*Commercial Validation* evidence but was deliberately **not** also asserted as a Customer Base
Breadth band, since a handful of named logos does not establish a customer *count*.

### 1.3 Metric identity is never collapsed (item 6)

Every magnitude-bearing claim carries an explicit `metric` field (`revenue` / `arr` / `gmv` /
`bookings` / `active_users` / `paying_customers`) that flows unchanged into the dimension's own
`classification_label` and `rationale` — a GMV-only company is reported as scored from GMV, never
silently reframed as revenue. `TRACTION_METRIC_PREFERENCE_ORDER` (`parameters.py`) is the one,
documented, non-magnitude-based tie-break used when more than one metric type qualifies: revenue and
ARR (the most direct signal of a company's own realized scale) rank above paying-customer/active-user
counts, which rank above GMV/bookings (the largest, least directly comparable pass-through figures)
— specifically so a bigger GMV number can never out-rank a smaller, more meaningful revenue figure.
A claim whose `structured_fact.kind` is anything other than `"traction_metric"` (a funding round, a
valuation) is structurally invisible to the parser regardless of which dimension's
`assessment_criteria` it was tagged with — cross-pillar leakage prevented mechanically, the same
`assessment_criteria`-enforcement pattern Market Opportunity's own report already documented (Task
13 §2), not by convention. All of this is proven, not just claimed, in §6.6 below with real data
where GMV was ~280x larger than revenue for the same company in the same year.

### 1.4 Company disclosures (item 9)

No dimension in this pillar requires independent sourcing (`requires_independent_source` is used
nowhere in `commercial_traction.py`) — a private company's own disclosed revenue/customer/retention
figures are legitimate, admissible evidence per spec Part 3.3's own wording, the same trust posture
Team & Leadership already established for self-reported biographies. `source_type` is preserved
unconditionally on every claim so a downstream reader can always tell a company disclosure from
independently-verified reporting; what every Classified label instead requires is
`requires_named_entity_fact` — a specificity bar, reused unchanged from Team & Leadership, blocking
vague, unsupported claims regardless of source.

### 1.5 Conflicting metrics (item 10) — reuses the ledger's existing rule, adds no new code

This pillar adds **no new conflict-resolution mechanism**. Two claims disagreeing about the same fact
are tagged `support_status=disputed` by whoever authors them (the engine's established, unmodified
convention since Task 9), and `ledger.py::resolve_dimension_evidence` already excludes disputed
claims from `admissible` entirely — exactly the fail-closed behavior item 10 asks for ("unresolved
material conflicts fail closed... while remaining visible in the ledger"). Two claims describing
genuinely *different* facts (different metrics, different periods) are never disputed in the first
place; they are handled by this pillar's own metric-keyed grouping (§1.3), never merged or averaged.

## 2. Stage awareness (item 11) — documented per dimension

| Dimension | Stage behavior | Reasoning |
|---|---|---|
| Disclosed Scale | Stage-tiered (early > growth > established, for the identical figure) | The same absolute magnitude is less expected, and therefore more remarkable, from a younger company — the same reasoning Product & Technology's and Team & Leadership's own stage-indexed tables already use. |
| Growth Trajectory | **Flat / stage-independent** | A genuine, documented ambiguity, resolved narrowly rather than invented: high percentage growth off a small base is the unremarkable *norm* at early stage (arguing to score it lower there), but a growth *rate* is simultaneously the primary signal investable at that stage (arguing the opposite). This methodology has no calibrated basis to choose between them — deferred to a future calibration pass, the same discipline Team & Leadership applied to its own Founder Relevant Experience label-set ambiguity. |
| Customer Base Breadth | Stage-tiered, same direction as Disclosed Scale | Same reasoning — magnitude is more remarkable earlier. |
| Commercial Validation | Stage-tiered, same direction | Same reasoning — a named enterprise commitment is more remarkable earlier. |
| Retention/Renewal Signal | **Flat / stage-independent** | A retention-quality band (e.g. a 95% net revenue retention figure) means the same thing regardless of company age. The spec's own explicit instruction that this dimension must never be inferred from company age reinforces treating age/stage as irrelevant to its score entirely — the same reasoning Team & Leadership already applied to Founder Relevant Experience/Public Track Record. |

**Stage never manufactures traction (item 11's own explicit two-sided instruction).** An early-stage
company with zero documented evidence receives the identical Unscored outcome any other stage would
— proven directly by `test_early_stage_with_zero_traction_evidence_is_not_manufactured_a_score`.
Stage-tiering only changes which score a band that already cleared its own evidence bar receives; it
never lowers that bar and never invents a data point.

## 3. How unknown private metrics are prevented from becoming weak scores (item 4 of the completion
##    report, the pillar's own central, non-negotiable rule)

Structurally, not narratively:

- Every dimension's "no qualifying evidence" path returns `score=None` with an explicit
  `UNSCORED_*` availability reason — there is no code path anywhere in `commercial_traction.py` that
  converts absence into zero, a below-average number, or an estimate. `test_missing_revenue_is_
  unscored_not_zero`, `test_missing_retention_is_unscored_not_weak`, and `test_missing_customer_
  count_is_unscored` each prove this for a specific dimension directly.
- `compute_pillar_strength` (shared, unmodified `scoring.py`) is a **renormalized average over only
  the `SCORABLE` dimensions** — an `Unscored` dimension is excluded from the average entirely, never
  averaged in as a low number. The dedicated regression test for the engine's own original failure
  mode (§6.5 below) demonstrates this with real weights: two genuinely undisclosed dimensions
  (Disclosed Scale, Growth Trajectory) never drag a published Strength down, because they are simply
  not part of the average.
- Retention specifically can **never** be inferred from company age, customer logos, reviews,
  traffic, social activity, funding history, customer count, or general popularity (item 8's own
  explicit list) — `WellBehavedRetentionRenewalClassifier` reads only `structured_fact.kind ==
  "retention_signal"`, a fact no other code path in this pillar ever produces, so none of those
  signals has any route into a retention score at all. Proven directly by `test_retention_is_never_
  inferred_from_company_age_or_popularity`.
- Absence affects `coverage_pct`/`confidence` only, never `Strength` — the shared firewall property
  (`compute_pillar_strength`/`compute_pillar_coverage_pct`/`compute_pillar_confidence` never read
  each other's inputs, unmodified since Task 8) makes this a structural guarantee, not a per-pillar
  convention this module could quietly violate.

## 4. Shared-engine changes (item 8) — one genuine defect fix, no new shared code otherwise

**Zero new shared-layer factories or fields were needed** — unlike Market Opportunity (which added
`EvidenceItem.structured_fact`) and Team & Leadership (which added `requires_named_entity_fact`),
this pillar's three Classified dimensions reuse all three existing `classification.py` factories
unchanged (`requires_named_entity_fact` for Customer Base Breadth/Retention, `requires_minimum_
distinct_facts` for Commercial Validation — the identical mechanism Leadership Composition already
established for named hires, Task 14).

**One genuine, pillar-local defect was found and fixed via the real-evidence sanity check, not a
shared-layer change:** the initial implementation of Growth Trajectory resolved its evidence through
the same generic per-claim staleness filter every other dimension uses, applying the dimension's
18-month staleness bound to *both* points of a growth pair. Spec Part 3.3's own staleness column for
this dimension reads **"newer point ≤18 months old"** — a bound on the newer point only; the older
point exists purely to establish a rate's starting baseline and carries no separate staleness meaning
of its own. Under the original (incorrect) implementation, a real, genuinely useful older revenue
figure was silently discarded the moment it aged past 18 months, even though the newer figure paired
with it was current — exactly reproduced by Stripe's real 2024/2025 revenue figures (§7 below): the
2024 point was 550 days old as of this evaluation, one day past the (incorrectly-applied) 548-day
bound, so Growth Trajectory came back `Unscored` despite two perfectly good, real, dated actuals
existing. **Fixed** by resolving this dimension's raw admissibility with no staleness ceiling
(`GROWTH_TRAJECTORY_RESOLUTION_STALENESS_DAYS`, disputed-exclusion and independence-group dedup
still apply) and applying the real 18-month bound explicitly, only to whichever point is chosen as
the newer one of a qualifying pair (`commercial_traction.py::evaluate_growth_trajectory`). This is a
**pillar-local fix** (`commercial_traction.py` and its own two new `parameters.py` constants only) —
it does not touch `ledger.py`, `scoring.py`, `classification.py`, or any other pillar's staleness
handling, so Product & Technology, Market Opportunity, and Team & Leadership's own staleness
semantics (all correctly "blanket per-claim," matching their own spec wording) are untouched and
unaffected, confirmed by their full regression suites reproducing identically (§6 below). Two
dedicated regression tests were added: `test_growth_trajectory_uses_an_old_baseline_point_if_the_
newer_point_is_current` and `test_growth_trajectory_rejects_a_pair_whose_newer_point_has_gone_stale`.

## 5. Test results

**46 new tests, `test_commercial_traction.py`, all passing** — covering strong documented traction
across all five dimensions; partial/sparse evidence; completely private metrics; missing revenue/
retention/customer-count (each proven Unscored, not zero/weak); first-party vs. independently-
corroborated revenue disclosure; conflicting revenue values and conflicting customer counts (fail
closed); ARR/bookings/GMV/funding/valuation/user-count-vs-paying-customer-count confusion (six
dedicated tests, each proving the correct metric is preserved and the wrong one never substituted);
bare customer-logo vs. attributable case-study evidence; stale evidence; duplicated/syndicated
commitment claims; disputed claims; invalid evidence references; invalid labels; unsupported
classification; classification recovery; prompt-injection resistance (an injection-*compliant*
adversarial mock, still blocked by evidence-sufficiency validation); Computed-dimension missing/
ambiguous input (one data point, too-short window, an actual paired with a projection, a declining
metric getting its own label rather than being folded into "slow," a non-USD figure correctly
excluded); the two coverage/count gates; deterministic reproducibility; full traceability; graceful
withholding under a crashing model; stage-tiering in both directions (magnitude dimensions higher
earlier, rate/quality dimensions flat); the two Growth Trajectory staleness-fix regression tests
(§4); and the dedicated original-failure-mode regression (§6.5).

**Full regression: 193 tests across 12 files, all passing** (147 prior + 46 new). Legacy regression
(`test_ai_request_reliability.py` 7/7, `test_analyze_unified_concurrency.py` 2/2) and the isolation
boundary (zero imports outside `app.evidence_engine` anywhere in the package) were both reconfirmed
**after** the live-research additions and the Growth Trajectory fix, not only before. Product &
Technology's own Task 11/12 results, Market Opportunity's own Task 13 sanity-check results, and Team
& Leadership's own Task 14 sanity-check results were all re-run and reproduce identically after this
pillar's addition — the new Commercial-Traction-tagged claims added to `live_research/stripe.py`/
`notion.py` are invisible to all three other pillars' evaluators, which only ever read claims tagged
with their own `assessment_criteria`.

## 6. The original failure-mode regression (item 14)

`test_established_company_with_strong_adoption_but_undisclosed_private_metrics_scores_well`
constructs exactly the scenario that motivated this engine: an established, privately-held company
with real, strong, documented commercial adoption (a large named customer base, three named
commercial commitments, a real disclosed retention figure) but **no** disclosed revenue or growth
figures, both genuinely private.

**Result:** Disclosed Scale and Growth Trajectory are honestly `UNSCORED_NO_EVIDENCE`. Customer Base
Breadth, Commercial Validation, and Retention/Renewal Signal all score from real evidence. The pillar
**publishes** (3 scored dimensions clear both gates) with **Strength = 7.85** — driven entirely by
the three genuinely-documented dimensions, never diluted or dragged down by the two honestly-private
ones, because Strength is a renormalized average over only the scorable dimensions (§3). Coverage
correctly reports 50%, honestly reflecting the two undisclosed dimensions rather than hiding them.

A stricter sibling test, `test_withholds_rather_than_manufactures_a_score_when_coverage_is_
insufficient`, confirms the other required half: when only two small-weighted dimensions score
(35% coverage, below the 40% floor), the pillar **withholds** entirely (`strength=None`) rather than
publishing a diluted or manufactured number — the coverage gate, not a fabricated low score, is what
communicates "insufficient evidence" to a reader.

## 7. Small real-evidence sanity check (item 15)

**Method note, identical to Tasks 11-14: research used this session's own `WebSearch`/`WebFetch`
tools, not the project's paid OpenAI/Tavily infrastructure — no paid API call was made or required.**
Reused Stripe and Notion from Tasks 11-14 (their `live_research/*.py` files extended with a small
number of new, genuinely-researched, real Commercial-Traction-tagged claims — see each file's own
"Task 15 addition"). **Stripe was chosen specifically as item 15's own "established private company
with meaningful observable adoption but incomplete public private-metric disclosure"** — real,
well-sourced revenue and payment-volume figures and named enterprise customers exist for Stripe, but
genuinely no disclosed retention/renewal figure or overall customer count was found anywhere in this
pass. Reproduce with `python -m app.evidence_engine.live_research.run_commercial_traction_sanity_check`.

### 7.1 Results

| Company | Publishable | Strength | Coverage | Disclosed Scale | Growth Trajectory | Customer Base Breadth | Commercial Validation | Retention |
|---|---|---|---|---|---|---|---|---|
| Stripe | Yes | 7.25 | 50% | 8.0 `LARGE` ($6.8B 2025 revenue) | 6.5 `MODERATE` (33.4% CAGR) | Unscored (no count disclosed) | Unscored (see §7.3) | Unscored (genuinely undisclosed) |
| Notion | No (withheld) | — | 25% | 9.5 `LARGE` ($500M ARR, Sept 2025) | Unscored (no second clean point found) | Unscored, `UNSCORED_STALE` (see §7.4) | Unscored (not researched this pass) | Unscored (not researched this pass) |

**Zero traceability violations** across all real scored dimension results (directly verified via
`verify_traceability()` against each company's own claim-ID set).

### 7.2 The GMV-vs-revenue risk, demonstrated with real, dramatic numbers

Stripe's own 2025 annual letter discloses total payment volume (TPV) of **$1.9 trillion** for
2025 — roughly **280 times larger** than its independently-reported **$6.8 billion** revenue for the
same year. Both figures are real, both are admissible, both are tagged `assessment_criteria =
["disclosed_scale"]`. **Confirmed programmatically that the TPV claim was never cited by any
dimension result** — `TRACTION_METRIC_PREFERENCE_ORDER` correctly chose revenue over the vastly
larger GMV-family figure, exactly the "do not automatically choose the larger number" guarantee item
10 requires, demonstrated with the largest real magnitude gap this session's research has produced
for any metric-confusion risk in this engine.

### 7.3 A genuine, honest finding: Commercial Validation safely fails closed on ambiguous real text

Three named-customer facts were entered for Stripe (OpenAI, Anthropic — both drawn from one shared
source sentence naming several companies together — and a separate Orb-customers group: Vercel,
Glean, Replit, Supabase). The deterministic classifier counted 3 raw independence groups and proposed
`SUBSTANTIAL_VALIDATION`; the shared provenance-verification layer (`requires_minimum_distinct_
facts`, unchanged since Task 10) found only **2** are confirmed independent — the OpenAI and
Anthropic claims share an identical verbatim excerpt (the source names both companies in one
sentence with no company-specific quotable sub-fragment), which the Jaccard-similarity mechanism
correctly cannot distinguish from a genuine restatement. The classifier does not adapt its count
downward on retry (the same non-adaptive counting behavior Leadership Composition's own mock
classifier already has, Task 14), so the dimension **safely fails closed to `Unscored`** rather than
settling for the lower-but-real `SOME_VALIDATION` label it could have supported. This is disappointing
but correct: the engine's design deliberately prefers withholding over guessing whenever a model (or
its deterministic stand-in) cannot support its own claimed count on a second attempt. **Not fixed**
— changing the classifier specifically to recover a better Stripe score would be exactly the kind of
tuning item 15's own "do not tune the system so ... any recognizable company receives a desired
score" instruction forbids. Flagged as a known limitation of the deterministic mock classifiers'
non-adaptive retry behavior (§9), not a scoring-correctness defect — the mechanism's core behavior
(never manufacture SUBSTANTIAL_VALIDATION from an under-supported count) is exactly what it should be.

### 7.4 A second genuine finding: a real, well-sourced fact can still be honestly stale

Notion's own blog announced passing 100 million users on 2024-09-03. As of this evaluation
(2026-09-28), that is 755 days old — past Customer Base Breadth's 18-month (548-day) staleness bound
— so the dimension correctly reports `UNSCORED_STALE` despite the underlying fact being real and
well-sourced. This is the staleness mechanism working exactly as designed, not a bug, but it is worth
flagging honestly: an 18-month bound may be more aggressive than warranted for a slow-changing,
directional metric like a total-user-count milestone (unlike revenue, which genuinely needs
re-verification on a similar cadence) — a real, calibration-relevant observation (§9), not acted on
here per the "not a calibration project" instruction.

### 7.5 Checked against item 15's own failure-mode checklist

- **Missing private metrics remaining Unscored:** confirmed for both companies — Stripe's retention
  and customer count, Notion's growth/validation/retention, all honestly `Unscored`, none defaulted
  to a low number.
- **Company disclosures appropriately labeled:** confirmed — the TPV claim is tagged `company_
  disclosure` (Stripe's own annual letter); the revenue figures are tagged `independent_reporting`
  (Axios/SaaStr, both citing The Information); `source_type` is preserved and visible on every claim.
- **Adoption evidence overstated:** not found — Notion's 100M-user claim is explicitly labeled "not
  specifically paying customers" in its own `named_entity` field (item 13's own required distinction),
  and Stripe's named customers were deliberately kept out of Customer Base Breadth (§1.2).
- **Revenue definitions remaining distinct:** confirmed — see §7.2's GMV finding.
- **Conflicting metrics failing safely:** Notion's ARR is reported wildly inconsistently across
  low-quality aggregator sources found during this pass ($300M/$500M/$600M/$610M/$865M for
  overlapping late-2025 periods) — rather than enter that noise as a disputed pair for the engine to
  resolve, only the single best-sourced figure (CNBC, on the record, attributed to a named
  co-founder) was entered as a ledger claim at all; the weaker figures were excluded by research
  judgment before ever reaching the ledger, a conservative choice documented directly in `notion.py`.
- **Stage behavior sensible:** Stripe (Growth stage, determined from its own tender-offer stage
  signal) and Notion (Undetermined — no round-type or founding-year signal was researched for this
  pass) both behaved as expected; no stage-tiered dimension scored from real evidence in this small
  pass to further stress-test the direction empirically (the offline suite already proves the
  direction for both stage-tiered and flat dimensions, §2).
- **Cross-pillar evidence leakage:** not found — confirmed programmatically that no claim tagged for
  another pillar's dimension was cited by any Commercial Traction result, and vice versa (the
  Task 14 university-prestige claim remains uncited, unaffected by this task's additions).

## 8. Provisional parameters requiring future calibration

Every weight, band cutoff, and label score below is `CALIBRATION REQUIRED`, exactly like every
number in the three prior pillars' own tables — none was set from real data, only reasoned to be
plausible enough to exercise the mechanism:

`COMMERCIAL_TRACTION_DIMENSION_WEIGHTS` (0.25/0.25/0.20/0.15/0.15), `TRACTION_METRIC_PREFERENCE_
ORDER` (the ordering itself, a reasoned position), `DISCLOSED_SCALE_MONEY_SMALL_MAX_USD`/`_MODERATE_
MAX_USD` ($1M/$20M cutoffs), `DISCLOSED_SCALE_COUNT_SMALL_MAX`/`_MODERATE_MAX` (10K/1M cutoffs),
`DISCLOSED_SCALE_LABEL_SCORES` and `CUSTOMER_BASE_BREADTH_LABEL_SCORES` (stage-tiered, 4-9.5),
`GROWTH_SLOW_MAX_PCT`/`_MODERATE_MAX_PCT` (20%/100% cutoffs), `GROWTH_TRAJECTORY_LABEL_SCORES`
(including the `DECLINING` band's own addition, §1 spec deviation, documented not asserted),
`GROWTH_ANNUALIZE_MIN_WINDOW_DAYS` (350 days, alongside the spec's own already-flagged `GROWTH_MIN_
WINDOW_DAYS` 180-day floor), `COMMERCIAL_VALIDATION_SOME_MIN_COUNT`/`_SUBSTANTIAL_MIN_COUNT` (1/3,
reused from Leadership Composition's own precedent), `COMMERCIAL_VALIDATION_LABEL_SCORES`,
`RETENTION_LABEL_SCORES`. Growth Trajectory's own stage-direction ambiguity (§2) is explicitly
deferred, not decided, pending real calibration data.

## 9. Remaining limitations

- **No FX normalization exists.** A money figure in any currency other than USD is retained in the
  ledger for transparency but does not currently contribute to Disclosed Scale or Growth Trajectory —
  a conservative, fail-closed limitation (`test_non_usd_money_figure_does_not_score_disclosed_scale`
  proves this directly), not encountered in this pass's real data (both companies report in USD) but
  real for any non-US-dollar-reporting company this engine might assess.
  - Segment mix (`structured_fact.segment` on Customer Base Breadth claims) is retained and available
  but does not independently move the score beyond the band itself — the spec gives no explicit rule
  for how mix should score, so it stays documentary context only (§1.2/`parameters.py`), a deferred
  calibration item rather than an invented scoring axis.
- **The deterministic mock classifiers' non-adaptive retry behavior** (§7.3) means a real over-claimed
  count fails all the way to `Unscored` rather than settling for a lower, still-supportable label —
  correct and safe, but conservative; a smarter classifier implementation (using provenance-verified
  counting internally, matching what the validator already does) could recover more real evidence in
  this specific situation. Not changed here, to avoid the appearance of tuning toward a specific
  company's outcome.
- **Notion's real 18-month-old user-count milestone going stale (§7.4)** raises a real question about
  whether an 18-month staleness bound is appropriate for every Customer Base Breadth fact, or whether
  slow-changing directional milestones deserve a longer bound than fast-changing ones — flagged, not
  acted on, per the "not a calibration project" instruction.
- Two real companies (Stripe, Notion) remains far short of a calibration cohort —
  `NEW_ENGINE_CALIBRATION.md`'s much larger plan is still the real path to final numbers, and this
  pass's own research did not specifically seek Commercial Validation or Retention evidence for
  Notion, or a second clean growth-trajectory point (§7.5).
- The scale-based stage-determination fallback `stage.py`'s own docstring has flagged as blocked
  since Task 9 ("needs Commercial Traction's Disclosed Scale, which does not exist yet") is now
  *technically* possible to build, since Disclosed Scale exists as of this task — but was deliberately
  **not** built here: it is a `stage.py` (shared-layer) feature addition, not a defect this pillar
  exposed, and this task's own scope constraints do not ask for it. Flagged as a natural next step
  for a future task, not attempted in this one.

## 10. Readiness for the eventual full-engine evaluation

Commercial Traction now behaves like the architecture the three prior pillars already proved:
evidence-traceable (zero violations, real and offline), deterministic after classification,
resistant to unsupported claims and metric confusion (the real-evidence pass directly demonstrates a
280x GMV-vs-revenue gap resolved correctly), explicit about uncertainty (distinct Unscored reasons —
no evidence, stale, disputed, uncorroborated, extraction-failed — all exercised with both offline and
real data), and willing to withhold (both individual dimensions and, when warranted, the full
pillar). It additionally demonstrates the engine's central Task 15 guarantee empirically, not just
narratively: an established company's genuinely undisclosed private metrics (Stripe's retention;
Notion's growth/validation/retention) never became a mediocre or negative score, and the one real
methodological bug this pass surfaced (Growth Trajectory's staleness bound) was found, fixed, and
regression-tested before this report was written. **Ready to join Product & Technology, Market
Opportunity, and Team & Leadership in a future combined evaluation once at least one more pillar
exists to make "full-engine" meaningful** — this task deliberately implements no overall
(cross-pillar) scoring and no additional pillar (Execution & Momentum and Financial & Funding Signals
both remain unbuilt), per its own explicit scope constraints.
