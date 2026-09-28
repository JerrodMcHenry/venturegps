# VentureGPS Evidence Engine — Implementation State

Methodology: `docs/methodology/NEW_ENGINE_SPEC.md`. Architecture: `docs/architecture/
NEW_ENGINE_ARCHITECTURE.md`. Calibration plan: `docs/methodology/NEW_ENGINE_CALIBRATION.md`.
Calibration report (Task 9 + Task 10): `docs/methodology/NEW_ENGINE_CALIBRATION_REPORT.md`.
Live evaluation (Task 11, real companies, unchanged): `docs/methodology/
NEW_ENGINE_LIVE_EVALUATION.md`. Remediation of that evaluation's findings (Task 12):
`docs/methodology/NEW_ENGINE_REMEDIATION_REPORT.md`. Market Opportunity pillar (Task 13):
`docs/methodology/NEW_ENGINE_MARKET_OPPORTUNITY_REPORT.md`. Team & Leadership pillar (Task 14):
`docs/methodology/NEW_ENGINE_TEAM_LEADERSHIP_REPORT.md`. Commercial Traction pillar (Task 15):
`docs/methodology/NEW_ENGINE_COMMERCIAL_TRACTION_REPORT.md`. Execution & Momentum pillar (Task 16):
`docs/methodology/NEW_ENGINE_EXECUTION_MOMENTUM_REPORT.md`. Financial & Funding Signals pillar
(Task 17, the sixth and final individual pillar):
`docs/methodology/NEW_ENGINE_FINANCIAL_FUNDING_REPORT.md`.

**This package is isolated by design** (architecture doc Part 1) — it imports nothing from
`app.ai`, `app.database`, `app.api`, `app.models`, or `app.v2`. Confirmed with:
`grep -rn "^from app\.\|^import app\." app/evidence_engine/ | grep -v app.evidence_engine`
(zero matches as of this writing — re-run this before any future change to confirm the
boundary still holds).

## What is implemented (Tasks 8-17: all six individual pillars, calibration, reliability, live evaluation, remediation)

- **`models.py`** — the `Claim` model, including `structured_fact` (Task 9) and
  `SourceType.COMMUNITY_COMMENTARY` (Task 12 — an anonymous public comment, independent of the
  company but distinct from attributable reporting), with write-time rejection of missing
  excerpts / blank publishers.
- **`ledger.py`** — `EvidenceLedger` and `resolve_dimension_evidence()`: staleness, disputed-claim
  exclusion, declared-group deduplication.
- **`provenance.py`** — `assess_independence()`/`verify_independence()`: claim identity decided
  purely by content (Jaccard token overlap), never by shared source URL (Task 12).
- **`scoring.py`** — `DimensionResult`/`PillarResult`, the firewall-respecting Strength/Coverage/
  Confidence functions, the two-gate `evaluate_pillar()`, `verify_traceability()` — shared by both
  pillars unchanged.
- **`confidence.py`** — support-status mix, source-reliability weighting, provenance-*verified*
  corroboration counting.
- **`stage.py`** — `Stage`/`StageTier`, `determine_stage()` (round-type > founding-age >
  Undetermined, routed through the same admissibility check every dimension uses since Task 12),
  `tier_for_stage()`.
- **`classification.py`** — the schema-constrained AI interface: request/response types, the
  `ClassificationModel`/`ExtractionModel` Protocols, `validate_classification()`/
  `validate_extraction()`, `redact_company_identity()`, `classify_with_recovery()`/
  `extract_with_recovery()`. **Task 13** added one additive field, `EvidenceItem.structured_fact`
  (propagated from `Claim.structured_fact`) — Product & Technology's own dimensions never read it
  and are unaffected; Market Opportunity's magnitude-bearing dimensions need it. See the Market
  Opportunity report §4 for the full justification. **Task 14** added a second additive factory,
  `requires_named_entity_fact(qualifying_labels)` — a specificity/checkability requirement distinct
  from `requires_independent_source`, needed because Team & Leadership's own evidence bar (self-
  disclosed bios are admissible; vague unsupported claims are not) is not about source
  independence. Product & Technology and Market Opportunity use neither the field nor the factory
  and are unaffected. See the Team & Leadership report §5. **Task 15 added no new shared factory or
  field** — Commercial Traction's three Classified dimensions reuse `requires_named_entity_fact` and
  `requires_minimum_distinct_facts` unchanged. **Task 16 likewise added no new shared factory or
  field** — Execution & Momentum's two Classified dimensions reuse the same two factories unchanged.
  **Task 17 also added no new shared factory or field** — Capital Efficiency reuses `requires_
  named_entity_fact` unchanged, and Funding History calls the already-public
  `provenance.py::verify_independence()` directly (not a new function) to provenance-verify its own
  summed total.
- **`parameters.py`** — every numeric constant, versioned `evidence_engine.v1-provisional-9`, all
  explicitly `CALIBRATION REQUIRED`.
