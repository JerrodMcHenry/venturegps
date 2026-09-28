# VentureGPS Evidence Engine — Financial & Funding Signals Pillar (Task 17)

**Status: implemented and tested — the sixth and final individual pillar in `app/evidence_engine/`,
on the exact architecture Product & Technology (Tasks 8-12), Market Opportunity (Task 13), Team &
Leadership (Task 14), Commercial Traction (Task 15), and Execution & Momentum (Task 16) already
validated.** No shared scoring philosophy, evidence ledger, classification system, provenance
system, confidence model, stage model, or publication gate was redesigned to build this. This
document does not rewrite any of the engine's five prior historical reports.

**This task deliberately implements no overall (cross-pillar) scoring** — with all six individual
pillars now implemented, that is the next task's own scope, not this one's (per Task 17's own
explicit constraint).

## 0. A spec conflict, surfaced and resolved before implementation began

Task 17's own instructions stated that Capital Efficiency "was removed from the public framework"
as a previously approved decision, and instructed: "If the current specification differs, stop and
explicitly report the conflict rather than silently changing the approved methodology."

**It differs.** `NEW_ENGINE_SPEC.md` Part 3.3 still defines Capital Efficiency (weight 0.30) as a
live dimension, and `NEW_ENGINE_CALIBRATION.md` still names specific test companies (Notion, Stripe)
whose calibration rationale explicitly depends on it existing and correctly staying `Unscored`.
Neither document, nor `NEW_ENGINE_ARCHITECTURE.md`, records a removal decision for this engine — the
only "Capital Efficiency removed/merged" history findable anywhere in the repository is in the
legacy `SPS_V3_RULEBOOK.md`/`VENTUREGPS_METHODOLOGY_V2_PROPOSAL.md`, describing the prior V2/V3
methodology this engine's own Task 9 explicitly rejected and rebuilt from scratch.

This conflict was surfaced to the user before any code was written. **The user confirmed the spec as
currently written is authoritative.** This report and the implementation therefore include all three
dimensions exactly as `NEW_ENGINE_SPEC.md` defines them — Capital Efficiency was not quietly
reintroduced (it was never actually absent from the approved spec) and was not quietly omitted
either.

## 1. Implemented dimensions (spec Part 3.3, unmodified)

| Dimension | Weight | Category | Staleness | Admissible evidence (spec) |
|---|---|---|---|---|
| Funding History | 0.45 | Computed | *36 months, not applied as an exclusion — see §3* | Disclosed round(s) — size, date, named investors |
| Revenue Disclosure | 0.25 | Computed (cross-referenced) | 18 months | Identical to Commercial Traction's Disclosed Scale, filtered to specifically-revenue figures |
| Capital Efficiency | 0.30 | Classified | 12 months | A specifically and voluntarily disclosed burn rate, gross margin, or runway figure |

**Two Computed dimensions, one Classified** — matching the spec's own table exactly.

## 2. Computed vs Classified

**Funding History and Revenue Disclosure are pure deterministic functions**, no classification model
call at all — the same precedent Commercial Traction's Disclosed Scale/Growth Trajectory (Task 15)
already established: the typed fact is read directly from `Claim.structured_fact`, and Python owns
the amount → band → score mapping. **Capital Efficiency is Classified**, reusing the exact harness
pattern (and both of the shared `classification.py` factories) every prior pillar's own Classified
dimensions already use.

## 3. Funding History's staleness resolution — the one genuine implementation decision this task
##    required, resolved narrowly and documented

Spec Part 3.3's own staleness cell reads **"36 months (a disclosed 2021 round remains a real,
permanent fact)"** — a stated bound and a stated justification that directly contradict each other
if the 36-month figure is applied as a per-round exclusion (a disclosed 2021 round observed from a
2026 `as_of` date is nearly 60 months old). This is the same class of tension Growth Trajectory
(Commercial Traction, Task 15) and Strategic Consistency (Execution & Momentum, Task 16) each
surfaced — but *unlike* those two, Funding History has **no "current view" component to anchor a
narrower bound to at all**: it is purely cumulative/historical, and every disclosed, completed round
is exactly the "permanent fact" the spec's own parenthetical describes. Per Task 17 item 13's own
explicit instruction ("avoid repeating the prior mistake of applying a staleness threshold to
historical baseline facts required for a legitimate over-time calculation"), this was resolved
**narrowly, and more simply than the two prior fixes**: no staleness exclusion is applied to Funding
History's evidence at all (`FUNDING_HISTORY_RESOLUTION_STALENESS_DAYS`, an effectively-unlimited
sentinel; disputed-exclusion and independence-group dedup still apply). Proven directly by
`test_old_funding_round_is_not_stale_a_disclosed_2021_round_remains_a_real_permanent_fact` and
`test_old_and_recent_rounds_both_count_toward_the_total`.

