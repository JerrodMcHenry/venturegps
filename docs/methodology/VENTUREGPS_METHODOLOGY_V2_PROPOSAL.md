# VentureGPS Methodology V2 — Proposed Specification

**Status: PROPOSAL ONLY. No production code, prompts, schemas, database records, or API
behavior has been changed by this document. Nothing here has been implemented. This is
the Task 8 deliverable — read for approval, then stop.**

**A naming note before anything else, because this codebase already has two things called
"v2" and one called "v3":** the legacy pillar methodology's own internal version string is
already `"v2.1-spec-2026-08-29"` (`app/ai/sie_methodology.py`, stamped into every analysis's
`analysis_context.methodology_version`), and a structurally different, already-built,
currently-disabled-by-default engine already exists under the name **SPS V3**
(`app/ai/sps_v3_engine/`, `sps_v3.engine_version = "SPS_V3_10_9H"`). Task 8 calls the work
requested here "Methodology v2 Design." **This document does not mint a third "v2."** Part 7
below proposes an explicit, unambiguous new version identifier and flags it as an open
question — the name "v2" in this file's own filename is Task 8's label for the *initiative*,
not a claim about which internal version string the result will carry.

---

## Part 0 — Executive Summary

Two concrete, real production failures were reported: Notion scored 69.1 overall with
Traction at 60 despite 4 of 5 Traction dimensions being `Unavailable`, and Financial Health
scored 74 despite Unit Economics and Runway both being `Unavailable`. This audit traced both
to one exact, reproducible mechanism (Part 1.3) and confirmed it against a real stored
analysis from this codebase's own validation history
(`app/calibration/validation_2026_08/raw_results/notion_labs.json`: Traction score 7.0/10,
confidence `"Low"`, `evidence_coverage: 15.0`, with `Customer Growth`, `Revenue Growth`,
`Retention`, and `Engagement` all `Unavailable` and only `Growth Velocity` scored — the exact
shape of the reported bug, reproduced independently of the specific run the task cites).

**The most consequential finding of this audit is that the fix does not need to be invented.**
A structurally sound answer to almost this entire task already exists in this codebase,
already designed in detail (`docs/methodology/SPS_METHODOLOGY_V3_DESIGN.md`, 1,472 lines) and
already partially implemented and tested (`app/ai/sps_v3_engine/`, 3,582 lines; a 31-company
calibration roster; a leakage register; sensitivity analysis; synthetic validation). It was
briefly the default engine (`docs/methodology/SPS_V3_CANONICAL_ACTIVATION.md`), then returned
to disabled-by-default during this project's own Task 7, Phase 2, on the recommendation to
"keep six-pillar as canonical" while the adapter work below remained unfinished — not because
the architecture was found wrong.

**What is genuinely missing is one specific thing:** SPS V3's evidence-classification adapter
(`app/ai/sps_v3_adapter.py::classify_evidence_for_v3`) only populates 9 of 27 dimensions. It
never populates Financial Health at all, and never populates 4 of Traction's 5 dimensions
(`SPS_V3_CANONICAL_ACTIVATION.md` §6). This is why V3, when it briefly ran by default, mostly
returned `"limited"` or `"insufficient"` rather than ever reaching `"sufficient"` — not because
real companies lack evidence, but because the adapter was never finished for those two pillars.

