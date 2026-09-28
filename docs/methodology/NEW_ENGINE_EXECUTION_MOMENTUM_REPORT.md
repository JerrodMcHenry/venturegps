# VentureGPS Evidence Engine — Execution & Momentum Pillar (Task 16)

**Status: implemented and tested — the fifth pillar in `app/evidence_engine/`, on the exact
architecture Product & Technology (Tasks 8-12), Market Opportunity (Task 13), Team & Leadership
(Task 14), and Commercial Traction (Task 15) already validated.** No shared scoring philosophy,
evidence ledger, classification system, provenance system, confidence model, stage model, or
publication gate was redesigned to build this. This document does not rewrite
`NEW_ENGINE_LIVE_EVALUATION.md`, `NEW_ENGINE_REMEDIATION_REPORT.md`,
`NEW_ENGINE_MARKET_OPPORTUNITY_REPORT.md`, `NEW_ENGINE_TEAM_LEADERSHIP_REPORT.md`, or
`NEW_ENGINE_COMMERCIAL_TRACTION_REPORT.md` — all five of the engine's prior historical reports are
untouched by this task.

## 1. Implemented dimensions (spec Part 3.3, unmodified)

All three dimensions from the approved specification, exactly as weighted — no dimension invented,
renamed, or dropped:

| Dimension | Weight | Category | Staleness | Admissible evidence (spec) |
|---|---|---|---|---|
| Shipping Velocity | 0.35 | Classified | 12 months | Named, dated product releases/launches, ≥2 in a trailing window |
| Go-to-Market Motion Evidence | 0.35 | Classified | 18 months | A named acquisition channel, named partnership, or disclosed sales/GTM hiring |
| Strategic Consistency | 0.30 | Computed (rule-based) | *(spec leaves this cell blank — see §1.3)* | ≥2 dated public statements to compare, mechanically checked for contradiction |

**Two Classified dimensions, one Computed** — matching the spec's own table exactly.

### 1.1 The announced → launched → available distinction, enforced structurally

