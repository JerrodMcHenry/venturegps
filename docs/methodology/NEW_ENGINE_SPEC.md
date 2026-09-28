# VentureGPS Evidence Engine — Methodology Specification

**Status: TASK 10 (Evidence Reliability & Validation) COMPLETE for Product & Technology.**
Building on Task 9's calibration pass (classification/extraction interface, stage-aware
evaluation, source-reliability-weighted Confidence): Task 10 added provenance-verified
evidence-independence checking (`app/evidence_engine/provenance.py` — corroboration counting no
longer trusts a claim's self-declared `independence_group_id` at face value) and
retry-with-validation-feedback classification recovery (`classification.py::
classify_with_recovery`/`extract_with_recovery`). See `docs/methodology/
NEW_ENGINE_CALIBRATION_REPORT.md` Part 10 for findings, including an explicit rationale review
of the stage-tiered label-to-score tables (6.4/4.2) that changed no values. 77 tests across 7
files. Everything else in this document (the other five pillars, a real Research pass,
persistence, API, frontend) remains design only — see `app/evidence_engine/README.md`.

> **Decided (approved), superseding the "open question" framing used elsewhere in this
> document and in the companion architecture document:**
> - **Naming:** package `app/evidence_engine/`, methodology identifier `evidence_engine.v1`.
> - **Company identity (spec Part 7, architecture Part 1.3/3.3):** the lightweight,
>   fully-decoupled company reference (no dependency on V2's canonical Company resolution).
>   Revisit only in a later, separately-scoped integration phase, if ever.
> - **Confidence's output shape (Part 6.4):** categorical `Low`/`Medium`/`High`, not continuous.
>
> Not yet decided, and not needed for the first vertical slice: whether the engine's result
> ever appears alongside the legacy/V3 result on the same page, and whether near-always-
> `Unscored` dimensions in pillars not yet built (Retention/Renewal Signal, Capital Efficiency)
> should be kept or dropped — both remain open per the companion architecture document until a
> phase that actually reaches those pillars.

**Working name:** this document calls the new system the **VentureGPS Evidence Engine**
(package: `app/evidence_engine/`; methodology identifier: `evidence_engine.v1`) specifically to
avoid colliding with the two existing, already-taken internal names — the legacy pillar
methodology's `"v2.1-spec-2026-08-29"` and the separate, already-built `sps_v3` engine
(`app/ai/sps_v3_engine/`). This is a genuinely new, independent methodology, not a third
revision of either.

**This is a clean-slate design, per explicit instruction.** It does not repair, extend, or
inherit the scoring methodology of either existing engine (six fixed pillars scored by asking
an LLM to pick a 0-10 number, in the legacy case; the three-axis-but-incompletely-adapted
design in the V3 case). Both were inspected — their failure modes and, separately, some of
their sound *infrastructure patterns* inform this design (noted explicitly wherever reused,
Part 8) — but no pillar definition, dimension, weight, threshold, or scoring formula from
either is carried over. Every number in this document is either a structural rule (zero
degrees of freedom, stated as such) or explicitly marked **CALIBRATION REQUIRED** — this
document does not invent a plausible-sounding weight or threshold anywhere.

---

## Part 1 — Design Principles (restated as enforceable rules)

These are the constitution of the engine. Every rule below is intended to be checkable
against the actual implementation later, not aspirational prose:

1. **Evidence precedes assessment. Assessment precedes scoring.** No code path may compute a
   score from anything other than an already-recorded Evidence Ledger entry (Part 2) that has
   already passed through Assessment (Part 5.1). There is no "direct to score" path anywhere
   in the pipeline, for any dimension.
2. **Every material scored claim is traceable to admissible evidence.** "Traceable" means a
   human reviewer can, from the persisted record alone, find the exact ledger entry, its
   source, and its excerpt that a given dimension score rests on — not a paraphrase, not "the
   AI concluded this from context."
3. **Missing information is not evidence of poor performance.** A dimension with no admissible
   evidence is `Unscored`, never defaulted to a low, medium, or average score.
4. **A score is withheld when there is insufficient evidence.** This applies at the dimension,
   pillar, and overall level, each with its own explicit, independently-checkable gate (Part
   6).
5. **Performance, evidence coverage, and confidence are separate measurements.** Computed as
   three structurally independent passes over the same underlying data — changing how much
   evidence exists or how reliable it is must never, by construction, change what the evidence
   says (the "firewall" property, Part 6.6).
6. **Deterministic code owns all aggregation, weighting, scoreability, and publication
   decisions.** No LLM call in this engine ever outputs a final numeric dimension score,
   pillar score, or overall score. Every number the product shows is computed by versioned,
   reviewable Python from AI-produced *classifications*, never chosen by the AI directly. This
   is the single largest structural departure from both prior engines (Part 8.1) and is
   treated as non-negotiable.
7. **AI may research, extract, classify, and assess evidence within explicit schemas, but
   cannot override deterministic rules.** Every AI call in this engine has a closed output
   schema (a fixed enum, a bounded set of labels, a typed fact with required provenance
   fields) — never a free-form number, and never a schema field whose value is "the score."
8. **Company stage affects the criteria used for assessment**, never a weight multiplier or an
   additive bonus (Part 4).
9. **The engine must produce useful intelligence even when no numerical score can be
   published.** A withheld score is never a blank page — the product always shows whatever
   pillar- and dimension-level information *is* responsibly available, honestly labeled (Part
   6.5).
10. **Identity-blindness.** The engine is designed to recognize documented achievements
    consistently regardless of which company they belong to, not to make specific companies
    score well. Concretely: extraction and classification prompts are never given the
    company's name as a signal to weigh (it is used only for retrieval/search, not passed into
    the schema-constrained classification calls as context that could bias a label choice),
    and the calibration plan (companion document) includes an explicit blind-rerun test for
    this (redact the company name, confirm identical classifications).

---

## Part 2 — The Evidence Ledger

The Evidence Ledger is the single foundation everything else reads from. Nothing in
Assessment or Scoring (Parts 5-6) ever reads raw research text directly — only ledger
entries.

### 2.1 Ledger entry (a "Claim") — required and optional fields

| Field | Required? | Description |
|---|---|---|
| `claim_id` | Required | Stable identifier (content hash of the normalized claim text + source URL, so re-running research against an unchanged source produces the same id, not a new duplicate row) |
| `company_ref` | Required | Which company this claim is about (Part 7.3 — a lightweight reference, not V2's canonical Company identity) |
| `claim_text` | Required | A normalized, single-fact statement (one checkable assertion per claim — a source paragraph making three claims is split into three ledger entries, never stored as one compound claim, so each can be independently supported/disputed/aged) |
| `subject_entity` | Required | What the claim is actually about — the company itself, a named competitor, the market/category, a named person (a founder, an investor) — kept distinct from `company_ref` because a claim can be *about* a competitor while still being *relevant to* the subject company's Market Opportunity assessment |
| `source.url` | Optional | Present when the source is web-locatable; absent for a company-provided document with no public URL (e.g., an uploaded pitch deck) |
| `source.publisher` | Required | Named publisher/domain/document source — "the company's own site," "TechCrunch," "the submitted pitch deck," never blank |
| `source.type` | Required | One of: `company_disclosure`, `independent_reporting`, `public_filing`, `product_documentation`, `aggregator_or_directory` (funding databases, review-aggregator sites — treated as a distinct, weaker tier from primary independent reporting, since aggregators often just restate a company's own press release), `other` |
| `published_at` | Optional | The source's own publication/last-update date, when determinable |
| `retrieved_at` | Required | When this engine's research step actually fetched/observed this source — always present, never inferred |
| `support_status` | Required | One of `directly_supported` (the excerpt states the claim in terms a reader would recognize as the same fact), `inferred` (the claim is a reasonable but not literal reading of the excerpt — e.g., inferring "the company is expanding internationally" from a job posting for a role based outside its home country), `disputed` (a materially conflicting claim exists elsewhere in the ledger for the same fact and has not been resolved — see 2.3) |
| `excerpt` | Required when `support_status` is `directly_supported` or `inferred`; absent for `disputed` entries pending resolution | The verbatim source text the claim rests on — never paraphrased, never omitted for a scorable claim |
| `assessment_criteria` | Required | Which dimension(s) (Part 3) this claim is admissible evidence for — a claim with no mapped criteria is retained for transparency but never enters scoring |
| `independence_group_id` | Required | Claims that trace back to the same underlying event (e.g., five outlets restating one funding-round press release) share a group id, so corroboration counting (Part 6.4) counts independent *events*, not independent *restatements* |
| `contradicts` | Optional | Other `claim_id`s this claim conflicts with, populated when `support_status = disputed` |
| `limitations` | Optional | Free-text, structured notes a human or the classification step attaches — "single source," "over 18 months old," "company-disclosed, uncorroborated" — surfaced to the report, never silently dropped |
| `ledger_version` | Required | The schema version this entry was written under, for forward migration safety |

### 2.2 Missing sources

A claim with no locatable `source.url` is not automatically excluded — a company-provided pitch
deck or an offline document is a legitimate `source.type: company_disclosure` with no URL. What
*is* required unconditionally is `source.publisher` and `retrieved_at`; a claim missing either
is malformed and is rejected at ledger-write time (never persisted half-formed).

### 2.3 Duplicate and conflicting claims

- **Duplicates** (the same fact restated by multiple sources, same `independence_group_id`):
  retained in full in the ledger for transparency, but only the earliest-retrieved entry in a
  group counts toward a dimension's evidence for coverage purposes; the others contribute only
  to the corroboration count (Part 6.4) — this prevents one funding announcement, restated by
  ten aggregator sites, from ever looking like ten independent pieces of evidence.
- **Conflicting claims** (two sources disagree on the same fact — e.g., two different disclosed
  revenue figures for the same period): both entries are marked `support_status: disputed` and
  linked via `contradicts`. A deterministic resolution rule attempts to break the tie using two
  ordered signals, in this order: (a) **source-type precedence** — a `public_filing` or the
  company's own `company_disclosure` outranks an `aggregator_or_directory` restatement; (b)
  **recency** — a more recently published figure for a metric that is expected to change over
  time (revenue, headcount) outranks an older one for the *same reporting period label*, but
  never across different reporting periods (a 2024 figure does not "resolve" a 2023 one — they
  are different facts, not a conflict). If neither signal breaks the tie, the conflict remains
  `unresolved` and **both entries stay excluded from scoring** — this is a fail-closed default,
  never a coin-flip pick.
- **Unsupported company-provided statements:** a `company_disclosure` claim with no independent
  corroboration is not rejected outright (a company's own pitch deck is real evidence of what
  the company claims, and self-disclosed facts — a named customer, a specific dated metric —
  are frequently the *only* record of true facts a private company will ever put in writing).
  It is retained, scorable where the assessment framework's own rubric (Part 3) allows
  uncorroborated company disclosure as admissible for that specific dimension, and always
  tagged with a `limitations` note ("company-disclosed, uncorroborated") that the Confidence
  computation (Part 6.5) reads. Some dimensions (Part 3) explicitly require independent
  corroboration and cannot be scored from company disclosure alone — this is a rubric-level
  decision made per dimension, not a blanket rule.

### 2.4 Staleness

Every dimension in Part 3 declares its own maximum admissible evidence age (a fast-moving fact
like headcount or an active fundraising round needs fresher evidence than a slow-moving one like
a founder's prior company). A claim older than its dimension's threshold, measured from
`published_at` when known or `retrieved_at` otherwise, is retained in the ledger but excluded
from scoring, tagged `limitations: "stale"`, surfaced in the report rather than silently
dropped.

### 2.5 The URL-is-not-verification rule

`source.url` establishes only *locatability* — a human reviewer can go look. It never, by
itself, establishes `support_status: directly_supported` (an inaccurate blog post has a URL
too) and never substitutes for `source.type` or corroboration. The report's presentation layer
(architecture document) must show these as visibly separate facts — a link icon next to a claim
never implies "verified," only "sourced."

---

## Part 3 — The Assessment Framework

### 3.1 Evaluating the candidate framework

The six candidate pillars (Market Opportunity, Product & Technology, Team & Leadership,
Commercial Traction, Execution & Momentum, Financial & Funding Signals) are adopted as the
top-level structure — they cover the right territory and avoid the legacy framework's
worst structural defect (Traction and Financial Health each concentrating most of their weight
in dimensions that are realistically private, Part 8.2). Two redesign decisions were made
against the candidate framework, both to prevent double-counting the same underlying evidence
across two pillars:

- **Customer-demand-for-the-category evidence moves out of Market Opportunity and into
  Commercial Traction.** The candidate framework's implicit inclusion of "customer demand" in
  Market Opportunity would otherwise double-count the same paying-customer evidence Commercial
  Traction's own dimensions already use — Market Opportunity is redefined to measure the
  *category*, not this specific company's pull within it.
- **Revenue-scale evidence is extracted once** (inside Commercial Traction's `Disclosed Scale`
  dimension) and *referenced*, not re-extracted, by Financial & Funding Signals' `Revenue
  Disclosure` dimension when the disclosed figure is specifically revenue — the two pillars
  answer different questions ("is the company growing" vs. "what capital/revenue facts are
  publicly known") about the same underlying fact, and the ledger's `assessment_criteria` field
  (2.1) is exactly the mechanism that lets one claim serve two dimensions without being
  extracted, and therefore weighted, twice.

Team & Leadership's candidate scope is narrowed relative to the legacy framework: dimensions
that reduce to an unverifiable narrative judgment about the team's presumed operating skill
("business capability," "leadership quality") are dropped, since public evidence realistically
supports only *named, checkable facts* (a prior company, a prior exit, a named executive hire)
— judgment about how *good* that makes the team is exactly the kind of free-form scoring this
engine is designed to eliminate. What that removed scope covers is now visible, where it is
genuinely observable, in Execution & Momentum's evidence-based dimensions instead (shipped
product, named GTM motion) rather than as a narrative team-quality score.

### 3.2 Category system — every dimension is one of exactly two kinds

There is no third "AI picks a qualitative label that isn't backed by a fixed table" category
in this engine, unlike the prior V3 design's bounded "Category C." Every dimension is:

- **Computed** — a pure deterministic function of one or more *structured, typed facts*
  (a dated dollar figure, a dated count, a disclosed date) already present in the ledger. The
  AI's only role is extracting/normalizing the fact into a typed field with its own provenance
  (Part 5.1); the function that turns the fact into a score is versioned Python, reviewable
  without any company name in it.
- **Classified** — the AI maps one or more ledger claims to exactly one label from a fixed,
  closed, versioned enum per a written rubric (e.g., `founder_relevant_experience: NONE_DISCLOSED
  | ADJACENT | DIRECT`), and a separate, versioned Python lookup table maps that label to a
  score. The AI never sees or chooses the number — it is structurally impossible for a
  Classified dimension's AI call to emit anything but one label from the fixed set (schema
  enforcement), and the label-to-score table lives in code, not in the prompt.

### 3.3 Pillars and dimensions

Weights below are **CALIBRATION REQUIRED placeholders**, shown only so pillar/dimension
relative proportions are legible while reading this document — see Part 6.7 for exactly which
numbers require calibration before this engine can be considered final.

#### Market Opportunity (pillar weight: CALIBRATION REQUIRED, shown as 0.20)

**Implemented (Task 13)** — `app/evidence_engine/pillars/market_opportunity.py`. All four
dimensions below are Classified, stage-independent (documented reasoning in that module's own
docstring), and every scoring label requires independent evidence per the "Minimum to score"
column already below. See `docs/methodology/NEW_ENGINE_MARKET_OPPORTUNITY_REPORT.md` for closed
label definitions, test results, and a small real-evidence sanity check.

| Dimension | Weight (placeholder) | Category | Admissible evidence | Minimum to score | Staleness bound |
|---|---|---|---|---|---|
| Market Definition & Size | 0.30 | Classified | Named customer segment + independently published market-size/report figures for that category | ≥1 independently-published market-size claim for a comparable category | 24 months |
| Market Growth Signal | 0.25 | Classified | Independently published category growth-rate reporting | ≥1 independent-reporting claim | 18 months |
| Timing & Catalyst | 0.20 | Classified | A named, dated external catalyst (regulatory change, platform shift) cited to independent reporting | ≥1 independent-reporting claim naming a specific catalyst, not a generic "AI is growing" statement | 24 months |
| Competitive Landscape Position | 0.25 | Classified | Named competitors + an independently-sourced comparison (review site, analyst comparison, press) | ≥1 named competitor with an independent (not self-authored) comparison point | 18 months |

#### Product & Technology (0.18)

| Dimension | Weight | Category | Admissible evidence | Minimum to score | Staleness bound |
|---|---|---|---|---|---|
| Product Existence & Maturity | 0.25 | Computed | A directly observable product artifact (live URL, app-store listing, public demo, product documentation) | ≥1 directly-observed artifact, dated by `retrieved_at` | 12 months (re-verify the product still exists) |
| Differentiation Claim Corroboration | 0.25 | Classified | An independent comparison (review site, press, analyst) that agrees or disagrees with the company's own differentiation claim | ≥1 independent-source comparison; a company's own claim alone scores `Unscored` for this dimension, not a low score | 18 months |
| Technical Depth Signal | 0.25 | Classified | Named integrations, disclosed patents/technical documentation, named technical infrastructure partners | ≥1 named, checkable technical fact | 24 months |
| Defensibility Signal | 0.25 | Classified | Named structural moat evidence corroborated independently (a network-effect claim backed by independently reported usage scale; a switching-cost claim backed by a named long-term customer relationship) | ≥1 independently-corroborated moat claim; an uncorroborated self-description of "strong moat" is retained in the ledger but does not score this dimension | 24 months |

#### Team & Leadership (0.18)

**Implemented (Task 14)** — `app/evidence_engine/pillars/team_leadership.py`. All three dimensions
below are Classified; Founder Relevant Experience and Public Track Record are stage-independent
(fixed biographical facts), while Leadership Composition is stage-tiered (documented reasoning in
that module's own docstring — `NONE_BEYOND_FOUNDERS` is pinned flat across every tier and is never
itself a penalty). Self-disclosed biographies are admissible per this table's own wording; every
scoring label instead requires a named, checkable entity (`requires_named_entity_fact`,
`classification.py`) rather than independent sourcing. See
`docs/methodology/NEW_ENGINE_TEAM_LEADERSHIP_REPORT.md` for closed label definitions, the
fail-closed identity-resolution mechanism, test results, and a small real-evidence sanity check.

| Dimension | Weight | Category | Admissible evidence | Minimum to score | Staleness bound |
|---|---|---|---|---|---|
| Founder Relevant Experience | 0.40 | Classified (`NONE_DISCLOSED` \| `ADJACENT` \| `DIRECT`) | Named prior company/role/customer segment, from a bio, press profile, or public professional-history record | ≥1 named, checkable prior role or company | 36 months (biographical facts age slowly) |
| Leadership Composition | 0.30 | Classified (count band) | Named executives/leadership hires from public bios/announcements | ≥1 named leadership hire beyond the founder(s), or explicit confirmation the founder(s) are the only leadership (a real, scorable `NONE_BEYOND_FOUNDERS` state, distinct from `Unscored`) | 12 months |
| Public Track Record | 0.30 | Classified (`NONE_DISCLOSED` \| `PRIOR_VENTURE_ROLE` \| `PRIOR_EXIT`) | A disclosed, named prior venture-backed role or a disclosed, named prior exit | ≥1 named, checkable prior company | 36 months |

#### Commercial Traction (0.20)

**Implemented (Task 15)** — `app/evidence_engine/pillars/commercial_traction.py`. Two Computed
dimensions (Disclosed Scale, Growth Trajectory — pure deterministic functions over an already-typed
`structured_fact`, no model call at all) and three Classified. Growth Trajectory's own staleness
column below ("newer point ≤18 months old") is applied literally — only the newer of a qualifying
pair must be current; the older baseline point carries no separate staleness bound of its own, a
distinction a real-evidence sanity check surfaced was initially implemented incorrectly and then
fixed (see the Commercial Traction report §4). Disclosed Scale, Customer Base Breadth, and
Commercial Validation are stage-tiered (the same magnitude/count is more remarkable earlier);
Growth Trajectory and Retention/Renewal Signal are deliberately flat/stage-independent (documented,
narrow ambiguity resolutions in that module's own docstring). No dimension requires independent
sourcing — company disclosures are admissible per this table's own wording — but every scoring
label requires a named, checkable fact (`requires_named_entity_fact`) or a provenance-verified
minimum distinct-fact count (`requires_minimum_distinct_facts`), both reused unchanged from Team &
Leadership. See `docs/methodology/NEW_ENGINE_COMMERCIAL_TRACTION_REPORT.md` for closed label
definitions, the metric-preference tie-break mechanism, test results, and a small real-evidence
sanity check that includes a real ~280x GMV-vs-revenue magnitude gap resolved correctly.

| Dimension | Weight | Category | Admissible evidence | Minimum to score | Staleness bound |
|---|---|---|---|---|---|
| Disclosed Scale | 0.25 | Computed | One dated, disclosed absolute figure (revenue, GMV, ARR, active users, paying customers) | Exactly one admissible dated figure — unlike Growth Trajectory below, this dimension deliberately needs no second point | 18 months |
| Growth Trajectory | 0.25 | Computed | Two dated, disclosed figures for the *same* metric, both confirmed actuals (never one actual paired with a projection/guidance figure) | Two qualifying dated points, spanning ≥2 quarters (a shorter window is not annualized — CALIBRATION REQUIRED for the exact minimum-window value; 2 quarters stated here as a structural floor carried over as a sound general principle, not a specific reused threshold) | Newer point ≤18 months old |
| Customer Base Breadth | 0.20 | Classified (named count band + segment mix) | Named customer count/band, named segment mix (enterprise vs. SMB, consumer) from press, case studies, the company's own site | ≥1 named, checkable customer-count fact | 18 months |
| Commercial Validation | 0.15 | Classified (presence/count band) | Named contracts, renewals, or enterprise-partnership announcements | ≥1 named, checkable commercial-commitment fact | 24 months |
| Retention/Renewal Signal | 0.15 | Classified | A specifically disclosed retention/renewal/churn figure from an independent source or a company disclosure explicitly presented as a real measured figure (not a marketing adjective) | ≥1 explicitly disclosed figure; **never inferred from funding, headcount, or general market presence** | 12 months |

#### Execution & Momentum (0.14)

**Implemented (Task 16)** — `app/evidence_engine/pillars/execution_momentum.py`. Two Classified
dimensions plus one Computed (Strategic Consistency — a pure, rule-based mechanical contradiction
check over the company's own disclosed statements, no model call). Shipping Velocity introduces a
new, narrow mechanism this engine did not previously need: named-release supersession — a single
release described by multiple dated claims over time (announced, then later launched, delayed, or
cancelled) resolves to its most-recent status, never letting an early favorable "announced" claim
outlive a later correction. Strategic Consistency's own staleness bound (this table's own cell,
below, is intentionally left blank by the spec) is a documented, invented placeholder (24 months),
applied only to the most recent statement on record — an old-but-real statement is exactly what a
"compared... over time" check needs, never discarded for its own age. Shipping Velocity and
Go-to-Market Motion Evidence are stage-tiered; Strategic Consistency is flat/stage-independent
(a mechanical quality check, not a magnitude signal). No dimension scores from funding, general
headcount, investor prestige, or commercial-traction magnitude. See
`docs/methodology/NEW_ENGINE_EXECUTION_MOMENTUM_REPORT.md` for closed label definitions, the
supersession mechanism, test results, and a small real-evidence sanity check.

| Dimension | Weight | Category | Admissible evidence | Minimum to score | Staleness bound |
|---|---|---|---|---|---|
| Shipping Velocity | 0.35 | Classified (release-cadence band) | Named product releases/launches from a changelog, press, or the product's own release notes, over a trailing window | ≥2 named, dated releases in the trailing window (one shipped feature is Product Existence, Part above; a *cadence* needs at least two dated points, mirroring Growth Trajectory's own two-point discipline) | 12 months |
| Go-to-Market Motion Evidence | 0.35 | Classified | Named acquisition channel, named partnership, or disclosed sales/GTM hiring | ≥1 named, checkable GTM fact | 18 months |
| Strategic Consistency | 0.30 | Computed (rule-based, not a judgment of strategic quality) | The company's own disclosed public statements (mission, target market, roadmap) compared against its other disclosed facts over time | ≥2 dated public statements to compare; scored as `CONSISTENT` \| `CONTAINS_CONTRADICTION` \| insufficient history for `Unscored` — this is a mechanical contradiction check, never a subjective "is this a good strategy" judgment |

#### Financial & Funding Signals (0.10)

**Implemented (Task 17)** — `app/evidence_engine/pillars/financial_funding.py`, all three
dimensions below exactly as this table defines them (Capital Efficiency's own removal, referenced in
Task 17's initial instructions, is not recorded in this document or in `NEW_ENGINE_CALIBRATION.md`;
the conflict was surfaced to and resolved by the user before implementation — see the Financial &
Funding report §0). Funding History and Revenue Disclosure are Computed, pure deterministic
functions with no model call, matching Commercial Traction's own precedent (Task 15). Funding
History's own staleness cell below is **not** applied as a per-round exclusion — its own parenthetical
("a disclosed 2021 round remains a real, permanent fact") is taken literally; every disclosed,
completed, equity round counts toward a summed total regardless of age, provenance-verified against
double-counting via `provenance.py::verify_independence()` called directly. Revenue Disclosure never
re-extracts a figure — it reads the exact same claim Commercial Traction's own Disclosed Scale
already requires, tagged with an additional `assessment_criteria` entry at claim-authoring time (spec
Part 3.1's own reuse mechanism), proven with real Stripe data to cite the literal same `claim_id`
across both pillars. See `docs/methodology/NEW_ENGINE_FINANCIAL_FUNDING_REPORT.md` for closed label
definitions, the equity-only funding-summation rule, test results, and a small real-evidence sanity
check.

| Dimension | Weight | Category | Admissible evidence | Minimum to score | Staleness bound |
|---|---|---|---|---|---|
| Funding History | 0.45 | Computed | Disclosed round(s) — size, date, named investors — from company disclosure, independent reporting, or a funding-database aggregator | ≥1 disclosed round with a size and date | 36 months (a disclosed 2021 round remains a real, permanent fact) |
| Revenue Disclosure | 0.25 | Computed (cross-referenced, not re-extracted — see 3.1) | Identical to Commercial Traction's `Disclosed Scale`, filtered to specifically-revenue figures | Same claim already required for Commercial Traction; this dimension adds no new extraction requirement | 18 months |
| Capital Efficiency | 0.30 | Classified | A specifically and voluntarily disclosed burn rate, gross margin, or runway figure | ≥1 explicitly disclosed figure. **This dimension is `Unscored` for the large majority of companies assessed from public sources alone, by design, and this is the expected, honest, structural outcome — never inferred from funding amount, headcount, or general market presence, per explicit instruction.** | 12 months |

### 3.4 Pillar-level minimum-to-publish requirements

Stated precisely in Part 6.2 (deterministic scoring); referenced here because it is part of the
assessment framework's own contract: **no pillar publishes a Strength score from a single
scored dimension alone**, regardless of that dimension's own weight, unless it is the only
dimension the pillar has (no pillar in Part 3.3 has fewer than three dimensions, so this
condition cannot occur under the current dimension set — flagged so a future dimension-count
change doesn't silently reintroduce the single-dimension failure mode).

---

## Part 4 — Stage-Aware Evaluation

**Implemented for Product & Technology (Task 9)** — `app/evidence_engine/stage.py`. Scoped
honestly: only the round-type and founding-age signals below are implemented; the scale-based
fallback this Part originally described needs Commercial Traction's Disclosed Scale, which does
not exist yet (see `NEW_ENGINE_CALIBRATION_REPORT.md` Part 9). This pillar's own stage-indexed
scoring (4.2) uses a coarser 3-tier grouping (early/growth/established) than the 6-state Stage
below — see `stage.py::StageTier` — since Product & Technology's dimensions did not need finer
granularity; other pillars, if built, may use the 6-state Stage directly.

### 4.1 How stage is established — from evidence, deterministically, never guessed

Stage is not asked of an LLM as a free-text field and keyword-matched (the prior engines' own
approach, and a confirmed source of a silent-default failure mode). Instead, stage is
**computed from already-extracted, typed ledger facts**, in a fixed priority order, each with
its own admissibility bar:

1. **Most-recent disclosed funding round type** (from the `Funding History` dimension's own
   extracted facts — a disclosed "Series B" round is unambiguous) — highest priority, since a
   round label is the most direct, least-inferential stage signal available.
2. **Absent a disclosed round type: disclosed revenue/user scale** (from `Disclosed Scale`)
   mapped to a stage band via a versioned table (**CALIBRATION REQUIRED** for the exact
   cutoffs) — used only as a fallback, since scale-based stage inference is inherently coarser
   than a company's own disclosed round label.
3. **Absent both: company age since founding** (from a disclosed founding date, if any) mapped
   to the most permissive plausible stage band for that age — the weakest signal, used last,
   and only to avoid defaulting to "Undetermined" when *any* real signal exists.
4. **Absent all three: `Stage: Undetermined`.** This is a first-class, explicit, reportable
   state — never silently defaulted to Seed or any other single stage.

### 4.2 How stage affects assessment

Exactly as Design Principle 8 states: stage changes **which label maps to which score** in a
Classified dimension's lookup table (Part 3.2), never a pillar weight and never an additive
bonus. Concretely, each Classified dimension's label-to-score table (Part 3.3) is itself
stage-indexed — e.g., `Founder Relevant Experience: DIRECT` maps to a higher score at Pre-Seed
(where it is one of the only signals a company this young can possibly have) than the identical
label at Growth stage (where the same fact, with no additional corroborating traction/hiring
evidence, is an unremarkable baseline for a company that old). The exact per-stage table values
are **CALIBRATION REQUIRED** (Part 6.7); the *mechanism* — a stage-indexed lookup table, not a
prompt instruction the AI may or may not apply consistently — is the structural design decision
made here.

### 4.3 Handling `Stage: Undetermined`

Every stage-indexed dimension is evaluated against the **most permissive applicable band across
all six stages** when stage is `Undetermined` — never the average of the six bands (which would
be an invented number) and never a specific guessed stage. This guarantees a company whose stage
cannot be determined is never penalized for failing to clear a bar appropriate to a stage it may
not actually be at, at the cost of also never being credited with a bar tightened for a later
stage it may actually be at — an explicit, stated tradeoff, not an oversight. `Stage:
Undetermined` is always visibly disclosed in the report, never presented as if a stage had been
confidently determined.

### 4.4 No arbitrary stage bonuses

There is no code path anywhere in this design that adds or multiplies a score based on stage.
Every stage effect is expressed as "this label, at this stage, maps to this score" in a lookup
table that a reviewer can read without reference to any specific company — satisfying, by
construction, the instruction not to introduce predetermined scores or arbitrary bonuses.

---

## Part 5 — AI's Role: Evidence, Extraction, and Classification Only

**Implemented for Product & Technology (Task 9)** — `app/evidence_engine/classification.py`
(the interface, `validate_classification`/`validate_extraction`, `redact_company_identity`) and
the `WellBehaved*` default mock models in `app/evidence_engine/pillars/product_technology.py`.
**Task 10 added** `classify_with_recovery()`/`extract_with_recovery()`: on a validation
failure, the model is retried exactly once with the violations fed back as structured
`validation_feedback`; a still-invalid second attempt fails closed to `Unscored` — never a
substituted score, never a relaxed check on the retry (`test_classification_recovery.py`).
No paid AI call has been made; every test uses either a well-behaved mock or a deliberately
adversarial one (`app/evidence_engine/tests/test_adversarial_robustness.py`) conforming to the
same `ClassificationModel`/`ExtractionModel` Protocol a real model call will eventually satisfy.

### 5.1 What every AI call in this engine may output

Every AI call in this engine has exactly one of two possible output shapes, both schema-enforced
(structured output / function-calling style, validated against a Pydantic model, matching this
codebase's own existing, proven pattern for structured LLM outputs):

- **A typed fact** (for a Computed dimension) — e.g., `{metric: "ARR", value: 4_200_000,
  currency: "USD", as_of_date: "2025-11-01", source_claim_id: "..."}` — with the source
  `claim_id` mandatory, so a Computed dimension's numeric input is always traceable to a ledger
  entry, never a bare number floating free of provenance.
- **A label from a fixed enum** (for a Classified dimension) — e.g.,
  `founder_relevant_experience: "DIRECT"`, with a mandatory `supporting_claim_ids: [...]` list.

**No AI call output schema in this engine contains a numeric score field, a 0-10 field, a
0-100 field, a confidence-as-a-number field, or any free-text field that downstream code
parses for a number.** This is checked structurally (a schema review, not a prompt-wording
review) precisely because prompt-level instructions not to fabricate a number were exactly
what both prior engines relied on and both prior engines' own audits found unreliable.

### 5.2 What AI may not do

An AI call may not: choose which label "feels right" outside the fixed enum (schema rejects
anything else); see the company's name inside the classification prompt itself (5.3);
determine whether a dimension is scoreable (that is Part 6.2, deterministic); decide a pillar's
or the overall score's publishability (Part 6.3, deterministic); or resolve a conflicting-claims
tie (Part 2.3, deterministic).

### 5.3 Identity-blindness in practice

The research/retrieval step legitimately uses the company's name (you cannot search for a
company without naming it). The **classification** step — the call that maps ledger claims to
a Classified dimension's label — receives only the relevant claim text and excerpts, with the
company's own name and any obviously identifying brand terms stripped/replaced with a neutral
placeholder before the call. This is checkable in calibration (companion document) via a
blind-rerun test: the same evidence, same claims, run twice — once naturally, once through a
name-redaction pass — must produce identical labels.

---

## Part 6 — Deterministic Scoring

All of this part is pure Python: no network call, no AI call, no randomness. Every function is
a pure function of its inputs, versioned, and reviewable without any company name appearing in
the code.

### 6.1 Dimension scoring

- **Computed dimension:** `score = f(typed_fact)`, where `f` is a versioned, stage-indexed
  lookup/formula (e.g., Growth Trajectory: `f(point_a, point_b, window) -> CAGR -> scale-tiered
  band -> score`). Absent a qualifying typed fact (Part 3.3's own minimum-to-score bar), the
  dimension is `Unscored` — never a partial/estimated value from a single point where two are
  required.
- **Classified dimension:** `score = TABLE[stage][label]`, a plain dictionary lookup. A label
  outside the fixed enum cannot occur (schema-enforced at the AI call boundary, 5.1), so this
  lookup can never fail to find an entry for a valid label.
- Every dimension score also carries its own **evidence-support quality**, computed
  deterministically from the ledger entries backing it (their `support_status` mix, whether any
  are `disputed`-and-unresolved, corroboration count) — this quality measure feeds Confidence
  (6.5), never the score itself.

### 6.2 Pillar aggregation and the single-dimension-carries-the-pillar prevention rule

A pillar's **Strength** is the renormalized weighted average of its own scorable (non-`Unscored`)
dimensions — the same general renormalization shape both prior engines used, adopted here
because it is mathematically sound on its own (unavailable dimensions excluded, never
defaulted) and is not itself the defect (Part 8.2 traces the actual defect to the *absence* of
a gate on top of this renormalization, not to renormalization itself).

**Two independent gates, both required, prevent one scored dimension from ever representing an
entire pillar:**

1. **Weighted-coverage floor:** the pillar's scorable dimensions must carry at least
   `MIN_PILLAR_COVERAGE_PCT` (**CALIBRATION REQUIRED**) of the pillar's total configured weight.
2. **Minimum-distinct-dimensions floor:** the pillar must have at least
   `MIN_SCORED_DIMENSIONS_PER_PILLAR` (**CALIBRATION REQUIRED**, provisionally reasoned as ≥2 for
   every pillar in Part 3.3, since every pillar has ≥3 dimensions and no single dimension in this
   design exceeds ~45% of its pillar's weight — see Financial & Funding Signals' Funding History
   at 0.45, the single largest dimension-weight anywhere in this framework) scored, independent
   of gate 1.

**Both gates must pass for a pillar to publish a numeric Strength.** Gate 2 exists specifically
because gate 1 alone is insufficient in principle: a pillar with one dimension weighted above
the coverage floor would pass gate 1 alone while still being "one dimension carrying the whole
pillar" — exactly the failure this task explicitly requires be prevented. This is a deliberate
design choice against the most recent version of the prior V3 engine, which had removed its own
equivalent second gate in favor of coverage alone; this audit's review of that removal (companion
architecture document, Part 8.2) found the coverage-alone design leaves exactly this edge case
open whenever one dimension's weight alone clears the floor, and reinstates the second gate here
for that reason, stated explicitly rather than silently.

When either gate fails, the pillar's Strength is withheld (`None`, never a number), with a
disclosed `withhold_reason` naming which gate failed and by how much.

### 6.3 Evidence coverage

`pillar_coverage_pct = (sum of weights of scorable dimensions) / (sum of weights of in-scope
dimensions) × 100`. **In-scope** excludes any dimension that is stage-inapplicable by
construction (e.g., Growth Trajectory for a company with only one disclosed data point is not
"stage-inapplicable," it is simply unscorable this run — true stage-inapplicability is rare in
this framework's dimension set and is called out explicitly if a future dimension needs it,
rather than assumed). Overall coverage is the `PILLAR_WEIGHTS`-weighted sum of each pillar's own
coverage, computed identically at every level (matching the one part of both prior engines'
coverage math this audit found already sound and worth keeping as a pattern).

### 6.4 Confidence

**Implemented for Product & Technology (Task 9)** — `app/evidence_engine/confidence.py`. A
dimension's Confidence is a function of three inputs, each computed without reference to Score
(firewall property, 6.6): (a) the `support_status` mix of the cited claims (weighted toward
`directly_supported` over `inferred`), (b) the corroboration count (Part 2.3's
`independence_group_id` — how many independent events, not restatements, back the dimension),
and (c) **source reliability** — a weighted average over each cited claim's `source_type`
(independent reporting/public filings weighted above product documentation, above aggregator/
directory restatements, above company disclosure), added explicitly in the Task 9 calibration
pass. Pillar-level Confidence remains the weighted-ordinal average of its scored dimensions'
own Confidence, unchanged. The categorical (Low/Medium/High, decided per Part 0's box) output
shape is fixed; the exact reliability weights and the HIGH/MEDIUM thresholds remain
**CALIBRATION REQUIRED** — see `docs/methodology/NEW_ENGINE_CALIBRATION_REPORT.md` Part 5 for
what the first real test against five fixtures found (no dimension across any fixture reached
HIGH, a finding flagged as ambiguous, not resolved).

### 6.5 Minimum scoreability and overall-score publication

**Status (Task 19):** company-level Coverage and Confidence are implemented
(`app/evidence_engine/full_analysis.py`); **an overall 0-100 Strength ("Startup Power") is
deliberately NOT implemented** — Task 19 evaluated this part's own original proposal directly against
real evidence and concluded the pillar weights it would require are still too provisional to justify
the added precision (full reasoning: `docs/methodology/NEW_ENGINE_CALIBRATION_RESULTS.md` §8). This is
an explicit, evidence-backed decision, not a placeholder for a number nobody has gotten to yet — a
future task may revisit it once a larger calibration pass validates `PILLAR_WEIGHTS` (Part 3.3's own
header rows) against real comparative judgment.

**What Task 19 actually built, using this part's own two-gate shape (adapted for the absence of a
Strength number):**

```
company_coverage_pct = Σ (PILLAR_WEIGHTS[pillar] × pillar.coverage_pct)   -- always computed
company_confidence   = weighted-ordinal average of PUBLISHED pillars' own Confidence -- None if zero published
company_publishable  = company_coverage_pct >= MIN_OVERALL_COVERAGE_PCT (40.0)
                        AND published_pillar_count >= MIN_PUBLISHABLE_PILLARS (2)
```

A withheld pillar's own partial `coverage_pct` still contributes to `company_coverage_pct` (Coverage
answers "how much was assessable," and a withheld pillar still contains that information) but is
excluded from `company_confidence` (a withheld pillar's own default-Low placeholder would conflate
"no evidence" with "unreliable evidence," two different concepts) and counts against, never toward,
`MIN_PUBLISHABLE_PILLARS`. `MIN_OVERALL_COVERAGE_PCT`/`MIN_PUBLISHABLE_PILLARS` are both
**CALIBRATION REQUIRED** like every other number in this document, currently set equal to the
pillar-level `MIN_PILLAR_COVERAGE_PCT`/`MIN_SCORED_DIMENSIONS_PER_PILLAR` values for structural
consistency, justified by the sensitivity analysis in the calibration results document §4/§9-10, not
by intuition.

**The original three-gate proposal below is retained for historical/design reference** — it describes
what a future Overall Strength, if and when adopted, would still need to satisfy; gate 3 in particular
("Overall Confidence is not the lowest category") was not re-implemented as a company-level gate this
task, since `company_confidence` is now always separately visible for a reader's own judgment rather
than gating a number that does not yet exist.

Overall Startup Power (the top-level number), if and when implemented, would be published only when,
simultaneously:

1. **Overall weighted coverage** clears `MIN_OVERALL_COVERAGE_PCT` (**CALIBRATION REQUIRED**).
2. **At least `MIN_PUBLISHABLE_PILLARS` pillars** (of six) independently clear their own
   pillar-level gates (6.2) (**CALIBRATION REQUIRED** — provisionally reasoned as similar in
   spirit to, but not copied from, either prior engine's own since-revised gate history,
   companion architecture document Part 8.2).
3. **Overall Confidence is not the lowest category** (mirrors the same principle both prior
   engines already implemented; adopted here as sound).

When any gate fails, the overall score would be withheld (`None`) with a disclosed reason, and — per
Design Principle 9 — the report still shows every pillar's own individually-publishable
Strength/Coverage/Confidence, never collapsing to a blank result. A pillar can be individually
publishable even when the overall score is withheld (or, as currently implemented, even when no
overall score exists at all); this is the intended, honest behavior for a company with excellent
evidence in two or three pillars and none in the rest, and it is distinguished in the report from a
blanket "not enough evidence anywhere" state.

### 6.6 The firewall property

`compute_strength()`, `compute_coverage()`, and `compute_confidence()` must be three functions
that never call each other and never read each other's output — verified by a dedicated test
(companion calibration document) that mutates Coverage or Confidence inputs alone and asserts
Strength is bit-for-bit unchanged, and vice versa. This is the one specific pattern this design
deliberately keeps from the prior V3 engine's own aggregation code, because it is a sound,
already-proven-in-this-codebase general engineering discipline, not a scoring rule (permitted
under "identify reusable infrastructure").

### 6.7 Parameters explicitly requiring calibration (complete list, not scattered)

| Parameter | What it controls | Where it must NOT be invented from |
|---|---|---|
| Every pillar weight (Part 3.3 header rows) | Overall score composition | Calibration cohort (companion document), not asserted here |
| Every dimension weight within a pillar (Part 3.3 tables) | Pillar Strength composition | Same |
| `MIN_PILLAR_COVERAGE_PCT` | Pillar-level withholding gate 1 | Same |
| `MIN_SCORED_DIMENSIONS_PER_PILLAR` | Pillar-level withholding gate 2 | Same (provisional reasoning given in 6.2, not a final value) |
| `MIN_OVERALL_COVERAGE_PCT` | Overall-score withholding gate | Same |
| `MIN_PUBLISHABLE_PILLARS` | Overall-score withholding gate | Same |
| Every Computed dimension's numeric band table (growth-rate tiers, scale tiers, funding-size tiers) | Turns a raw computed number into a 0-10 score | Same — no scale-tier cutoff in this document is a final number |
| Every Classified dimension's stage-indexed label-to-score table | Turns an AI-chosen label into a 0-10 score, per stage | Same |
| Confidence's exact weighting of support-status mix / corroboration / freshness | The Confidence categorical output | Same |
| Growth Trajectory's minimum measurement window (stated as "≥2 quarters" in 3.3, carried over as a sound general principle) | Whether a short window is annualized at all | Flagged explicitly as a carried-over structural principle, not a recalibrated value, since it addresses a distortion (short-window CAGR blowup) that is a property of the math, not of this specific methodology |
| **New (Task 9):** Product & Technology's stage-tiered label→score tables (`DIFFERENTIATION_LABEL_SCORES` etc.) | Same as "stage-indexed label-to-score table" above, now implemented with placeholder numbers | `NEW_ENGINE_CALIBRATION_REPORT.md` Part 8 — direction (early > growth > established) is a design decision; magnitude is not |
| **New (Task 9):** `SOURCE_RELIABILITY_WEIGHT` | Confidence's new source-reliability input | Same report, Part 5 — ordering is reasoned, weights are not |
| **New (Task 9):** `CONFIDENCE_MIN_RELIABILITY_FOR_HIGH` / `_FOR_MEDIUM` | Confidence's HIGH/MEDIUM thresholds | Same report, Part 5 — flagged as possibly too strict (never reached across 5 fixtures), not adjusted without real data |
| **New (Task 9):** Founding-age stage bands (`stage.py::_FOUNDING_AGE_BANDS`) | The age-based stage-determination fallback | Same report, Part 8 — never exercised against a real company's actual founding date |

---

## Part 7 — Versioning and Historical Integrity

- **Methodology identifier:** `evidence_engine.v1` (decided/approved).
- **Every persisted assessment stamps** the exact methodology identifier, every table version
  referenced in 6.7, and the model identifier used for extraction/classification calls — so a
  stored result is fully reproducible in principle (same evidence, same tables, same model
  version) even after the tables are recalibrated for future analyses.
- **No historical analysis under either prior engine is touched, reinterpreted, or silently
  compared against this engine's output.** This engine is purely additive at the persistence
  layer (architecture document, Part 3).
- **Recalibrating a parameter in Part 6.7 bumps the methodology identifier's calibration
  sub-version** (e.g., `evidence_engine.v1.1`), never overwrites `v1`'s stored results or
  recomputes them retroactively.

---

## Part 8 — What Was Inspected From the Prior Engines, and What Was (and Was Not) Kept

### 8.1 The failure this design specifically avoids repeating

Both prior engines let an LLM directly choose a final numeric score for the large majority of
dimensions (23 of 28 legacy dimensions; the prior V3 design's own "Category C" bounded
qualitative judgment, while more constrained, still let the AI's own read of a rubric determine
where within a band a score landed). This design closes that door entirely (Part 3.2, Part 5.1)
— there is no dimension anywhere in Part 3.3 where an AI call's output is closer to a score than
a label or a typed fact with a deterministic formula behind it.

### 8.2 The specific defect that motivated this task, confirmed independently

Tracing the legacy engine's own aggregation code (`app/ai/scoring.py::calculate_weighted_score`,
`app/ai/investment_score.py::calculate_base_score`) confirms the reported production failures
(a pillar score built from one scored dimension out of five, presented with no less confidence
than a fully-evidenced pillar) are a real, reproducible mechanism, not a one-off — the legacy
renormalization step excludes `Unavailable` dimensions correctly but re-weights the remainder to
100% with no floor on how little was actually scored, and the overall-score aggregation reads
each pillar's already-renormalized score with no awareness of that pillar's own coverage at all.
The already-built (but currently disabled) prior V3 engine independently reached a structurally
similar three-axis design and did add a coverage-based publishability gate
(`app/ai/sps_v3_engine/aggregation.py`) — but its most recent revision **removed** an equivalent
second, dimension-count-based gate in favor of coverage alone, reasoning (in that codebase's own
words) that a coverage-weighted sum "already sees" the failure modes the second gate existed to
catch. This design's own review (6.2) found that reasoning does not hold in the specific case of
one dimension whose weight alone clears the coverage floor — which is why Part 6.2 reinstates an
explicit second gate here, as a considered disagreement with the most recent version of that
prior design, not an oversight.

### 8.3 Infrastructure explicitly reused (patterns and utilities, never scoring values)

- The three-independent-passes "firewall" pattern for Strength/Coverage/Confidence (6.6).
- The general shape of a versioned, external parameter table for thresholds that require
  calibration rather than hand-invented constants (the prior V3 engine's `ParameterRegistry`
  pattern) — the specific numbers are not reused; the pattern of "code reads a named,
  versioned parameter rather than a literal" is.
- Raw research/ingestion utilities that contain no scoring logic at all (Tavily search, PDF
  text extraction, website scraping) — reused as-is, unmodified, per explicit instruction to
  reuse research infrastructure "wherever practical" (architecture document, Part 2).
- The existing bounded-concurrency helper (`app/ai/concurrency.py::run_concurrently`) for
  dispatching the engine's own independent research/classification calls — a general utility,
  not scoring logic.
- The general discipline of a closed missing-evidence-reason taxonomy (the legacy engine's
  `MissingEvidenceState` concept) — redesigned from scratch for this engine's own ledger model
  (Part 2) rather than imported, since the underlying data model (a Claim ledger) is itself new,
  but the *idea* of a small, closed set of named reasons for "why is this missing" rather than a
  single boolean is kept.

### 8.4 Explicitly not reused

Every pillar/dimension definition, every weight, every score-band description, every
confidence-cap value, and both prior engines' specific aggregation formulas are not reused. This
engine's dimension set (Part 3.3), its Computed/Classified category system (3.2), and its
two-gate publishability rule (6.2) are new designs produced for this task, informed by (not
copied from) the failure analysis above.