**Recommendation, stated up front and justified in the parts below:** do not design a fourth
scoring system. Finish SPS V3's adapter for the two unpopulated pillars, apply a small set of
genuinely new refinements this audit identified that V3's own design does not yet cover
(Financial Health's public-vs-private evidence split, an explicit "Stage: Uncertain" state,
extending V3's existing calibration roster rather than replacing it), and then retire the
legacy renormalize-blindly pipeline in favor of V3's already-built three-axis
(Power/Coverage/Confidence) and publishability-gate architecture. This is both the most
correct answer and, because most of the hard design and a meaningful fraction of the
implementation already exists and is already partially calibrated, the smallest one.

Consequential decisions and open questions requiring approval are collected in Part 8.

---

## Part 1 — Audit of the Existing Methodology

### 1.1 Pipeline as it exists today

```
POST /analyze  (app/api.py)
  -> run_due_diligence()  (app/workflows/due_diligence_workflow.py)
       -> research enrichment (Tavily, 4 categories, concurrent)
       -> 5 free-form narrative calls (concurrent)
       -> six pillar analyses (concurrent; each pillar internally sequential):
            extract_pillar_evidence()  -- Stage 1: LLM decides evidence + evidence_status
            score_pillar_evidence()    -- Stage 2: LLM picks a 0-10 number per dimension
            finalize_pillar_score()    -- scoring.py: weighted average, Stage 3, deterministic
       -> assemble_sie_analysis()  (app/workflows/sie_assembler.py)
            -> calculate_investment_score()  (app/ai/investment_score.py: overall SPS)
            -> compute_partial_structural_coverage()  (display-only flag)
            -> [if SPS_ENGINE_VERSION selects v3] sps_v3_adapter.compute_sps_v3_assessment()
       -> generate_readiness_score()  (separate LLM call, prose only)
  -> save_analysis()
```

Confirmed live in `app/ai/analyze_pillar.py`, `app/ai/scoring.py`, `app/ai/investment_score.py`,
`app/workflows/sie_assembler.py`, `app/workflows/due_diligence_workflow.py`, and this session's
own Task 7 Phase 2 concurrency work (`app/ai/concurrency.py`), which changed call *scheduling*
only — it did not touch any scoring math and is orthogonal to everything below.

### 1.2 Every existing subscore: weight, evidence requirement, and public-research realism

Source: `app/ai/scoring_methodology.py` (1,807 lines, `SCORING_METHODOLOGY`), the single
source of truth for all 28 scored dimensions (Fundraising Readiness, a 29th, was demoted to an
unscored narrative flag by a prior "v2.1" pass and never enters any calculation — see 1.4).

**Legend for "Realistically publicly assessable?":** **Yes** = a diligent public-research pass
(company site, press, job postings, funding databases, product docs, review sites) can usually
find real signal for this; **Sometimes** = depends heavily on company disclosure choices, stage,
and press coverage; **Rarely** = this is normally confidential/data-room information and public
research will usually come up empty, by the nature of the dimension, not the researcher's
effort.

| Pillar | Dimension | Weight | `evidence_requirement` tag | Realistically publicly assessable? | Current scoring behavior |
|---|---|---|---|---|---|
| Market (0.20 of SPS) | Market Size | 0.25 | Public | Yes — inferable from ICP/geography/category | LLM free-form 0-10 |
| | Market Growth | 0.20 | Public | Yes — category growth is usually press/report-covered | LLM free-form 0-10 |
| | Market Timing | 0.20 | Public | Sometimes — depends on whether a clear external trigger is publicly discussed | LLM free-form 0-10 |
| | Competitive Intensity | 0.15 | Public | Yes — competitors and positioning are usually public | LLM free-form 0-10 |
| | Customer Demand | 0.20 | **Inferred** (mistagged in spirit — see below) | Sometimes — paying-customer counts are often disclosed, retention/expansion rarely is | LLM free-form 0-10 |
| Team (0.20) | Founder-Market Fit | 0.25 | Public | Yes — LinkedIn/press bios are the normal source | LLM free-form 0-10 |
| | Technical Capability | 0.20 | Inferred | Sometimes — shipped product is public, engineering depth claims often aren't verifiable | LLM free-form 0-10 |
| | Business Capability | 0.20 | Inferred | Rarely — GTM/pricing/unit-economics detail is usually private | LLM free-form 0-10 |
| | Leadership | 0.20 | Inferred | Sometimes — named hires are public, hiring *quality* and internal dysfunction rarely is | LLM free-form 0-10 |
| | Execution Track Record | 0.15 | Inferred | Sometimes — shipped milestones are public, growth figures rarely are without disclosure | LLM free-form 0-10 |
| Product (0.20) | Customer Value | 0.25 | Inferred | Sometimes — reviews/case studies help, ROI/retention figures rarely public | LLM free-form 0-10 |
| | Differentiation | 0.20 | Public | Yes — competitor comparison is a public-research task | LLM free-form 0-10 |
| | Usability | 0.15 | Public | Sometimes — review sites (G2, Capterra) help when the company is reviewed there | LLM free-form 0-10 |
| | Defensibility | 0.20 | Inferred | Sometimes — integrations/partnerships are public, switching-cost depth rarely is | LLM free-form 0-10 |
| | Adoption Potential | 0.20 | Inferred | Sometimes — logo counts sometimes disclosed, NRR/churn rarely is | LLM free-form 0-10 |
| Execution (0.15) | Go-to-Market Execution | 0.25 | Inferred | **Rarely** — CAC/pipeline/conversion is core private commercial data | LLM free-form 0-10 |
| | Product Execution | 0.25 | Inferred | Sometimes — shipped features/integrations are public, reliability data rarely is | LLM free-form 0-10 |
| | Operational Execution | 0.25 | **Private** | **Rarely** — burn/margin/hiring-cadence detail is core private operating data | LLM free-form 0-10 |
| | Strategic Execution | 0.25 | Inferred | Sometimes — public strategy statements exist but "was this the right call" is inherently judgment-heavy, not evidence-heavy | LLM free-form 0-10 |
| Traction (0.15) | Customer Growth | 0.15 | Public | Sometimes — two dated customer counts are occasionally disclosed | **Deterministic** (`sie_v2_anchors.py`), fail-closed without a real two-point series |
| | Revenue Growth | 0.25 | Public | **Rarely** at private companies — ARR/MRR is core private financial data | Deterministic, fail-closed |
| | Retention | 0.25 | Public | **Rarely** — NRR/GRR/churn is almost never voluntarily disclosed pre-IPO | LLM free-form 0-10 (not actually Deterministic despite the Public tag) |
| | Engagement | 0.15 | Inferred | Sometimes — usage claims sometimes appear in press/case studies | LLM free-form 0-10 |
| | Growth Velocity | 0.20 | Public | **Rarely** — needs two dated actual (not projected) figures for the *same* metric | Deterministic, fail-closed; structurally Not Applicable pre-revenue |
| Financial Health (0.10) | Revenue Quality | 0.20 | Inferred | Sometimes — "recurring vs. one-time" is sometimes discussable qualitatively without a number | LLM free-form 0-10 |
| | Unit Economics | 0.25 | **Private** (corrected from a prior Public mistag, per code comment) | **Rarely** | LLM free-form 0-10 |
| | Burn Efficiency | 0.25 | Private | **Rarely** | LLM free-form 0-10 |
| | Runway | 0.30 | Public (mistagged — see below) | **Rarely** — cash-on-hand/burn-rate is core private financial data | LLM free-form 0-10 |

**Dimensions that depend on confidential financial or operational information (the task's own
explicit ask):** Unit Economics, Burn Efficiency, Runway (all of Financial Health except
Revenue Quality), Go-to-Market Execution, Operational Execution, and — despite their `Public`
tag — Revenue Growth and Retention in Traction. That is **7 of 28 dimensions, carrying 0.25 +
0.25 + 0.30 = 0.80 of Financial Health's weight and 0.25 + 0.25 = 0.50 of Traction's weight** —
concentrated in exactly the two pillars the production failures were reported in. This is not a
coincidence; it is why those two pillars are structurally the ones most likely to have most of
their weight `Unavailable` for any company assessed from public sources only, and it is why any
fix must treat "most of Financial Health/Traction is usually private" as an expected, honest
structural property (a position SPS V3's design already reaches independently, Part 1.5) rather
than something to score around.

**Existing tag inaccuracies found in this audit, beyond what prior "v2.1" work already
corrected:** Runway carries `evidence_requirement="Public"` in `scoring_methodology.py` today,
but its own rubric text ("cash on hand," "burn rate") is exactly as private as Unit Economics
and Burn Efficiency, which are already correctly tagged `Private`. This looks like a leftover
mistag from before the Unit Economics correction (the code comment at line 1606-1608 shows one
such correction already happened for Unit Economics specifically) that was never extended to
Runway. Retention is tagged `Public` but is scored by a free-form LLM call, not the Deterministic
path its Traction siblings use, and NRR/GRR disclosure is realistically no more public than
Revenue Growth's. Recommend both be corrected to `Private` as part of this work (Part 2).

### 1.3 The renormalization defect — exact mechanism, confirmed in code and in real data

This is the root cause of both reported production failures. It is **one mechanism operating
at two levels**, and it survived through a prior methodology revision ("v2.1") that explicitly
declared this exact behavior correct.

**Level 1 — within a pillar** (`app/ai/scoring.py::calculate_weighted_score`):

```python
scorable_subscores = [s for s in subscores if s.score is not None and s.evidence_status != "Unavailable"]
...
total_weight = sum(s.weight for s in scorable_subscores)   # only the SCORED dimensions' weight
weighted_score = sum(s.score * s.weight for s in scorable_subscores) / total_weight
```

`Unavailable` dimensions are correctly excluded rather than defaulted to zero (a real, sound
design decision — see 1.4). But the remaining weight is then **renormalized to 100%** across
whatever is left. For Traction, if only `Growth Velocity` (weight 0.20) is scored and the other
four dimensions (weight 0.15 + 0.25 + 0.25 + 0.15 = 0.80) are `Unavailable`, that single
dimension's score becomes **the entire pillar score** — a number built from 20% of the intended
assessment, presented with exactly the same numeric confidence as a pillar built from 100% of
it. This is confirmed against real stored data
(`app/calibration/validation_2026_08/raw_results/notion_labs.json`): Traction score 7.0,
`evidence_coverage: 15.0`, with only `Growth Velocity` (or in that specific run, whichever
single Deterministic dimension had a real two-point series) scored and everything else
`Unavailable`.

**Level 2 — across pillars** (`app/ai/investment_score.py::calculate_base_score`):

```python
for pillar_name, weight in PILLAR_WEIGHTS.items():
    pillar_score = getattr(pillar, "score", None)
    if pillar_score is None:
        continue                      # only fully-Unavailable pillars are dropped
    scored_pillars.append((pillar_score, weight))
included_weight = sum(weight for _, weight in scored_pillars)
weighted_score = sum(score * weight for score, weight in scored_pillars) / included_weight
```

This reads each pillar's already-renormalized-from-Level-1 score and blends it into the overall
SPS using the pillar's full nominal weight (0.10 for Financial Health, 0.15 for Traction), with
**zero awareness of that pillar's own `evidence_coverage`**. A Financial Health score of 74
built from 45% real coverage (only Revenue Quality and Burn Efficiency scored; Unit Economics
and Runway `Unavailable`) counts in the overall SPS exactly as if it were built from 100%
coverage. **`calculate_base_score` never reads `evidence_coverage` or `confidence` at all** —
confirmed by reading the full function; those fields exist on `PillarScoreBreakdown` but nothing
downstream of pillar-level `finalize_pillar_score` ever looks at them again.

**Why this is not a "bug" in the sense of a coding mistake, but a real methodology gap:** a
prior "v2.1" implementation pass explicitly audited this exact aggregation logic
(`app/docs/SIE_Methodology_v2_Implementation_Gap_Analysis.md`, "Aggregation" row) and concluded:
*"already scored-set-only, already renormalizes, already excludes `None`/`Unavailable` with no
defaulting — this already matches v2 Part 4/9's core requirement."* That conclusion is correct
as far as it goes (unknown information is never treated as evidence of weakness, which is the
one thing the prior spec's Part 4 actually required) — but it never asked the complementary
question: *at what point does "renormalize over what's scored" stop being honest because too
little was scored to renormalize over?* That question was explicitly identified as open and
never answered: the same gap-analysis document's closing section lists **"SPS-suppression
coverage floor... no calibration-program value exists for any of these (Part 11 lists them as
still open)"** as unresolved technical debt. The Notion/Financial-Health production failures are
that exact unresolved gap surfacing in real data.

### 1.4 What "v2.1" already built, and why it was not enough

A substantial amount of relevant machinery already exists and should be reused, not rebuilt:

- **`MissingEvidenceState`** (`app/ai/sie_v2_evidence_semantics.py`) — a 9-state taxonomy for
  *why* a dimension is `Unavailable` (not expected by stage, not applicable, optional, usually
  private, expected but missing, research failure, management refusal, unresolved conflicting
  evidence, resolved conflicting evidence), each with its own diligence-flag severity. This is
  exactly the kind of "distinguish missing information from demonstrated poor performance"
  vocabulary Part 3 of this task asks for, and it already exists.
- **Confidence score caps** (`app/ai/scoring.py::apply_confidence_score_cap`) — a Low-confidence
  dimension score cannot exceed 6.0, Medium cannot exceed 8.5. Real and load-bearing (it does
  change individual dimension scores), but it caps *scores*, never *whether a pillar number
  should be shown at all* — it would not have prevented either reported failure, since a single
  scored dimension can still be Medium/High confidence on its own even while four siblings are
  `Unavailable`.
- **Partial Structural Coverage ("PSC")** (`compute_partial_structural_coverage`) — flags when a
  pillar is *entirely* `Unavailable` (zero scored dimensions). Explicitly documented as
  **"Display-layer label only. SPS math is unchanged and unpenalized."** Crucially, it only
  fires at 0% coverage — a pillar with exactly one scored dimension out of five (Notion's
  Traction, 20% coverage) never trips it, because "unavailable" here means the pillar score is
  `None`, and a pillar with even one scored dimension always has a real, non-`None` score. **PSC
  cannot catch either reported production failure by construction.**
- **Evidence Independence Metadata** — concentration/duplication detection for scored evidence.
  Real and useful, but also explicitly "metadata-only," never gating a score.

**The pattern across all four:** every one of "v2.1"'s coverage/confidence/provenance
improvements was built as **additive, display-layer reporting**, deliberately never touching the
score-computation path (`calculate_weighted_score`/`calculate_base_score`). This was a
reasonable, low-risk choice at the time it was made (each of these was scoped under a "do not
change the scoring formula" constraint, per its own commit history and comments) — but the
net effect is that today's production report can show a company "Medium confidence,
`evidence_coverage: 45.0`" *right next to* a pillar-level score of 74, with nothing in the
pipeline connecting the two. The task's own framing — "we must fix the underlying methodology,
not manually adjust scores" — is, precisely, permission to finally close this gap.

### 1.5 A structurally sound answer already exists: SPS V3

`docs/methodology/SPS_METHODOLOGY_V3_DESIGN.md` (1,472 lines) independently reaches nearly
every conclusion this audit reaches, from a different starting complaint (LLM-fabricated
numbers and mid-band clustering, not renormalization specifically), and its recommended
architecture already **structurally prevents both reported production failures**:

- **Three-axis output** — Power (renamed "Strength" internally), Coverage, Confidence computed
  as three independent passes over the same dimension results, verified in code
  (`app/ai/sps_v3_engine/aggregation.py`) to never read each other's output — this is Part 3 of
  this task, already built.
- **Publishability gates** — `evaluate_pillar()` withholds a pillar's numeric Strength entirely
  (`publishable=False`, `withhold_reason=...`) when that pillar's own weighted coverage is below
  a configured floor (`gate.min_pillar_coverage_pct`); `evaluate_sps()` does the same at the
  overall level (`gate.overall_coverage_floor_pct`). Three UX states —
  `sufficient`/`limited`/`insufficient` — are derived purely from these gates
  (`classify_ux_state()`). **This is exactly Part 3's "define explicit conditions under which a
  dimension, pillar or overall score must be withheld,"** already implemented and already
  covering the "one inferred dimension representing a whole pillar" failure mode by construction
  (a pillar with 20% coverage fails `gate.min_pillar_coverage_pct` and is withheld rather than
  shown as "Traction: 60").
- **Traction redesigned** (`app/ai/sps_v3_engine/evaluators.py`) into `current_scale` (0.20,
  scorable from a single disclosed figure — no two-point series required),
  `growth_trajectory` (0.25, still correctly fail-closed without two dated points),
  `customer_adoption` (0.20), `retention_engagement` (0.20), `commercial_validation` (0.15).
  This directly fixes the *structural* coverage-ceiling problem the design doc found (every real
  audited company hit exactly 15% Traction coverage under the old all-Deterministic design,
  because scale-without-growth-history had no dimension that could credit it at all).
- **Financial Health redesigned** into `revenue_quality` (0.35, Category B/taxonomy — realistic
  for public research), `unit_economics` (0.30, Deterministic, fail-closed, correctly Private),
  `capital_efficiency` (0.35, Deterministic, fail-closed, correctly Private — a merger of the old
  Burn Efficiency and Runway concepts). The design doc explicitly states: **"Should Financial
  Health frequently have low public coverage? Yes — this should be treated as an expected,
  honest, structural property... not a defect to engineer away."**
- **Stage fairness as a lookup table, not prose** — the same taxonomy classification maps to a
  different score band depending on stage, enforced by code, not by an LLM's inconsistent
  reading of `stage_guidance` text.
- **A 31-company calibration roster already built and partially executed**
  (`docs/validation/SPS_V3_CALIBRATION_DATASET.md`, `SPS_V3_P0_CALIBRATION_REPORT.md`), with a
  leakage register, training/holdout split, sensitivity analysis, and synthetic-suite tests
  already run.

**What is genuinely, honestly missing** (confirmed in `docs/methodology/
SPS_V3_CANONICAL_ACTIVATION.md` §6 and by reading `app/ai/sps_v3_adapter.py` directly): the
adapter that turns raw evidence into the typed inputs this engine consumes
(`classify_evidence_for_v3`) **only classifies evidence for 9 of the 27 scored dimensions**. It
never populates any Financial Health dimension, and never populates 4 of Traction's 5
dimensions (`current_scale`, `growth_trajectory`, `retention_engagement`,
`capital_efficiency` — everything except `customer_adoption`). This is confirmed by this
project's own live verification of the one time V3 ran as the default engine: **coverage 26.0%,
`withhold_reason: "Overall coverage 26.0% < 35% floor"`, Traction and Financial Health both at
0.0% coverage** — not because the company had no evidence, but because the adapter was never
built for those two pillars. This is a genuinely scoped, well-documented, finishable gap, not an
architectural flaw — and it is the single highest-leverage piece of remaining work identified by
this audit (Part 7).

### 1.6 Version-string inventory (why Part 7 flags this as an open question)

| Identifier | Where it lives | What it currently means |
|---|---|---|
| `analysis_context.methodology_version` | Every analysis, legacy pipeline | `"v2.1-spec-2026-08-29"` — the six-pillar, 28-dimension, renormalize-blindly methodology audited in 1.1-1.4 |
| `scoring_methodology.SCORING_VERSION` | `app/ai/scoring_methodology.py` | `"2.0"` — the pillar-weight/aggregation-formula version, a *different* version axis from the one above |
| `sps_v3.engine_version` / `sps_v3.scoring_version` | Additive `sps_v3` field, currently disabled by default | `"SPS_V3_10_9H"` / `"sps_v3.10_9.1"` — the architecture described in 1.5 |

Any new work must not reuse any of these three strings for something new (Phase 10.9's own
design explicitly forbade reusing a V2.1 string for V3, for exactly this reason). See Part 7.

---

## Part 2 — Revised Pillars

**Design stance:** the six pillars (Market, Team, Product, Execution, Traction, Financial
Health) remain the right top-level structure — the audit found no evidence they measure the
wrong things, only that two of them (Traction, Financial Health) were built on dimensions that
are structurally hard to score from public evidence, and that renormalization hides that fact
rather than surfacing it honestly. Market, Team, and Product need no dimension redesign;
Execution and Traction/Financial Health do.

### 2.1 Market — unchanged

Five dimensions, weights, and rubrics as already defined in `scoring_methodology.py` (1.2
above) are sound: all five are genuinely public-research-realistic, and the audit found no
structural coverage problem here (nothing in this pillar depends on private data).
**Recommendation: keep as-is.**

### 2.2 Team — unchanged

Same conclusion. Founder-Market Fit is genuinely Public; the other four are Inferred but from
signals (shipped product, named hires, press) that a diligent public search realistically finds
*something* on, even if not a complete picture. **Recommendation: keep as-is.**

### 2.3 Product — unchanged

Same conclusion, with one caveat carried into Part 5: `Customer Value` and `Adoption Potential`
lean on retention/expansion signals that are usually private — but unlike Traction/Financial
Health, Product's other three dimensions (Differentiation, Usability, Defensibility) are
genuinely public-research-realistic and can carry the pillar on their own without triggering the
coverage floor discussed in Part 3. **Recommendation: keep as-is; monitor via calibration
(Part 6) rather than redesign preemptively.**

### 2.4 Execution — narrow, don't redesign

Go-to-Market Execution and Operational Execution are both realistically private (1.2). Unlike
Traction/Financial Health, however, Execution's other two dimensions (Product Execution,
Strategic Execution) are genuinely assessable from shipped-product and public-strategy
evidence, and Execution's own overall weight (0.15) is smaller than Traction's structural
private-weight problem. **Recommendation: no dimension redesign for Execution in this phase.**
Flag Operational Execution's `Private` tag as already correct (it needs no correction, unlike
Runway/Retention in Part 1.2) and rely on the new pillar-level coverage floor (Part 3) to
withhold Execution honestly on the rare company where both public dimensions also come up
empty, rather than inventing new dimensions for a problem this audit did not find evidence of at
production scale.

### 2.5 Traction — adopt SPS V3's redesign as-is

Adopt, verbatim, the 5-dimension redesign already implemented in
`app/ai/sps_v3_engine/evaluators.py` and justified in `SPS_METHODOLOGY_V3_DESIGN.md` (Part 1.5
above): **Current Scale** (0.20), **Growth Trajectory** (0.25), **Customer Adoption Breadth**
(0.20), **Retention/Engagement** (0.20), **Commercial Validation** (0.15).

- **What each measures:** Current Scale — has the company reached a real, disclosed absolute
  level (revenue, GMV, ARR, users) at a point in time. Growth Trajectory — is that level
  increasing/decreasing over time (requires two dated points; correctly stays fail-closed
  without them). Customer Adoption Breadth — how many/what kind of customers have adopted the
  product (a taxonomy: named count bands, customer-type mix), not a dated series. Retention/
  Engagement — do adopted customers keep using/paying (Deterministic when NRR/GRR/churn is
  disclosed, taxonomy otherwise). Commercial Validation — have real buyers committed (named
  contracts, enterprise logos, renewals), independent of whether revenue scale is disclosed.
- **Acceptable public evidence:** press-covered customer/revenue figures, funding-round
  announcements that disclose growth metrics, case studies, G2/Capterra reviews mentioning
  adoption, named enterprise-logo announcements.
- **Minimum evidence to score:** Current Scale needs one dated, confirmed-actual figure (not a
  projection). Growth Trajectory needs two dated points for the *same* metric, both confirmed
  actuals, spanning at least ~2 quarters (per the existing anchor architecture's own guard
  against short-window CAGR distortion). Customer Adoption Breadth and Commercial Validation
  need at least one named, checkable fact (a customer count, a named logo) — a bare claim of
  "many customers" with nothing checkable stays `Unavailable`.
- **Weak / moderate / strong:** unchanged in spirit from the existing rubric bands (0-2 through
  9-10 in `scoring_methodology.py`), re-anchored to each new dimension's narrower question
  rather than a blended "growth+scale+retention" question.
- **Stage effect:** Current Scale and Commercial Validation are structurally Not Applicable
  pre-revenue (Idea/Pre-Seed); Growth Trajectory is Not Applicable without two dated points
  regardless of stage, by construction, never "not yet available so we'll infer it."
- **Missing/conflicting/company-provided evidence:** exactly the existing `MissingEvidenceState`
  taxonomy (Part 1.4) already applies unchanged — this redesign changes *what* the five
  dimensions ask, not how missing evidence is classified.

### 2.6 Financial Health → renamed "Financial & Funding Signals"

**Renaming evaluated and recommended.** "Financial Health" implies the pillar assesses whether
the company's finances are healthy — but for a private company assessed from public sources
only, the pillar realistically assesses something narrower and more honest: *what public
signals exist about the company's financial and funding position*, most of which is about
capital raised and disclosed top-line figures, not the internal health metrics (burn, margin,
runway) that word implies. **"Financial & Funding Signals" is proposed as the new name** because
it (a) sets an accurate expectation that this pillar will frequently show partial or withheld
data for private companies, matching SPS V3's own design conclusion (1.5) that this is honest
and structural rather than a defect, and (b) makes room for genuinely public funding evidence
(see below) that "Financial Health" doesn't obviously cover today.

Adopt SPS V3's 3-dimension redesign as the base — **Revenue Quality** (Category B/taxonomy,
weight to be set in calibration, provisionally 0.30), **Unit Economics** (Deterministic,
fail-closed, `Private`, provisionally 0.30), **Capital Efficiency** (Deterministic, fail-closed,
`Private`, merging the old Burn Efficiency/Runway concepts, provisionally 0.30) — **plus one
genuinely new dimension this audit adds, not present in either the legacy pillar or the SPS V3
design doc:**

- **Funding Signals** (Category B/taxonomy, `Public`, provisionally 0.10): what has this company
  publicly disclosed about capital raised — round size, round date, lead/named investors,
  publicly reported valuation. This is realistically public (funding announcements, Crunchbase/
  PitchBook-style press coverage, the company's own press releases) even when unit economics,
  burn, and runway are not, and it is exactly the kind of "publicly assessable criteria replacing
  an inaccessible private metric" the task explicitly asks this audit to evaluate (task Part 2,
  final sentence). **This dimension measures only that a disclosed funding fact exists and is
  corroborated — it explicitly does not attempt to infer burn or runway from round size, which
  would reintroduce exactly the fabrication risk `evidence_provenance.py`'s guard already exists
  to catch.**
- **What it does not fix:** Unit Economics and Capital Efficiency remain genuinely,
  irreducibly private for the large majority of companies assessed from public sources alone.
  Adding Funding Signals raises the pillar's realistic public-coverage ceiling from ~20% (Revenue
  Quality alone, in the old 4-dimension structure) to something meaningfully higher without
  fabricating numbers for the other three — but does not, and should not be expected to, make
  Financial & Funding Signals a normally-`sufficient` pillar for a typical public-source-only
  private-company analysis. That expectation itself needs to be surfaced to users (Part 4).