- **`pillars/product_technology.py`** — the first pillar (Task 8-12): Product Existence & Maturity
  (Computed) plus three Classified dimensions, stage-aware (label scores vary by stage tier), all
  routed through the classification/extraction interface with recovery.
- **`pillars/market_opportunity.py`** (Task 13) — the second pillar: four Classified dimensions
  (Market Definition & Size, Market Growth Signal, Timing & Catalyst, Competitive Landscape
  Position), deliberately **stage-independent** (documented reasoning in the module's own
  docstring — this pillar measures the market, not the company). Every scoring label requires
  independent evidence; a company's own TAM slide or growth claim never scores alone.
- **`pillars/team_leadership.py`** (Task 14) — the third pillar: three Classified dimensions
  (Founder Relevant Experience, Leadership Composition, Public Track Record). Self-disclosed
  biographies are admissible (unlike Market Opportunity); every scoring label instead requires a
  named, checkable fact. Introduces fail-closed identity resolution (a `team_identity` pseudo-
  dimension + `structured_fact.person_id`) so two different people sharing a name are never
  combined. Leadership Composition is the pillar's one stage-tiered dimension, with
  `NONE_BEYOND_FOUNDERS` deliberately pinned flat across every tier. No dimension scores founder
  intelligence, charisma, prestige, or any subjective judgment — see the Team & Leadership report
  §4 for the structural (not just narrative) mechanism.
- **`pillars/commercial_traction.py`** (Task 15) — the fourth pillar: two Computed dimensions
  (Disclosed Scale, Growth Trajectory — pure deterministic functions over `structured_fact`, no
  model call) plus three Classified (Customer Base Breadth, Commercial Validation, Retention/
  Renewal Signal). No dimension requires independent sourcing; every scoring label instead requires
  a named, checkable fact or a provenance-verified minimum distinct-fact count. `TRACTION_METRIC_
  PREFERENCE_ORDER` resolves multi-metric ambiguity (revenue/ARR before GMV/bookings) without ever
  picking the larger raw number. Growth Trajectory's own staleness handling required a genuine,
  pillar-local fix during the real-evidence sanity check (spec's "newer point ≤18mo" applies to the
  newer point only, not both) — see the Commercial Traction report §4. The central, non-negotiable
  rule: unknown private metrics are Unscored, never a weak score.
- **`pillars/execution_momentum.py`** (Task 16) — the fifth pillar: two Classified dimensions
  (Shipping Velocity, Go-to-Market Motion Evidence) plus one Computed (Strategic Consistency, a pure
  rule-based contradiction check with no model call — the one dimension where `disputed` evidence is
  read as a positive signal rather than an exclusion reason). Introduces named-release supersession
  (a single release's most-recent claim wins for its current status, so an early "announced" claim
  can never outlive a later launch, delay, or cancellation) — a genuinely new mechanism no prior
  pillar needed. No dimension scores from funding, general headcount, investor prestige, or
  commercial-traction magnitude. Strategic Consistency's own staleness handling required a
  pillar-local fix during the real-evidence sanity check, analogous to Commercial Traction's own
  Growth Trajectory fix — see the Execution & Momentum report §9.
- **`pillars/financial_funding.py`** (Task 17) — the sixth and final individual pillar: two Computed
  dimensions (Funding History, Revenue Disclosure — pure deterministic functions, no model call)
  plus one Classified (Capital Efficiency). A spec conflict (Task 17's own instructions referenced a
  "previously approved" Capital Efficiency removal not recorded in `NEW_ENGINE_SPEC.md` or
  `NEW_ENGINE_CALIBRATION.md`) was surfaced to and resolved by the user before implementation — the
  spec as written (all three dimensions) is authoritative; see the Financial & Funding report §0.
  Funding History sums every distinct, completed, EQUITY-financed round (debt/grants/tender-offers
  excluded), provenance-verified via a direct call to the already-public `verify_independence()`, with
  deliberately NO staleness exclusion at all (a disclosed round is a permanent historical fact, per
  spec's own wording — the same class of staleness-scoping fix Commercial Traction's Growth
  Trajectory and Execution & Momentum's Strategic Consistency each needed, resolved here even more
  simply since this dimension has no "current view" component at all). Revenue Disclosure never
  re-extracts a figure — it reads the exact same claim Commercial Traction's Disclosed Scale already
  requires, tagged with one additional `assessment_criteria` entry, proven with real Stripe data to
  cite the literal same `claim_id` across both pillars. Funding is never financial health: no code
  path connects a funding/valuation fact to a Capital Efficiency label, and runway is never computed
  from funding amount or date.
- **`fixtures/`** — Notion, Linear (real companies), Auroraflow, Pathlight, DupliCo (fictional,
  each built to stress a specific mechanism; offline, hand-authored) — Product & Technology only.
