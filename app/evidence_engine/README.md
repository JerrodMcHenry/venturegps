# VentureGPS Evidence Engine — Implementation State

Methodology: `docs/methodology/NEW_ENGINE_SPEC.md`. Architecture: `docs/architecture/
NEW_ENGINE_ARCHITECTURE.md`. Calibration plan: `docs/methodology/NEW_ENGINE_CALIBRATION.md`.
Calibration report (Task 9 + Task 10): `docs/methodology/NEW_ENGINE_CALIBRATION_REPORT.md`.
Live evaluation (Task 11, real companies, unchanged): `docs/methodology/
NEW_ENGINE_LIVE_EVALUATION.md`. Remediation of that evaluation's findings (Task 12):
`docs/methodology/NEW_ENGINE_REMEDIATION_REPORT.md`. Market Opportunity pillar (Task 13):
`docs/methodology/NEW_ENGINE_MARKET_OPPORTUNITY_REPORT.md`. Team & Leadership pillar (Task 14):
`docs/methodology/NEW_ENGINE_TEAM_LEADERSHIP_REPORT.md`. Commercial Traction pillar (Task 15):
`docs/methodology/NEW_ENGINE_COMMERCIAL_TRACTION_REPORT.md`.

**This package is isolated by design** (architecture doc Part 1) — it imports nothing from
`app.ai`, `app.database`, `app.api`, `app.models`, or `app.v2`. Confirmed with:
`grep -rn "^from app\.\|^import app\." app/evidence_engine/ | grep -v app.evidence_engine`
(zero matches as of this writing — re-run this before any future change to confirm the
boundary still holds).

## What is implemented (Tasks 8-15: four pillars, calibration, reliability, live evaluation, remediation)

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
  `requires_minimum_distinct_facts` unchanged.
- **`parameters.py`** — every numeric constant, versioned `evidence_engine.v1-provisional-7`, all
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
- **`tests/`** — **193 tests across 12 files**, all script-style (this repo's pytest is scoped to
  `app/v2` only). Run any file: `python -m app.evidence_engine.tests.<name>`.
- **`demo.py`** — prints a human-readable Product & Technology pillar summary for all five offline
  fixtures: `python -m app.evidence_engine.demo`.

## What remains design-only (not implemented)

The other two pillars (Execution & Momentum, Financial & Funding Signals), a real AI-driven Research
pass (Assessment's mock models stand in for it), overall (cross-pillar) publication gates (not yet
meaningful — no orchestrator combines pillars yet), the scale-based stage-determination fallback
(`stage.py`'s own docstring has flagged this as blocked on Commercial Traction's Disclosed Scale
since Task 9 — now *technically* buildable since Task 15, but deliberately not built as part of this
task; see the Commercial Traction report §9), persistence, API contracts, frontend integration, and
observability beyond `print()`. Retry applies only to validation failures, not to a raised exception.
**Four open methodological questions flagged, not resolved:** whether `_OBSERVABLE_SOURCE_TYPES`
(Product & Technology) should ever include `COMMUNITY_COMMENTARY` (`NEW_ENGINE_REMEDIATION_REPORT.md`
§2.1); whether Competitive Landscape Position's `FRAGMENTED`/`CONCENTRATED` binary needs a third
state for "many named competitors, one explicitly dominant" markets (`NEW_ENGINE_MARKET_
OPPORTUNITY_REPORT.md` §9); whether Founder Relevant Experience's `NONE_DISCLOSED` label should be
split into a genuine-absence state and a disclosed-but-irrelevant state (`NEW_ENGINE_TEAM_
LEADERSHIP_REPORT.md` §9); and whether Customer Base Breadth's 18-month staleness bound is
appropriate for a slow-changing directional metric (a total-user-count milestone) versus a
fast-changing one (`NEW_ENGINE_COMMERCIAL_TRACTION_REPORT.md` §7.4/§9).

## Decisions locked in (see the design docs' own "Decided" boxes)

Package name `app/evidence_engine/`, methodology identifier `evidence_engine.v1`, a fully
decoupled lightweight company reference (`company_ref: str`, no V2 Company integration), and
categorical (`Low`/`Medium`/`High`) Confidence.