---

## Part 3 — Performance, Evidence Coverage, and Confidence

Adopt SPS V3's three-axis architecture (1.5) as the canonical design, with one addition this
audit proposes to close the exact gap Part 1.3/1.4 found in the legacy pipeline's PSC:

- **Performance ("Power"/"Strength")** — computed only from responsibly-scorable dimensions,
  renormalized among them, exactly as `compute_pillar_strength`/`evaluate_sps` already do in
  `app/ai/sps_v3_engine/aggregation.py`. Never defaults an unavailable dimension to zero or an
  average.
- **Evidence Coverage** — the fraction of a pillar's/the methodology's total configured weight
  that was backed by scorable evidence, computed identically at the dimension, pillar, and
  overall level, exactly as `compute_pillar_completeness_pct`/`_compute_overall_coverage`
  already do.
- **Confidence** — how reliable the evidence *backing the scored dimensions* is, independent of
  how much was scored, exactly as `compute_pillar_confidence` already computes it (a
  weighted-average confidence ordinal over only the scored dimensions).

**Firewall property to preserve exactly:** these three are computed as independent passes over
the same dimension-result list, verified by construction (none of the three functions reads
another's output) — this is what makes "changing Coverage/Confidence must never mathematically
change Power" true by construction rather than by convention, and it must remain true in
whatever replaces the legacy pipeline.

**Withholding conditions (adopt V3's gates, Part 1.5, as the baseline; new calibration work in
Part 6 sets the exact numeric floors):**

1. A pillar's own numeric Strength is withheld when that pillar's weighted Evidence Coverage
   falls below a configured floor (`gate.min_pillar_coverage_pct`). This is the single rule that
   would have prevented both reported production failures — Notion's Traction at 15-20%
   coverage and Financial Health at ~45% coverage would both need this floor set below their
   respective values to have passed through un-withheld, and calibration (Part 6) is exactly the
   process for choosing that floor honestly rather than tuning it to make any one company's
   score come out a particular way.
2. The overall Startup Power Score is withheld when overall weighted Evidence Coverage falls
   below a separate, overall floor (`gate.overall_coverage_floor_pct`), independent of any single
   pillar's own gate.
3. **New in this proposal:** when a pillar is withheld, the product must show *why*, using the
   existing `MissingEvidenceState` taxonomy's aggregate shape (e.g., "3 of 5 dimensions
   `Usually-Private-And-Unavailable`, not a research failure") rather than a bare "not enough
   evidence" — closing the exact "distinguish missing information from demonstrated poor
   performance" requirement with vocabulary that already exists (Part 1.4) but was never
   connected to a withholding decision until now.
4. **No dimension, pillar, or the overall score may ever collapse "insufficient evidence" into a
   score of zero or a heavily discounted number.** `None`/withheld is a distinct, explicit state
   from every real numeric value — this is already how `sps_v3.overall_score: float | None`
   is modeled (`app/models/sps_v3.py`) and must remain true for whatever new canonical field
   replaces it.

**One inferred dimension must never represent an entire pillar (the task's explicit
instruction):** directly satisfied by rule 1 above whenever the calibrated floor is set above
the weight of any single dimension in the pillars most at risk (Traction's largest single
dimension is 0.25 of that pillar's total; Financial Health's largest is ~0.35 under the Part 2.6
redesign) — this is a calibration-driven number, not a hand-picked one, and Part 6 is where it
gets set with evidence, not asserted here.

---

## Part 4 — Stage-Aware Assessment

### 4.1 How stage is determined today, and its real limitation

Stage is extracted as free text by an existing LLM call (`structured_analysis.py`, feeding
`SIEContext.company_stage`/`funding_stage`) and then best-effort keyword-matched into one of six
buckets (`app/ai/sps_v3_adapter.py::map_stage`: Idea, Pre-Seed, Seed, Series A, Series B+,
Growth) by substring search against a fixed keyword list. **Confirmed limitation:** an
unrecognized or empty stage string **silently defaults to Seed** (`map_stage`'s own final
`return Stage.SEED`), with no signal anywhere downstream that the stage was actually unknown
rather than confidently determined. This is a real gap this audit found that neither the legacy
pipeline nor the SPS V3 design doc's own Stage Fairness section addresses.

**Proposed fix:** add an explicit seventh state, `Stage: Uncertain`, distinct from any of the
six real stages, returned when no keyword match is found — rather than silently defaulting to
Seed. A company whose stage cannot be determined should be scored against the *most permissive*
applicable band per dimension (never penalized for failing to clear a bar for a stage it may not
actually be at) and the report should visibly disclose that stage is uncertain, rather than
implicitly presenting Seed-stage expectations as if they were confidently determined.

### 4.2 Stage effect: weights, criteria, or both

Adopt SPS V3's mechanism (1.5): stage affects **scoring criteria** (which taxonomy label maps to
which score band, via a per-stage lookup table, not prose) rather than **dimension weights**.
Pillar and dimension weights stay fixed across stages — an early-stage company is not scored on
a smaller Traction pillar than a growth-stage one; it is scored on the same Traction dimensions,
judged against a lower bar per dimension appropriate to what a company at that stage should
reasonably be able to show (exactly matching the task's own "avoid penalizing early-stage
companies for not having mature-company revenue histories" and the symmetric "avoid penalizing
established companies solely because confidential metrics aren't publicly disclosed" — the
latter is really a Coverage-axis question, not a stage question: Part 3's withholding gates,
not a stage-conditioned score, are what prevents an established company's undisclosed unit
economics from being scored as weak).