## 4. How funding is prevented from becoming financial health (item 4 of the completion report)

Structurally, not narratively:

- `Funding History`'s parser recognizes only `structured_fact.kind == "funding_round"`.
  `Capital Efficiency`'s classifier recognizes only `structured_fact.kind ==
  "capital_efficiency_signal"`. Neither has any code path into the other's label or score — a $500M
  round and an 80% gross margin are simply different `kind` values, never conflated.
- **Runway is never computed** by this engine — not from `funding_amount / guessed_burn`, not from
  `funding_date → assumed remaining runway` (item 8's own explicit prohibition). A runway figure is
  admissible for `Capital Efficiency` only as a specifically, voluntarily disclosed statement
  (`structured_fact.metric == "runway"`) — proven directly by
  `test_recent_funding_alone_does_not_establish_runway` and, more pointedly,
  `test_funding_amount_and_disclosed_revenue_together_do_not_compute_a_runway` (even with BOTH a
  funding fact and a revenue fact present, no code path combines them).
- **Unit economics/margins are never inferred** from revenue, customer count, funding, valuation,
  product popularity, company maturity, or "being a software company" —
  `WellBehavedCapitalEfficiencyClassifier` reads only `structured_fact`; none of those signals has any
  route into a label. Proven directly by `test_revenue_with_no_margin_evidence_does_not_score_
  capital_efficiency`, `test_large_funding_round_alone_does_not_score_capital_efficiency`, and
  `test_prestigious_investor_alone_does_not_score_capital_efficiency`.
- Missing financial evidence affects `coverage`/`confidence` only — `Strength` (the shared,
  unmodified `compute_pillar_strength`) is a renormalized average over only the `SCORABLE`
  dimensions, so an Unscored dimension is excluded from the average entirely, never averaged in as a
  low number.

## 5. How missing private financials are handled (item 5)

Every "no qualifying evidence" path returns `score=None` — never zero, never a below-average number,
never an estimate. `test_private_company_undisclosed_financials_are_unscored_not_penalized` proves
this across all three dimensions at once. Capital Efficiency in particular is *expected* to be
`Unscored` for the large majority of real companies assessed from public sources alone — spec Part
3.3's own wording — and this implementation treats that as the honest, correct, structural default,
never something to work around.

## 6. How Commercial Traction revenue evidence is reused (item 6, spec Part 3.1)

**No new extraction, no direct pillar-to-pillar coupling, no shared-layer code.** Revenue Disclosure
reads claims tagged `assessment_criteria` containing `"revenue_disclosure"` — a second, additive tag
placed at claim-authoring time on the SAME claim object Commercial Traction's own Disclosed Scale
already requires when the disclosed figure's `structured_fact.metric == "revenue"`. There is no
Python import or function call from `financial_funding.py` into `commercial_traction.py` anywhere —
`assessment_criteria` (spec Part 2.1's own generic mechanism) is the entire reuse mechanism, and it
already existed before this task.

**The reuse is explicit opt-in, never implicit.** `test_revenue_claim_not_tagged_for_this_dimension_
is_honestly_unscored` proves a claim with an otherwise-identical `structured_fact` but missing the
`"revenue_disclosure"` tag correctly stays Unscored — matching spec Part 2.1's own "a claim with no
mapped criteria... never enters scoring" rule exactly.

**Proven with real data, not just offline fixtures (§8 below):** Stripe's own real 2024/2025 revenue
claims (`stripe-traction-revenue-2024`, `stripe-traction-revenue-2025`, first entered by Commercial
Traction in Task 15) were retroactively given the additional `"revenue_disclosure"` tag — a purely
additive one-line change to each claim's own `assessment_criteria` list, no other field touched. The
real sanity check (§8) confirms Financial & Funding's Revenue Disclosure result cites
`stripe-traction-revenue-2025` — the literal same `claim_id` Commercial Traction's own sanity check
(Task 15) already cited — and confirms Commercial Traction's own full regression suite still
reproduces identically after the tag was added (§9).

## 7. Funding evidence semantics (item 7) — a real interpretive nuance, preserved honestly

Funding History sums the disclosed amount of every distinct, completed, **equity-financed**,
provenance-verified round on record — never just the latest, never a raw claim count.
`provenance.py::verify_independence()` (the same public function `requires_minimum_distinct_facts`
already calls internally) is called directly in this Computed dimension's own deterministic code,
since no classification model is involved to route the check through — proven directly by
`test_duplicated_reports_of_one_round_do_not_inflate_total` and
`test_provenance_verified_dedup_catches_near_identical_restatements_declared_as_different_groups`.

**Debt financing, grants, and tender-offer/secondary transactions are retained in the ledger but
structurally excluded from the sum** (`FUNDING_HISTORY_COUNTED_FINANCING_TYPES = {"equity"}`) — a
narrow, documented reading ("Funding History" in conventional startup/VC usage means equity
fundraising), tested directly by `test_debt_financing_alone_does_not_score_funding_history`,
`test_debt_financing_is_not_summed_alongside_a_real_equity_round`,
`test_grant_financing_does_not_score_funding_history`, and
`test_tender_offer_secondary_transaction_does_not_count_as_new_capital` (mirroring `stage.py`'s own
established treatment of Stripe's real tender offer as a stage signal, never a funding-round fact,
Task 11/12).

**A real, honestly-preserved ambiguity, found during the sanity check (§8.2):** Stripe's 2023
"Series I" round involved new investors and a new priced valuation (the hallmarks of a real primary
equity financing) but its proceeds were explicitly reported as earmarked for employee stock
liquidity rather than operating capital. This implementation treats it as a legitimate completed
equity round (the source-of-funds test, not the stated-use-of-funds test, is what this dimension
applies) — but the purpose nuance is preserved verbatim in the claim's own `limitations` field for
transparency, not smoothed into a cleaner-looking fact than the evidence actually supports.

## 8. Small real-evidence sanity check (item 16)

**Method note, identical to Tasks 11-16: research used this session's own `WebSearch`/`WebFetch`
tools, not the project's paid OpenAI/Tavily infrastructure — no paid API call was made or required.**
Reused Stripe — item 16's own explicit "established private company with strong observable
adoption/funding but incomplete public financial-health metrics." Reproduce with
`python -m app.evidence_engine.live_research.run_financial_funding_sanity_check`.

### 8.1 Result

| Company | Publishable | Strength | Coverage | Funding History | Revenue Disclosure | Capital Efficiency |
|---|---|---|---|---|---|---|
| Stripe | Yes | 8.0 | 70% | 8.0 `LARGE` (3 real rounds, $7.35B total: $250M 2019 + $600M 2020 + $6.5B 2023) | 8.0 `LARGE` ($6.8B 2025 revenue — the SAME claim Commercial Traction cites) | Unscored — genuinely never disclosed |

**Zero traceability violations.** Confirmed programmatically that `stripe-traction-tpv-2025` (the
real $1.9T GMV-like payment-volume claim, Task 15) was never cited by any Financial & Funding
dimension — the same metric-confusion resistance already proven for Commercial Traction now proven
here too, on the same real data.

### 8.2 Checked against item 16's own failure-mode checklist

- **Funding mistaken for financial health:** not found — Capital Efficiency correctly stayed
  Unscored despite $7.35B in real, confirmed funding.
- **Valuation mistaken for revenue:** not found — no valuation-kind claim exists in the ledger for
  Stripe at all in this pass; the mechanism itself is proven by the offline suite (`test_valuation_
  evidence_never_scores_funding_history`, `test_valuation_never_scores_revenue_disclosure`).
- **TPV/GMV mistaken for revenue:** not found — confirmed programmatically above.
- **Unavailable runway becoming a low score:** not found — Capital Efficiency reported honestly
  `Unscored`, not a low number.
- **Unsupported margin/unit-economics assumptions:** not found — no such claim was entered or
  scored.
- **Duplicated financing events:** not found in this real pass (each of the 3 rounds is a distinct,
  separately-dated event) — the dedup mechanism itself is proven by the offline suite (§7).
- **Revenue independently re-extracted instead of referenced:** confirmed NOT the case — see §6's
  real-data proof (the literal same `claim_id` is cited by both pillars).
- **Stale financial data treated as current:** not found — the 2019 round (6+ years old) correctly
  still counts (§3), and no revenue/capital-efficiency claim in this pass was stale.

## 9. Shared-engine changes (item 10)

**Zero new shared-layer factories or fields were needed.** Capital Efficiency reuses
`requires_named_entity_fact` unchanged. Funding History's provenance-verified summing calls
`provenance.py::verify_independence()` directly — an existing public function, not a new one.
Revenue Disclosure's reuse mechanism is `assessment_criteria`, which already existed. **No shared
code was modified at all in this task** — the only files changed outside this pillar's own new files
are `parameters.py` (additive, this pillar's own constants) and `live_research/stripe.py` (additive:
new claims, plus one new `assessment_criteria` tag on two existing claims). All five completed
pillars' full regression suites, and all five prior sanity-check scripts, were re-run after these
changes and reproduce identically (§10 below).

## 10. Test results

**52 new tests, `test_financial_funding.py`, all passing** — covering a completed funding round;
duplicated reports of one round (declared-group dedup and provenance-verified dedup on mismatched
groups, both tested separately per this engine's own established "claim deduplication and source
independence are distinct concepts" discipline); announced vs. completed financing; equity vs. debt
vs. grant vs. secondary/tender-offer (four dedicated exclusion tests); funding vs. valuation; funding
vs. revenue (both directions); ARR/GMV-TPV/bookings vs. revenue (three dedicated confusion tests);
total funding vs. latest-round amount; prestigious investor with no financial-health evidence; a
large round with no runway evidence; recent funding with no burn evidence; funding+revenue together
still not computing a runway; revenue with no margin evidence; explicitly disclosed burn/margin/
runway each scoring on their own; a private company with undisclosed financials; a public-style
company with extensive disclosure (proving Strength independence from coverage, item 10); conflicting
round sizes and conflicting revenue figures (fail closed); stale evidence; the old-round-is-not-stale
regression (§3); canonical Commercial Traction revenue reuse (both the positive and negative case);
invalid evidence references; invalid labels; classification recovery; unsupported classification;
missing/unparseable Computed inputs; non-USD currency exclusion; prompt-injection resistance; both
shared gates (including the coverage-floor-alone edge case spec Part 6.2 itself names Funding
History's own 0.45 weight as the framework's largest single-dimension weight, and gate 2 exists
specifically to still block it); deterministic reproducibility; full traceability; graceful
withholding; stage-tiering in both directions; and the dedicated original-failure-mode regression
(§11 below).

**Full regression: 290 tests across 14 files, all passing** (238 prior + 52 new). Legacy regression
(`test_ai_request_reliability.py` 7/7, `test_analyze_unified_concurrency.py` 2/2) and the isolation
boundary (zero imports outside `app.evidence_engine` anywhere in the package) were both reconfirmed
**after** the live-research additions, not only before. All five prior pillars' own sanity-check
results were re-run and reproduce identically — including Commercial Traction's own, confirming the
new `"revenue_disclosure"` tag added to two of its existing claims caused no change to its own
scoring.

## 11. Original-failure regression result (item 8 of the completion report)

`test_established_private_company_with_incomplete_financials_never_manufactures_a_health_score`
constructs exactly the scenario item 15 describes: an established private company with documented
funding history but no reliable public revenue, burn, or runway. **Result:** Funding History scores
legitimately from two real, distinct equity rounds; Revenue Disclosure and Capital Efficiency are
both honestly `UNSCORED_NO_EVIDENCE`. With only 1 of 3 dimensions scored, the pillar **withholds**
(`publishable=False`, `strength=None`) despite Funding History's own 0.45 weight alone clearing the
40% coverage floor — the minimum-distinct-dimensions gate (spec Part 6.2's own explicit design
intent, naming this exact dimension's weight as the framework's edge case) is what prevents a
"fake 59/100-style financial score" from a single dimension carrying the whole pillar. The system
prefers `WITHHELD`, exactly as item 15 requires.

## 12. Provisional parameters requiring future calibration

Every weight, band cutoff, and label score below is `CALIBRATION REQUIRED`, exactly like every
number in the five prior pillars' own tables — none was set from real data, only reasoned to be
plausible enough to exercise the mechanism: `FINANCIAL_FUNDING_DIMENSION_WEIGHTS` (0.45/0.25/0.30,
taken directly from the spec, not invented), `FUNDING_HISTORY_SMALL_MAX_USD`/`_MODERATE_MAX_USD`
($1M/$20M), `FUNDING_HISTORY_LABEL_SCORES` (stage-tiered, 4-9.5), `REVENUE_DISCLOSURE_SMALL_MAX_USD`/
`_MODERATE_MAX_USD` (same cutoffs, deliberately NOT imported from either Funding History's own or
Commercial Traction's own constants — pillar-local duplication over cross-pillar coupling, the same
discipline this engine has used throughout), `REVENUE_DISCLOSURE_LABEL_SCORES`,
`CAPITAL_EFFICIENCY_LABEL_SCORES` (3.5/6.0/8.5). **One value is genuinely invented, not merely
re-reasoned:** the decision that only `financing_type == "equity"` counts toward Funding History's
summed total (§7) — a documented, narrow reading of "Funding History," not a spec-derived rule.

## 13. Remaining limitations

- **No FX normalization exists** (the same documented limitation Commercial Traction's own Disclosed
  Scale already has) — a non-USD round or revenue figure is retained but not usable.
- **The equity-only summing rule (§7/§12)** means a company financed primarily through debt or grants
  would show a real but potentially misleadingly-low (or entirely `Unscored`) Funding History result
  — a documented, narrow reading, not a defect, but one a future calibration pass may revisit if
  debt-financed companies become a meaningful part of the assessed cohort.
- **The 2023 "Series I" purpose ambiguity (§7)** — treating source-of-funds (new equity, new
  investors) rather than stated-use-of-funds as the test for "is this a funding round" is a
  documented, defensible, but real interpretive choice; a future calibration pass may want an
  explicit `purpose` sub-classification distinguishing operating-capital rounds from liquidity-focused
  ones, which this implementation does not attempt.
- **Funding History's own deliberate absence of any staleness bound (§3)** means a company that
  raised money once, long ago, and never again will show the identical Funding History result as one
  that raised the same amount yesterday — correct per this dimension's own cumulative-fact framing,
  but a real property worth flagging: this dimension alone cannot distinguish "actively fundraising"
  from "hasn't raised in a decade," which is a different, unasked question.
- One real company (Stripe) remains far short of a calibration cohort —
  `NEW_ENGINE_CALIBRATION.md`'s much larger plan (which explicitly names both Notion and Stripe for
  this pillar) is still the real path to final numbers; this pass's own research did not exercise
  Notion's own funding history or seek any real debt-financing example.

## 14. Whether all six individual pillars are ready for combined-engine evaluation (item 13)

Financial & Funding Signals now behaves like the architecture the five prior pillars already proved:
evidence-traceable (zero violations, real and offline), deterministic after classification, resistant
to unsupported claims and cross-pillar/cross-kind leakage (funding, valuation, GMV/TPV, ARR, and
bookings all structurally cannot reach the wrong dimension's score), explicit about uncertainty
(distinct Unscored reasons — no evidence, stale, disputed, uncorroborated, extraction-failed — all
exercised with both offline and real data), and willing to withhold (both individual dimensions and,
when warranted per §11, the full pillar). It additionally demonstrates the engine's cross-pillar
evidence-reuse design (spec Part 3.1) working correctly with real data for the first time — the exact
same claim object serving two pillars' own dimensions, proven, not merely asserted.

**All six individual pillars — Product & Technology, Market Opportunity, Team & Leadership,
Commercial Traction, Execution & Momentum, and Financial & Funding Signals — are now implemented,
individually tested (a combined 290 tests across 14 files), and individually validated against real
evidence.** Each remains independently evaluable and independently withholdable; none has yet been
combined into an overall six-pillar score, overall coverage, or overall confidence — that
cross-pillar aggregation, and the calibration pass both `NEW_ENGINE_CALIBRATION.md` and every prior
pillar's own report have deferred, are the explicit next steps this task does not attempt, per its
own scope constraints.