- **`live_research/`** — genuine, real, dated evidence for Notion, Linear, Stripe, Fish Audio, and
  Bullet (Task 11), gathered via live web research, never a synthetic stand-in.
  `run_evaluation.py` reproduces the Task 11/12 Product & Technology results unchanged.
  `run_market_opportunity_sanity_check.py` (Task 13) runs a small, additional, genuinely-researched
  Market Opportunity pass against Notion and Linear, kept as its own script specifically so it
  never touches `run_evaluation.py`'s own reproducibility. `run_team_leadership_sanity_check.py`
  (Task 14) likewise runs a small, additional, genuinely-researched Team & Leadership pass against
  Stripe and Linear (`stripe.py`/`linear.py` each gained a "Task 14 addition" block), kept as its
  own script for the same reason. `run_commercial_traction_sanity_check.py` (Task 15) does the same
  for Commercial Traction against Stripe and Notion (each file gained a "Task 15 addition" block) —
  Stripe's real revenue/payment-volume/named-customer data was chosen specifically as an established,
  privately-held company with meaningful observable adoption but incomplete public disclosure.
  `run_execution_momentum_sanity_check.py` (Task 16) does the same for Execution & Momentum against
  Stripe and Linear (each file gained a "Task 16 addition" block) — Stripe's own Sessions 2026 recap
  provided a real, clean, dated announced-vs-generally-available distinction; Linear's public
  changelog provided a real, dense `RAPID` shipping-velocity result.
  `run_financial_funding_sanity_check.py` (Task 17) does the same for Financial & Funding Signals
  against Stripe (`stripe.py` gained a "Task 17 addition" block of three real, dated equity rounds
  totaling $7.35B, plus a `"revenue_disclosure"` tag added to two of its own existing Task 15 revenue
  claims — the real proof that Revenue Disclosure reuses, not re-extracts, Commercial Traction's own
  evidence).
- **`tests/`** — **290 tests across 14 files**, all script-style (this repo's pytest is scoped to
  `app/v2` only). Run any file: `python -m app.evidence_engine.tests.<name>`.
- **`demo.py`** — prints a human-readable Product & Technology pillar summary for all five offline
  fixtures: `python -m app.evidence_engine.demo`.

## What remains design-only (not implemented)

**All six individual pillars are now implemented.** What remains: overall (cross-pillar) six-pillar
scoring, overall coverage, and overall confidence (no orchestrator combines pillars yet — this is
the explicit next step every pillar task since Task 13 has deferred, per each one's own scope
constraints); a real AI-driven Research pass (Assessment's mock models stand in for it); the
scale-based stage-determination fallback (`stage.py`'s own docstring has flagged this as blocked on
Commercial Traction's Disclosed Scale since Task 9 — technically buildable since Task 15, but
deliberately not built as part of any task since; see the Commercial Traction report §9);
persistence; API contracts; frontend integration; and observability beyond `print()`. Retry applies
only to validation failures, not to a raised exception. A final, real calibration pass against a
much larger cohort (`NEW_ENGINE_CALIBRATION.md`'s own plan) has also not been attempted — every
numeric parameter across all six pillars remains an explicitly-flagged placeholder.

**Six open methodological questions flagged, not resolved:** whether `_OBSERVABLE_SOURCE_TYPES`
(Product & Technology) should ever include `COMMUNITY_COMMENTARY` (`NEW_ENGINE_REMEDIATION_REPORT.md`
§2.1); whether Competitive Landscape Position's `FRAGMENTED`/`CONCENTRATED` binary needs a third
state for "many named competitors, one explicitly dominant" markets (`NEW_ENGINE_MARKET_
OPPORTUNITY_REPORT.md` §9); whether Founder Relevant Experience's `NONE_DISCLOSED` label should be
split into a genuine-absence state and a disclosed-but-irrelevant state (`NEW_ENGINE_TEAM_
LEADERSHIP_REPORT.md` §9); whether Customer Base Breadth's 18-month staleness bound is appropriate
for a slow-changing directional metric (a total-user-count milestone) versus a fast-changing one
(`NEW_ENGINE_COMMERCIAL_TRACTION_REPORT.md` §7.4/§9); whether Shipping Velocity's three-state
`announced`/`beta`/`launched` vocabulary should be split further to match item 3's own richer
four-state progression (`NEW_ENGINE_EXECUTION_MOMENTUM_REPORT.md` §11); and whether Funding History's
equity-only summing rule should be extended to debt-financed companies, and whether the 2023-style
"real equity round, liquidity-focused proceeds" ambiguity deserves its own explicit sub-classification
(`NEW_ENGINE_FINANCIAL_FUNDING_REPORT.md` §13).

## Decisions locked in (see the design docs' own "Decided" boxes)

Package name `app/evidence_engine/`, methodology identifier `evidence_engine.v1`, a fully
decoupled lightweight company reference (`company_ref: str`, no V2 Company integration), and
categorical (`Low`/`Medium`/`High`) Confidence.