### 4.3 Missing, outdated, conflicting, or company-provided information

- **Missing:** `MissingEvidenceState` (Part 1.4), unchanged, extended to the new dimensions in
  Part 2.
- **Outdated:** governed by source freshness rules (Part 5).
- **Conflicting:** the existing `CONFLICTING_EVIDENCE_UNRESOLVED`/`CONFLICTING_EVIDENCE_RESOLVED`
  states already model this — unresolved conflicting evidence is excluded from scoring exactly
  like any other `Unavailable` state; resolved conflicting evidence is scored but capped to Low
  confidence, never allowed to reach a high anchor band on the strength of a single
  tie-broken source.
- **Company-provided:** SPS V3's design (Part 1.5, "Financial Health Redesign" ¶3) already
  specifies the correct model for this, unimplemented but fully designed: founder-submitted
  evidence produces the same typed `CanonicalObservation` structures as public evidence and
  flows through the identical deterministic evaluators — the evaluator does not know or care
  whether an observation came from a public website or a founder upload, only whether it is
  accepted and dated. This is adopted as-is; no change proposed here.

---

## Part 5 — Evidence Provenance

### 5.1 Claim-to-source connection

Adopt the `CanonicalObservation` concept from SPS V3's design as the target model: every
scorable claim is backed by a typed observation carrying its source, its date, and its
derivation (direct quote vs. inference), rather than today's plain evidence strings
(`app/models/evidence.py`'s `source_type`/`verified` fields exist on the model but are, in
practice, never populated by the extraction prompt — confirmed in this session's own prior
Phase 3 audit of the same gap).