"Adopted" (the fourth state item 3's own progression names) is deliberately out of scope for this
pillar entirely — that is Commercial Traction's job. Only two states matter here: a release has
**shipped** (`structured_fact.status == "launched"`, covering what a reader would recognize as
"generally available") or it has **not** (`"announced"` or `"beta"` — explicitly partial/incomplete
states that carry no code path to a score at all). `WellBehavedShippingVelocityClassifier` reads
only this field; "coming soon," "plans to," and roadmap language simply produce a claim with
`status != "launched"`, which is structurally invisible to the counting logic. No dimension in this
module ever upgrades one state into another.

### 1.2 Named-release supersession — the one genuinely new mechanism this pillar introduces

The approved spec describes no mechanism for a single named release evolving over time (announced,
then later shipped; or announced, then later delayed/cancelled). This pillar adds one, narrow and
documented: `_resolve_current_release_status()` groups admissible `product_release` claims by
`structured_fact.named_entity` (the release's own identifying name) and takes the **most recent**
(by `published_at`, falling back to `retrieved_at`) claim as authoritative for that release's
**current** status — mirroring `stage.py`'s own "most recent disclosed round wins" precedent,
applied here to a release's status rather than a company's funding stage. A release announced then
later shipped counts once, as launched; a release announced then later delayed or cancelled never
counts as launched at all, regardless of how favorably its earlier "announced" claim might have read.
This is distinct from, and applied *in addition to*, the ledger's own existing `independence_group_id`
dedup (item 4/14 — "a cluster of articles covering the same launch is one underlying event, not
repeated execution"), which already collapses restatements of one announcement before supersession
is even considered. A genuine factual disagreement about the same release (e.g. two sources giving
different launch dates) is a third, different case, handled the ordinary way every other dimension in
this engine handles a conflict — tagged `disputed`/`contradicts`, excluded from `admissible` by the
shared gate before supersession ever runs.

### 1.3 Go-to-Market Motion Evidence's narrow label set, and Strategic Consistency's blank staleness cell

Go-to-Market Motion Evidence's own spec wording asks only for presence of ≥1 named, checkable GTM
fact — no magnitude/count band is described (unlike Shipping Velocity's explicit "release-cadence
band" or Commercial Validation's "presence/count band" wording, Task 15). Per this engine's own "do
not invent an unspecified scoring axis" discipline, this dimension is therefore the narrowest
defensible two-state label set: `NOT_ESTABLISHED` (Unscored) / `GTM_FACT_PRESENT`.

Strategic Consistency's own spec row gives **no staleness-bound value at all** — the table cell is
simply blank, a genuine spec gap, not an oversight in this implementation. Resolved narrowly: 24
months, reasoned analogous to Team & Leadership's Public Track Record (a slow-changing,
biographical-like fact about the company itself) — an invented placeholder, explicitly flagged as
such and listed among this task's provisional parameters (§10).

### 1.4 Only a SALES/GTM-function hire counts — never general headcount (item 8)

`structured_fact.kind == "gtm_evidence"` is the one recognized fact this dimension's classifier
reads; a general headcount-growth or engineering-hire claim (e.g. `structured_fact.kind ==
"headcount_growth"`) carries no such fact and is structurally invisible, regardless of the hire's own
prestige. `test_prestigious_hire_does_not_score_higher_than_an_obscure_one` proves this directly: a
"former Salesforce VP of Sales" hire and an "regional sales manager" hire score identically, because
the score comes only from `structured_fact.gtm_type == "hire"`, never from the hire's own fame.

## 2. Strategic Consistency's own architectural wrinkle

Every other dimension in this engine (and every other pillar) treats `disputed` evidence as something
to **exclude** — spec Part 2.3's own fail-closed default. Strategic Consistency's entire job is the
opposite: detecting whether the company's own disclosed statements conflict *is* the dimension's
actual output, not a reason to discard evidence. This dimension is the one, narrow, documented place
in the whole engine where `disputed` is read as a **positive signal**:

```
if evidence.disputed:      → CONTAINS_CONTRADICTION (a real, scored, low outcome)
elif len(evidence.admissible) >= 2:  → CONSISTENT
elif len(evidence.admissible) == 1:  → Unscored, "insufficient history"
else:                                → Unscored, no evidence
```

**No new shared-layer code was needed for this** — `resolve_dimension_evidence()` already computes
both `evidence.disputed` and `evidence.admissible` as separate fields; this dimension simply reads
both, rather than only the latter the way every other dimension does. Per spec's own wording (only
"insufficient history" is listed as leading to `Unscored`), a detected contradiction is itself
meaningful, checkable evidence — `CONTAINS_CONTRADICTION` gets a real, low score
(`STRATEGIC_CONSISTENCY_LABEL_SCORES["CONTAINS_CONTRADICTION"] = 2.0`), never `None`.

**Zero classification model call for this dimension at all** — it is Computed, pure deterministic
Python over the ledger's own existing fields, exactly matching Commercial Traction's own precedent
for its two Computed dimensions (Task 15 §1.1) and spec Part 6.1's "no AI call" framing taken
literally.

## 3. Stage awareness (item 11) — documented per dimension

| Dimension | Stage behavior | Reasoning |
|---|---|---|
| Shipping Velocity | Stage-tiered (early > growth > established, for the identical release count) | The same release cadence is less expected, and therefore more remarkable, from a younger company — the same reasoning every other magnitude-ish stage-tiered table in this engine already uses. |
| Go-to-Market Motion Evidence | Stage-tiered, same direction | A real GTM motion fact is more remarkable from a younger company. |
| Strategic Consistency | **Flat / stage-independent** | A mechanical contradiction check over the company's own disclosed statements, not a magnitude signal — a genuine contradiction (or its absence) means the same thing regardless of company age, the same reasoning Retention/Renewal Signal (Commercial Traction) and Public Track Record (Team & Leadership) already established for their own quality-not-magnitude dimensions. |

**Stage never manufactures execution** — proven directly by
`test_early_stage_with_zero_execution_evidence_is_not_manufactured_a_score`: a pre-seed company with
zero documented milestones receives the identical Unscored outcome any other stage would. Stage-
tiering only changes which score a band that already cleared its own evidence bar receives.

## 4. How announcements are prevented from becoming completed execution (item 4 of the completion
##    report)

Structurally, not narratively:

- Every "no qualifying launched evidence" path returns `score=None` — there is no code path from
  `status == "announced"` or `status == "beta"` to a score. Proven directly by
  `test_roadmap_promises_only_do_not_score_shipping_velocity`,
  `test_coming_soon_language_does_not_upgrade_to_launched`, and
  `test_beta_status_does_not_count_as_launched`.
- The named-release supersession rule (§1.2) means a company cannot get credit for an early,
  favorable "announced" claim once a later claim reveals the release was delayed or cancelled —
  proven directly by `test_delayed_milestone_never_counts_as_launched` and
  `test_cancelled_milestone_never_counts_as_launched`.
- Funding, general headcount, prestigious investors, and commercial-traction facts all carry
  `structured_fact.kind` values this pillar's parsers do not recognize at all — structurally
  invisible regardless of which dimension's `assessment_criteria` they were mistakenly tagged with
  (§6 below).

## 5. How duplicate events are prevented from inflating momentum (item 5)

Two distinct, complementary mechanisms, tested separately (item 14's own explicit instruction: "claim
deduplication and source independence must remain distinct concepts"):

1. **Declared-group dedup** (the shared, unmodified `resolve_dimension_evidence()`): five claims
   sharing one `independence_group_id` (restatements of one announcement) collapse to one
   representative claim before the classifier ever runs. Proven with real data:
   `test_five_articles_about_one_launch_count_as_one_event` shows 5 restatements of one launch +
   1 genuinely separate second launch correctly banding `STEADY` (2), not `RAPID`.
2. **Provenance-verified distinct-fact validation** (`requires_minimum_distinct_facts`, reused
   unchanged from Team & Leadership/Commercial Traction): the stricter safety net for the case where
   whoever tagged the data assigned *different* group ids to what is actually near-identical restated
   text. Proven directly by
   `test_provenance_verified_dedup_catches_near_identical_restatements_declared_as_different_groups`
   — even with mismatched declared groups, the content-similarity check still catches the duplicate
   and prevents an inflated label.

A separate, genuinely different scenario — three **separately documented** product launches — counts
as three distinct events, proven by `test_three_separate_launches_count_as_three_events`.

## 6. Cross-pillar leakage tests (item 8 of the completion report)

Every boundary the task names has a dedicated test, all passing:

- **Funding never scores execution:** `test_funding_round_evidence_never_scores_shipping_velocity`,
  `test_funding_evidence_never_scores_gtm_motion`.
- **General hiring never scores GTM (only sales/GTM-function hiring does):**
  `test_general_engineering_hiring_does_not_score_gtm_motion` (rejects) vs.
  `test_sales_gtm_hire_does_score_gtm_motion` (accepts) — the same claim shape, different
  `structured_fact.kind`/`gtm_type`, proving the boundary is mechanical, not textual.
- **Prestige hires don't outscore obscure ones:**
  `test_prestigious_hire_does_not_score_higher_than_an_obscure_one` (§1.4).
- **Prestigious investors alone establish nothing:**
  `test_prestigious_investor_alone_does_not_establish_gtm_or_shipping`.
- **Commercial Traction evidence never scores execution:**
  `test_commercial_traction_evidence_never_scores_execution_dimensions` (a `traction_metric` claim
  never counts as a shipped release).
- **A shipped release alone never establishes Commercial Traction:**
  `test_product_launch_alone_does_not_establish_traction` — confirms no Shipping Velocity claim is
  ever tagged with a Commercial Traction `assessment_criteria`, the same mechanical enforcement every
  pillar boundary in this engine relies on.

## 7. Test results

**45 new tests, `test_execution_momentum.py`, all passing** — covering multiple completed milestones;
sparse and zero evidence; roadmap promises/"coming soon" language; announced-vs-launched
(with supersession in both directions); beta-vs-generally-available (including a beta that later
upgrades); multiple articles about one launch vs. separate launches (both directions of item 14's own
dedup requirement); provenance-verified dedup on mismatched declared groups; stale milestones;
conflicting launch dates (fail closed); delayed and cancelled milestones (never count, even after an
earlier favorable claim); first-party release notes vs. independent corroboration; the six cross-
pillar-leakage tests (§6); Strategic Consistency's consistent/contradiction/insufficient-history/no-
evidence four-way split, plus the two staleness-fix regression tests (§9); invalid evidence
references; invalid labels; unsupported classification; classification recovery; prompt-injection
resistance (an injection-*compliant* adversarial mock explicitly telling the classifier to award
"maximum execution scores," still blocked); both shared gates; deterministic reproducibility; full
traceability; graceful withholding under a crashing model; and stage-tiering in both directions
(magnitude dimensions higher earlier, the flat quality dimension unaffected by stage).

**Full regression: 238 tests across 13 files, all passing** (193 prior + 45 new). Legacy regression
(`test_ai_request_reliability.py` 7/7, `test_analyze_unified_concurrency.py` 2/2) and the isolation
boundary (zero imports outside `app.evidence_engine` anywhere in the package) were both reconfirmed
**after** the live-research additions and the Strategic Consistency staleness fix, not only before.
Product & Technology's own Task 11/12 results, Market Opportunity's own Task 13 sanity-check results,
Team & Leadership's own Task 14 sanity-check results, and Commercial Traction's own Task 15
sanity-check results were all re-run and reproduce identically after this pillar's addition — the new
Execution-&-Momentum-tagged claims added to `live_research/stripe.py`/`linear.py` are invisible to all
four other pillars' evaluators, which only ever read claims tagged with their own
`assessment_criteria`.

## 8. Small real-evidence sanity check (item 15)

**Method note, identical to Tasks 11-15: research used this session's own `WebSearch`/`WebFetch`
tools, not the project's paid OpenAI/Tavily infrastructure — no paid API call was made or required.**
Reused Stripe and Linear from Tasks 11-15 (their `live_research/*.py` files extended with a small
number of new, genuinely-researched, real Execution-&-Momentum-tagged claims — see each file's own
"Task 16 addition"). Reproduce with
`python -m app.evidence_engine.live_research.run_execution_momentum_sanity_check`.

### 8.1 Results

| Company | Publishable | Strength | Coverage | Shipping Velocity | GTM Motion | Strategic Consistency |
|---|---|---|---|---|---|---|
| Stripe | Yes | 5.92 | 100% | 5.0 `STEADY` (3 real Sessions 2026 GA launches) | 5.5 `GTM_FACT_PRESENT` (real Google/Gemini distribution partnership) | 7.5 `CONSISTENT` (2021 and 2026 mission statements, 5 years apart) |
| Linear | No (withheld) | — | 35% | 8.0 `RAPID` (5 real changelog entries) | Unscored — not researched this pass | Unscored — not researched this pass |

**Zero traceability violations** across all real scored dimension results (directly verified via
`verify_traceability()` against each company's own claim-ID set).

### 8.2 The announced/launched distinction, demonstrated on real data

Stripe's own "Everything we announced at Sessions 2026" post (2026-04-29) explicitly and cleanly
distinguishes generally-available features (Stripe Workflows, Managed Payments, stablecoin-backed
cards — all entered as `launched`) from several **previewed-only** features from the same event
(Checkout Studio, Stripe Database, Stripe Console, custom objects, Issuing for agents, custom Radar
models). One of these (Checkout Studio) was entered as a claim specifically to test the boundary.
**Confirmed programmatically that the previewed Checkout Studio claim was never cited by any
dimension result.** This is a real, dated instance of exactly the announced/launched risk item 3
warns against, resolved correctly.

### 8.3 A genuine, honest finding: a real GTM job posting correctly does not count

This pass's own GTM research for Linear found only an open job posting (a Developer Relations role
under Marketing) and a general description of Linear's product-led-growth strategy — neither is a
confirmed, named GTM fact. Per item 3's own explicit exclusion ("a job posting" must never become
completed execution), **no `gtm_motion_evidence` claim was added for Linear at all** rather than
stretching the job posting into one. Linear's GTM Motion Evidence stays honestly `Unscored` — not a
code limitation, a correct refusal to manufacture evidence that was never actually found. Combined
with Strategic Consistency also being unresearched this pass, Linear's pillar correctly **withholds**
overall (only 1 of 3 dimensions scored, below the 2-dimension floor) despite a genuinely excellent,
real `RAPID` Shipping Velocity result — directly demonstrating that legitimate high shipping activity
alone does not manufacture pillar publication.

### 8.4 A second genuine, honest finding: Stripe's real mission has been stable for 5+ years, and
###    the engine initially failed to see that

Stripe's real mission statement ("increase the GDP of the internet," Patrick Collison, March 2021)
and its 2026 Sessions framing ("economic infrastructure for AI commerce") are ~5 years apart. Under
the initially-implemented, straightforward per-claim 24-month staleness bound, the 2021 statement
aged out entirely, leaving Strategic Consistency with only one usable statement and reporting
"insufficient history" — technically correct given that bound, but a real loss of exactly the kind of
information this dimension exists to use (a genuinely long-standing, consistent mission is arguably
the *strongest* possible Strategic Consistency signal, not evidence that should disappear). **Fixed**
(§9) by applying the same "only the newest point needs to be current" principle Growth Trajectory
(Commercial Traction, Task 15) already established, for an analogous but independently-reasoned cause
(this dimension's spec cell gives no staleness value at all, so there was no spec text to contradict
— the fix here is a design inference from the dimension's own stated purpose, not a spec-fidelity
correction). **Not tuned to produce a specific number for Stripe** — the fix is a general, documented
principle applied identically regardless of which company's data happened to surface it, verified by
two new regression tests that assert the mechanism's behavior in both directions (old-but-usable vs.
genuinely-all-stale), not a specific company's outcome.

### 8.5 Checked against item 15's own failure-mode checklist

- **Announcements mistaken for completed milestones:** not found — see §8.2.
- **Duplicated reporting inflating momentum:** not found in this real pass (Linear's changelog
  entries are each a distinct, separately-dated entry, and Stripe's three GA features are distinct
  named products from one event) — the dedup mechanism itself is proven by the offline suite (§5).
- **Funding leaking into execution:** not found — no funding-round claim was tagged for any
  Execution dimension in this real pass; the mechanism itself is proven by the offline suite (§6).
- **Hiring leaking into execution:** not found — no headcount/hiring claim was researched or entered
  for either company's GTM Motion Evidence in this pass; the mechanism itself is proven by the
  offline suite (§6).
- **Traction leaking into execution:** not found — Commercial Traction's own claims (Task 15) for
  Stripe/Linear remain invisible to this pillar's evaluators, confirmed by both pillars' full
  regression suites passing identically after this task's additions.
- **Stale historical activity making an inactive company look active:** not directly exercised by
  real data in this pass (both companies' real release evidence is genuinely recent) — the mechanism
  itself is proven by the offline suite's stale-release test (§7).
- **Legitimate recent shipping activity being recognized:** confirmed — Linear's real `RAPID` result
  (5 genuine changelog entries within the trailing 12-month window) is exactly this, correctly scored
  even though the pillar as a whole withholds for an unrelated reason (§8.3).

## 9. Shared-engine changes (item 9)

**Zero new shared-layer factories or fields were needed** — this pillar's two Classified dimensions
reuse `requires_named_entity_fact` and `requires_minimum_distinct_facts` unchanged (both already
existed before this task).

**One genuine, pillar-local defect was found and fixed via the real-evidence sanity check** (§8.4),
analogous in shape to Commercial Traction's own Growth Trajectory fix (Task 15 §4) but independently
motivated: Strategic Consistency's initial implementation applied its 24-month staleness bound to
*every* individual statement, which defeats a dimension whose entire purpose is comparing statements
"over time" — a genuinely old-but-real statement is exactly what the check needs, not evidence to
discard. **Fixed** by resolving evidence with no staleness ceiling at the raw-resolution layer
(`STRATEGIC_CONSISTENCY_RESOLUTION_STALENESS_DAYS`, disputed-exclusion and independence-group dedup
still apply) and applying the real 24-month bound explicitly, only to whichever statement is the most
recent on record (`execution_momentum.py::evaluate_strategic_consistency`). This is a **pillar-local
fix** — it does not touch `ledger.py`, `scoring.py`, `classification.py`, or any other pillar's
staleness handling; Product & Technology, Market Opportunity, Team & Leadership, and Commercial
Traction's own staleness semantics are untouched and unaffected, confirmed by their full regression
suites reproducing identically (§7). Two dedicated regression tests were added:
`test_strategic_consistency_uses_an_old_statement_as_long_as_the_newest_is_current` and
`test_strategic_consistency_is_stale_when_the_newest_statement_itself_is_old`.

## 10. Provisional parameters requiring future calibration

Every weight, count threshold, and label score below is `CALIBRATION REQUIRED`, exactly like every
number in the four prior pillars' own tables — none was set from real data, only reasoned to be
plausible enough to exercise the mechanism:

`EXECUTION_MOMENTUM_DIMENSION_WEIGHTS` (0.35/0.35/0.30), `SHIPPING_VELOCITY_STEADY_MIN_COUNT`/
`_RAPID_MIN_COUNT` (2/4, reused convention from Commercial Validation's own 1/3), `SHIPPING_
VELOCITY_LABEL_SCORES` (stage-tiered, 5-9), `GTM_MOTION_LABEL_SCORES` (stage-tiered, 5.5-7.5),
`STRATEGIC_CONSISTENCY_LABEL_SCORES` (`CONTAINS_CONTRADICTION` 2.0, `CONSISTENT` 7.5). **Two values
are genuinely invented, not merely re-reasoned placeholders, and are flagged more strongly than the
rest:** Strategic Consistency's own 24-month staleness bound (spec's own table cell is blank, §1.3),
and the entire `announced`/`beta`/`launched` three-state vocabulary itself (the spec names a richer
`announced → launched → available → adopted` progression in prose, item 3, but gives no closed label
set for Shipping Velocity's own evidence column) — both are documented, narrow, defensible readings,
not spec-derived values.

## 11. Remaining limitations

- The `announced`/`beta`/`launched` vocabulary is a three-state simplification of item 3's own
  richer four-state progression (adoption is out of scope by design, §1.1, but "available" and
  "launched" are treated as one state here) — a documented, narrow reading, not a gap the real
  sanity check exposed as insufficient in practice, but one a future calibration pass may revisit.
- Go-to-Market Motion Evidence's binary presence/absence label set (§1.3) cannot distinguish "one
  named GTM fact" from "many" the way Commercial Validation's own count-band can — a deliberate,
  narrow reading of the spec's own minimal wording for this specific dimension, not an oversight.
- The named-release supersession rule (§1.2) requires `structured_fact.named_entity` to be
  consistently spelled across claims describing the same release over time (e.g. "Feature A" must be
  named identically in an early "announced" claim and a later "launched" claim) — a real, documented
  trust boundary on whoever authors the claims, the same kind of trust boundary this engine already
  has for `assessment_criteria` tagging discipline.
- Two real companies (Stripe, Linear) remains far short of a calibration cohort —
  `NEW_ENGINE_CALIBRATION.md`'s much larger plan is still the real path to final numbers, and this
  pass's own research did not specifically seek GTM or Strategic Consistency evidence for Linear, or
  find a genuine real contradiction in either company's own public statements (§8.5).

## 12. Readiness for the eventual full-engine evaluation

Execution & Momentum now behaves like the architecture the four prior pillars already proved:
evidence-traceable (zero violations, real and offline), deterministic after classification, resistant
to unsupported claims and cross-pillar leakage (funding, hiring, prestige, and traction all
structurally cannot reach an execution score), explicit about uncertainty (distinct Unscored reasons
— no evidence, stale, disputed, uncorroborated, extraction-failed — all exercised with both offline
and real data), and willing to withhold (both individual dimensions and, when warranted, the full
pillar — Linear's real `RAPID` shipping result correctly did not manufacture a published pillar
alone). It additionally introduces and proves a genuinely new mechanism — named-release supersession
— that no prior pillar needed but that a time-and-sequence-sensitive pillar structurally requires, and
the one real methodological bug this pass surfaced (Strategic Consistency's own staleness handling)
was found, fixed, and regression-tested before this report was written, following the exact same
"found via real evidence, fixed narrowly, regression-tested" pattern Commercial Traction's own Growth
Trajectory fix established (Task 15). **Ready to join Product & Technology, Market Opportunity, Team
& Leadership, and Commercial Traction in a future combined evaluation once the final pillar exists to
make "full-engine" meaningful** — this task deliberately implements no overall (cross-pillar) scoring
and no additional pillar (Financial & Funding Signals remains unbuilt), per its own explicit scope
constraints.