### 5.2 Source-kind taxonomy

Adopt, explicitly, five source kinds — company disclosure (pitch deck, website, investor
update), independent reporting (press, analyst coverage), public filings (where applicable —
rare for private companies, but real for Growth-stage/public comparables), directly observable
product information (a reviewer's or the pipeline's own observation of the live product), and
inference (the AI's own conclusion from indirect signals, carrying no independent source at
all). **A URL is never, by itself, evidence of independent verification** — the existing gap
this audit confirms (Part 1.5's evidence-transparency finding from this session's own prior
Phase 3 work): today's evidence items are shown "as-is, regardless of which [kind] it was." This
new taxonomy is the structural fix that specific finding's own "smallest next step"
recommendation pointed toward.

### 5.3 Freshness, corroboration, contradiction, citation

- **Freshness:** adopt `app/ai/sps_v3_engine/freshness.py`'s existing design (already built) —
  an observation's age relative to the dimension it backs determines whether it is still
  admissible, with faster-moving dimensions (e.g., current headcount) requiring fresher evidence
  than slower-moving ones (e.g., founder background).
- **Corroboration:** a claim backed by two independent source kinds is treated as stronger
  evidence for Confidence purposes than the same claim from one source repeated (e.g., a company
  blog post and an independent press article both stating the same funding round) — this is the
  Evidence Independence Metadata concept (Part 1.4) already built, generalized from "detecting
  duplication" to "crediting genuine corroboration," a small extension of existing code rather
  than new machinery.
- **Contradiction:** the existing `CONFLICTING_EVIDENCE_*` states (5.4 above), unchanged.
- **Citation requirements:** every `CanonicalObservation` backing a scored (non-`Unavailable`)
  dimension must carry a specific source reference sufficient for a human reviewer to locate it
  — a URL when one exists, otherwise an explicit label ("company-provided pitch deck," "AI
  inference from combined signals") rather than an implied citation. This directly satisfies the
  task's "never treat a source as independently verified merely because a URL exists" — the
  presence of a URL establishes *locatability*, not *independence* or *accuracy*, and the two
  must be visibly distinct fields, never collapsed into one "source" badge as today's UI does.

---

## Part 6 — Calibration and Evaluation

### 6.1 Do not replace the existing V3 calibration program — extend it

A 31-company roster already exists, sourced and substituted for realism, split into
training/holdout, spanning Pre-Seed through Growth and including deliberately distressed/failed
companies (Convoy, Olive AI, Katerra, Quibi, Bird) precisely so the methodology is tested against
real decline and failure, not only success (`docs/validation/SPS_V3_CALIBRATION_DATASET.md`). A
leakage register, a P0 grid-search calibration pass, holdout evaluation, sensitivity analysis,
and synthetic-suite tests have already been run against it. Discarding this and building a new
dataset from scratch would be wasted, already-validated work.

**Proposed addition, per the task's explicit instruction:** add Notion, Stripe, and Linear as
three new named regression cases to the existing roster (confirmed, by checking the roster
directly, that none of the three currently appears in it), following the roster's own
established design conventions — training/holdout split, stage/sector tagging, a documented
strength-profile hypothesis — rather than a separate, parallel dataset.

**Per the task's explicit instruction, no target scores are assigned by brand recognition.**
For each of the three, and for the several additional less-established companies this addition
should include per the task's own instruction (to avoid the dataset being dominated by famous
names), the specification records only:

- **Documented facts the methodology must recognize** — e.g., for a company with publicly
  reported revenue scale and no disclosed growth history, the methodology must recognize Current
  Scale as scorable and Growth Trajectory as correctly `Unavailable`, not force one dimension to
  stand in for the other.
- **Evidence gaps it must preserve** — e.g., for a company with no public unit-economics
  disclosure, Unit Economics/Capital Efficiency must render `Unavailable`/withheld, never
  inferred from adjacent public signals (round size, headcount) in a way that could fabricate a
  number `evidence_provenance.py`'s existing guard would otherwise have caught if the LLM had
  stated it directly.
- **Invalid conclusions it must avoid** — e.g., the methodology must not conclude "poor
  Financial & Funding Signals" from an absence of disclosure alone (this is precisely the
  bug under audit), and must not let brand familiarity substitute for checkable evidence in any
  dimension (an explicit test: does the pipeline produce a materially different Founder-Market
  Fit score for the same underlying evidence when the company name is well-known versus
  anonymized — a fabrication/bias check, not a target-score check).

### 6.2 New tests this proposal adds, beyond the existing V3 program

Building on, not replacing, the existing sensitivity-analysis and synthetic-validation work
already done for V3:

- **Score stability:** identical evidence run twice through the full pipeline must produce
  identical Power/Coverage/Confidence at every level (already a stated Non-Negotiable Principle
  in the V3 design; this proposal adds it as an explicit, automated regression test rather than
  a design principle alone).
- **Evidence removal:** incrementally removing one scored dimension's evidence at a time from a
  calibration company must move that pillar's Coverage down monotonically and must never
  increase Strength (the existing "adding evidence must not automatically increase SPS"
  corollary, tested in the removal direction specifically, which the existing program does not
  yet appear to test explicitly).
- **Contradictory sources:** feeding two sources that disagree on the same fact (e.g., two
  different disclosed revenue figures) must route to `CONFLICTING_EVIDENCE_UNRESOLVED` (excluded
  from scoring) rather than silently preferring one source over the other.
- **Missing data:** a company with genuinely sparse public evidence (most dimensions
  `Unavailable`) must produce a withheld pillar/overall score with an honest reason, never a
  number, regardless of how the few scored dimensions happen to look.
- **Stage sensitivity:** the same underlying evidence, relabeled to a different stage, must
  produce a different score where the rubric says it should (an early "no revenue yet" signal
  should score materially differently at Pre-Seed vs. Series B+) and must not change at all in
  dimensions the redesigned rubric marks stage-invariant.
- **Resistance to fabricated company claims:** evidence containing an unverifiable, self-serving
  claim with no independent corroboration (e.g., a pitch deck asserting "hockey-stick growth"
  with no dated figures) must not move Growth Trajectory or Current Scale, since both remain
  Deterministic and fail-closed without a real dated series — this test exists to catch a
  regression that would defeat the entire fail-closed design, not to discover a new failure mode.

---

## Part 7 — Migration and Implementation Impact

### 7.1 Affected modules (for the future implementation phase, not touched by this document)

| Area | Files |
|---|---|
| Dimension definitions/weights | `app/ai/scoring_methodology.py` (legacy), `app/ai/sps_v3_engine/evaluators.py` (V3 — Financial & Funding Signals' new Funding Signals dimension needs adding here) |
| Evidence classification adapter | `app/ai/sps_v3_adapter.py::classify_evidence_for_v3` (the actual gap — needs Financial Health + 4 Traction dimensions built) |
| Aggregation/publishability | `app/ai/sps_v3_engine/aggregation.py` (mostly reusable as-is; new withholding-reason surfacing per Part 3 item 3) |
| Stage determination | `app/ai/sps_v3_adapter.py::map_stage` (add the `Uncertain` state, Part 4.1) |
| Evidence provenance model | `app/models/evidence.py`, `app/ai/evidence_provenance.py`, new source-kind taxonomy (Part 5) |
| API contracts | `app/models/sps_v3.py` (the eventual canonical replacement for `startup_intelligence_score`/`InvestmentScore`), `app/api.py` response models |
| Persistence | `analyses.methodology` JSONB column — no schema change needed if the new canonical result is added the same way `sps_v3` was (additive JSONB field, Phase 10.9's own precedent) |
| Frontend | `dashboard/components/startup/*` (score ring, Key Risks, pillar workspace — all already built to read `evidence_status`/coverage/confidence-shaped data from this session's own Task 7 Phase 3 work, which should transfer with moderate changes rather than a rewrite) |
| Rankings/Compare/Saved/history | Per `SPS_V3_CANONICAL_ACTIVATION.md`'s own already-made, still-valid decisions: Rankings/Saved/history stay on the legacy field for compatibility until a ranking design that tolerates a nullable score exists; Compare already handles a withheld state correctly |
| Calibration | `app/calibration/expected_scores.py` (legacy harness — currently only has `stripe_series_a`; needs the redesigned pillar weights reflected once implemented), `docs/validation/SPS_V3_CALIBRATION_DATASET.md` (extend per Part 6) |

### 7.2 Versioning proposal

Given the three already-taken identifiers in Part 1.6, this proposal recommends a new,
unambiguous version string for the result of this work — **not** "v2" (taken by legacy) and
**not** a bare "v3" bump (taken by the existing, differently-scoped SPS V3 identifier). Two
options are presented for approval rather than decided unilaterally here:

- **Option A:** `venturegps.methodology.v1` — a deliberately new namespace, signaling that this
  is the first version under a new, explicit naming convention going forward, sidestepping the
  legacy `v2.1`/`v3` numbers entirely.
- **Option B:** `sps_v3.11_0` (or similar) — treat this work as the continuation and completion
  of the already-existing SPS V3 program (finishing its adapter, adding the one new dimension
  and the one new stage state this audit proposes) rather than a new methodology name, since the
  overwhelming majority of the substance is SPS V3's own design, completed.

This audit's own recommendation is **Option B** — it accurately represents that this is
completing existing, already-partially-calibrated work, not starting over — but the decision
affects how every future document, log line, and stored record refers to this methodology and
should be made explicitly, not inferred from this document's own filename.

Existing scores remain associated with their original methodology version exactly as today's
architecture already guarantees: `methodology_version`/`sps_v3.engine_version` are stamped
per-analysis at creation time and never rewritten; a newly-canonical version is never silently
compared against or backfilled onto historical scores (unchanged from the existing, already-
correct precedent in `SPS_V3_CANONICAL_ACTIVATION.md` §2).

### 7.3 Recommended smallest safe implementation sequence

1. **Finish the SPS V3 adapter** for Financial Health's three (soon four, with Funding Signals)
   dimensions and Traction's four currently-unpopulated dimensions. This is the one piece of
   genuinely new code required; everything else in Parts 2-5 either already exists in the V3
   engine or is a small, additive extension of it (the new Funding Signals dimension, the
   `Uncertain` stage state, the corroboration extension to Evidence Independence Metadata).
2. **Add the Funding Signals dimension and the renamed "Financial & Funding Signals" pillar
   label** to `evaluators.py`, alongside the adapter work in step 1 (they touch the same files
   and should land together).
3. **Extend the calibration roster** (Part 6.1) and re-run the existing P0/holdout calibration
   process against the completed adapter — the existing process does not need to be redesigned,
   only re-executed now that Financial Health and Traction actually receive evidence.
4. **Only after calibration confirms the completed adapter behaves as designed** against the
   extended roster: flip `sps_v3_enabled()`'s default back on (the mechanism already exists,
   unchanged, from the prior canonical-activation work), this time with Financial Health and
   Traction actually populated, so the product's default experience is `sufficient`/`limited`
   for a normal company rather than routinely `insufficient`.
5. **Retire the legacy renormalize-blindly aggregation** (`calculate_weighted_score`/
   `calculate_base_score`) as the *primary* number the product shows, once step 4 is confirmed
   safe — keeping the legacy fields populated in the background for historical continuity and
   rollback exactly as `SPS_V3_CANONICAL_ACTIVATION.md`'s own already-proven rollback mechanism
   (`SPS_ENGINE_VERSION=v2_1`) already allows, rather than deleting legacy code.

This sequence deliberately does not touch Market/Team/Product/Execution's dimension
definitions, does not require a database migration (the additive-JSONB pattern already proven
for `sps_v3` extends cleanly), and does not require re-scoring any historical analysis.

---

## Part 8 — Consequential Decisions and Open Questions Requiring Approval

1. **Naming (Part 7.2):** should the completed methodology be called `venturegps.methodology.v1`
   (a clean break from legacy numbering) or a continuation of the SPS V3 identifier (e.g.
   `sps_v3.11_0`)? This audit recommends the latter but treats it as the user's call, since it
   affects every future reference to this work.
2. **Financial & Funding Signals rename (Part 2.6):** approved for this proposal to proceed on,
   but is a user-facing product-copy change (every place "Financial Health" appears today) and
   should be explicitly confirmed rather than assumed bundled into a scoring-methodology
   approval.
3. **The new Funding Signals dimension (Part 2.6):** genuinely new (not in the existing SPS V3
   design), needs its own weight decided in calibration (Part 6) rather than the provisional
   0.10 stated here, and needs confirmation that "publicly disclosed funding facts" is an
   acceptable pillar contribution distinct from the financial-health question the pillar's old
   name implied.
4. **Exact coverage-floor numbers (Part 3):** deliberately left as "to be set in calibration,"
   not asserted in this document, consistent with this codebase's own established practice of
   never inventing a threshold the calibration program hasn't produced (Part 1.4's own
   "CALIBRATION_ANCHOR_REQUIRED" convention). Needs sign-off that calibration, not this document,
   is where these numbers will be decided.
5. **Sequencing (Part 7.3):** confirms the recommended order is "finish the adapter, then
   calibrate, then flip the default, then retire legacy as primary" rather than a faster path —
   approval needed that this pace (versus, e.g., shipping the adapter completion and immediately
   making it canonical without a fresh calibration pass) matches risk tolerance.
6. **Rankings/Compare/Saved-startups/score-history** remain on the legacy field even after this
   work, per `SPS_V3_CANONICAL_ACTIVATION.md`'s own already-made decision (Part 7.1) — this
   document does not revisit that decision, but flags that it means those four surfaces will
   keep showing the renormalize-blindly-computed legacy number even after the Startup Profile
   view shows the corrected one, until a separate, explicitly-scoped future phase addresses it.
