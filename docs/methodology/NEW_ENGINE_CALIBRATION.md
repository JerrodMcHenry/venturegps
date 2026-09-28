# VentureGPS Evidence Engine — Calibration Plan

**Status: STILL THE PLAN for a real, large-cohort calibration.** No parameter here has been set
from a real calibration run. Task 9 ran a first, honest calibration *exercise* — not this plan —
against an expanded 5-company offline fixture roster (Notion, Linear, and three fictional
companies designed to stress specific mechanisms); Task 10 closed two engineering gaps that
exercise found (evidence-independence verification, classification recovery) and reviewed the
stage-tiered tables' own rationale without changing any value. See
`docs/methodology/NEW_ENGINE_CALIBRATION_REPORT.md` (Parts 1-9 for Task 9, Part 10 for Task 10)
for what these passes actually found and what they explicitly could not validate (offline
fixtures are not a cohort). All seven acceptance tests in Part 4 below are now implemented as
real, passing offline tests, spanning 7 files and 77 tests total — including 4.7
(identity-blindness), a prompt-injection test, and dedicated provenance/recovery/boundary suites
beyond what this plan originally specified. This document remains the real plan for eventually
setting the numbers themselves against the much larger cohort in Part 2.

**Task 19 update:** after all six pillars were assembled (Task 18), a sensitivity-analysis pass was
run against the resulting 7-company cohort (`docs/methodology/NEW_ENGINE_CALIBRATION_RESULTS.md`) —
publication-gate behavior across the pillar-level 35-50% coverage range, and a controlled-fixture
investigation of Confidence's Low/Medium/High boundaries. **This is still not the large-cohort
calibration plan below** — it is a smaller, evidence-conditions-focused pass (per that task's own
explicit "do not build a massive benchmarking project" instruction), and it changed no pillar-level
parameter (the sensitivity evidence did not justify a change to any of them). It did add one new,
narrow layer: company-level Coverage/Confidence/publishability (spec Part 6.5, now partially
implemented) using `PILLAR_WEIGHTS` taken directly from this document's own Part 3.3 header rows —
still exactly as provisional as everything else here. An overall 0-100 Strength was evaluated and
explicitly NOT adopted (`NEW_ENGINE_CALIBRATION_RESULTS.md` §8) — the real, large-cohort calibration
plan below remains the actual path to validating `PILLAR_WEIGHTS` (and every other number in this
document) before that decision would be revisited.

Companion documents: `docs/methodology/NEW_ENGINE_SPEC.md` (the methodology this calibrates)
and `docs/architecture/NEW_ENGINE_ARCHITECTURE.md` (the system this runs against).

---

## Part 1 — What Calibration Is For, and What It Is Not For

Calibration exists to set the numeric parameters the spec explicitly refuses to invent (Part
6.7 of the spec: every pillar/dimension weight, every coverage/dimension-count gate, every
Computed-dimension band table, every Classified-dimension stage-indexed label-to-score table,
Confidence's input weighting). **It does not exist to make any specific company's score come
out a particular way.** Per the task's own explicit instruction, no company in this plan —
recognizable or not — has a predetermined target score anywhere in this document. What each
calibration case defines instead, consistently, is: which **facts** the engine must correctly
recognize as evidence, which **gaps** it must honestly preserve rather than fill in, and which
**conclusions would be invalid** if the engine reached them. A parameter set that produces
scores consistent with those three things, across the full cohort, is an acceptable
calibration; a parameter set that happens to rank one famous company highly is not evidence of
anything by itself.

---

## Part 2 — Calibration Cohort Design

### 2.1 Roster composition principles

- **Spans all stages** the spec's Stage-Aware Evaluation (spec Part 4) defines: Idea, Pre-Seed,
  Seed, Series A, Series B+, Growth — plus at least one company whose stage is deliberately
  ambiguous from public evidence alone, to exercise `Stage: Undetermined` (spec Part 4.3)
  directly.
- **Includes real failure and decline cases**, not only success stories — a methodology
  calibrated only on companies that went well cannot be trusted to score companies that did not.
- **Is dominated by less-recognizable companies, not by the three named regression cases.** Per
  the task's explicit instruction, Notion/Stripe/Linear are three specific, named regression
  cases among a larger roster, not the roster's center of gravity.
- **A training/holdout split** (mirroring the sound methodology already established in this
  codebase's prior calibration work, `docs/validation/SPS_V3_CALIBRATION_DATASET.md` — reused
  as a *process* pattern, not as a source of this engine's own roster or numbers): parameters are
  set against the training split only; the holdout split is evaluated once, after parameters are
  frozen, and is not used to further tune anything — a look at holdout results that leads to
  re-tuning is itself a calibration-process failure, not a legitimate refinement.
- **A leakage register**, tracking, per company, whatever the calibrating engineer already knows
  about that company's real-world outcome or reputation before evidence is gathered — the same
  discipline this codebase's prior calibration work already established as necessary (a person
  calibrating a "is this company strong" system who already knows Notion is a well-regarded
  company is exactly the bias Design Principle 10 exists to prevent, and the register makes that
  prior knowledge visible and checkable rather than silently laundered into a threshold choice).

### 2.2 Roster

**Named regression cases (per explicit instruction):**

| Company | Stage (hypothesis) | Why included |
|---|---|---|
| Notion Labs | Growth | Well-documented product-led SaaS company with substantial public reporting on user counts, funding history, and product evolution — a strong test of whether Commercial Traction and Product & Technology can be assessed richly from public evidence alone, and of whether Capital Efficiency correctly stays `Unscored` absent voluntary disclosure of margin/burn. |
| Stripe | Growth/late-stage private | Extensively publicly documented funding history, named enterprise customers, and named executive team — a strong test of Team & Leadership and Financial & Funding Signals' Funding History dimension, and a check that Capital Efficiency does not get inferred from Stripe's scale or funding size (the exact invalid conclusion the spec explicitly forbids). |
| Linear | Series B/C-ish | Smaller, more recent public disclosure footprint than the other two — a useful contrast case testing whether the engine correctly produces a more moderate Evidence Coverage than Notion/Stripe (a *real* difference in public disclosure volume, not a real difference the engine should read as a real difference in company quality) rather than forcing a similarly rich profile onto a company with a genuinely thinner public footprint. |

**Additional cohort (illustrative roles; exact company selection to be finalized against
verifiable, current sources at execution time — following this codebase's own established,
sound practice of live-reverifying a roster immediately before use, since company status
changes, per the prior V3 calibration program's own documented experience of needing
last-minute substitutions when a roster company was acquired or shut down between roster design
and execution):**

| Role in cohort | Stage | Strength-profile hypothesis | Split |
|---|---|---|---|
| A current accelerator-batch company (sourced at execution time) | Pre-Seed | Sparse-but-real evidence; tests whether thin coverage is honestly withheld rather than forced into a number | Training |
| A second current accelerator-batch company, different sector | Idea/Pre-Seed | Near-zero disclosed facts beyond a public landing page | Holdout |
| A Series A company in a B2B SaaS category with real but unglamorous public evidence | Series A | "Ordinary for stage," not exceptional — tests mid-band behavior | Training |
| A Series B company with strong, well-corroborated public commercial evidence (named enterprise logos, independently reported growth) | Series B | Evidence-rich, strong candidate | Training |
| A Series B/C company whose public evidence is real but comes almost entirely from one corroboration group (a single funding announcement restated widely) | Series B/C | Tests the independence-group deduplication rule (spec Part 2.3) directly — must not read as heavily corroborated | Holdout |
| A growth-stage company with real, disclosed, publicly documented 2022-2023 operational struggles (layoffs, leadership departures) | Growth | Tests that demonstrated weakness is scored as weakness, distinctly from thin evidence | Training |
| A profitable, capital-efficient, bootstrapped company with minimal fundraising disclosure | Growth | Tests that a company with genuinely low Funding History evidence (because it mostly didn't raise, not because evidence is missing) is not penalized as if evidence were missing — a real, important distinction the spec's dimension design (Funding History is about disclosed rounds, not about "is the company well-capitalized") must get right | Training |
| A real, publicly documented shut-down/failed company | Growth (defunct) | Tests that genuine, disclosed decline/failure evidence correctly drives Strength down, and that Execution & Momentum's Strategic Consistency dimension correctly detects a real, documented contradiction between the company's own earlier public statements and its later disclosed struggles | Training |
| A second real, publicly documented shut-down/failed company, different sector | Growth (defunct) | Same purpose, sector diversity | Holdout |
| A company whose public stage signal is genuinely ambiguous (no disclosed round, ambiguous age/scale signals) | Deliberately ambiguous | The direct test case for `Stage: Undetermined` (spec Part 4.1, 4.3) | Training |
| A historical, as-of-a-past-date snapshot case (assessed using only evidence that would have existed as of a stated past date) | Growth, historical AS-OF | Tests that the engine's historical/as-of-date handling (Part 2.3 below) does not leak future knowledge into a past assessment | Training |

This yields a cohort in the same size range as this codebase's prior, proven calibration
program (low-to-mid-30s companies once the accelerator/current-batch slots are filled at
execution time) without asserting a fixed final count here, since two roles are deliberately
left to be filled with real, currently-verifiable companies at execution time rather than named
now and risking staleness before calibration actually runs (the same, explicitly-learned lesson
from this codebase's prior calibration program, which had to substitute two roster companies
after they were acquired/shut down between design and execution).

### 2.3 Historical/as-of-date methodology

The historical snapshot case requires the research step to be constrained to sources dated on
or before the stated as-of date — implemented as a hard filter on `published_at`/`retrieved_at`
in the Evidence Ledger (spec Part 2.1) at research time, not a prompt instruction to "ignore
later information" (which both prior engines' own failure analysis suggests is exactly the kind
of instruction an LLM applies inconsistently). This is the one calibration case that doubles as
an architecture test: it only works if the Research step (architecture doc Part 2.1) can
actually honor a date cutoff mechanically.

---

## Part 3 — Documented Facts, Preserved Gaps, and Invalid Conclusions (per named regression case)

For each named case, this section states only the category of fact/gap/invalid-conclusion the
engine must get right — not a target score, and not, for the additional cohort, specific
real-world figures that would need independent verification closer to execution time (per the
same "reverify immediately before use" discipline as the roster itself).

### 3.1 Notion Labs

- **Documented facts the engine must recognize:** a real, named, dated funding history exists in
  independent press coverage (Funding History, Computed, must not be `Unscored` for lack of
  trying — evidence genuinely exists here); the product is a directly observable, long-running,
  actively maintained artifact (Product Existence & Maturity); the company has a substantial
  public footprint of named customers/use-case case studies (Customer Base Breadth).
- **Unavailable information the engine must not invent:** current, specific unit economics
  (margin, burn, runway) are not, to public knowledge, routinely disclosed in a form this
  engine's Capital Efficiency dimension would accept — the engine must leave this `Unscored`
  rather than inferring a plausible-sounding figure from the company's scale or funding history.
- **Failure conditions to avoid:** treating the *absence* of a recent, specific revenue or
  margin disclosure as evidence of weak Financial & Funding Signals (the exact defect that
  motivated this entire task); letting Product & Technology's dimensions read as uniformly
  maximal purely because the company is well-known, rather than because each dimension's own
  specific evidence bar (spec Part 3.3) is independently met.

### 3.2 Stripe

- **Documented facts the engine must recognize:** an extensive, independently reported funding
  history with named investors and disclosed valuations across multiple rounds (Funding
  History); named enterprise customers and integration partners are independently reported, not
  merely self-claimed (Technical Depth Signal, Commercial Validation); a large, named executive
  team is publicly documented (Leadership Composition).
- **Unavailable information the engine must not invent:** as a long-private company, specific
  disclosed revenue or margin figures are inconsistently and incompletely available in public
  reporting; the engine must reflect exactly what is independently reported, not extrapolate a
  precise current figure from older disclosures or from funding size.
- **Failure conditions to avoid:** the specific, explicitly named invalid conclusion from the
  task instructions — inferring profitability, burn rate, runway, or retention from Stripe's
  large disclosed funding rounds or its general market presence. This is the single most
  important test case for that specific instruction, precisely because Stripe's funding
  disclosures are large and numerous enough that an insufficiently guarded Capital Efficiency
  dimension would be most tempted to "round up" from them.

### 3.3 Linear

- **Documented facts the engine must recognize:** a real, smaller, but genuine public disclosure
  footprint — named funding rounds, a product with independent reviews and press coverage,
  named integrations.
- **Unavailable information the engine must not invent:** Linear's public footprint is real but
  genuinely thinner than Notion's or Stripe's across most dimensions — the engine must reflect a
  correspondingly lower Evidence Coverage, not manufacture equivalent richness.
- **Failure conditions to avoid:** two, in opposite directions — (a) reading Linear's smaller
  disclosure footprint as evidence of weaker performance (a coverage difference is not a
  performance difference, the core distinction Design Principle 5 exists to enforce), and (b)
  overcorrecting by treating recognizability/reputation as a substitute for Linear's own actual,
  checkable evidence (the identity-blindness principle, Design Principle 10, cuts against boosting
  a well-regarded but evidence-thinner company just as much as it cuts against boosting a
  famous one).

---

## Part 4 — Acceptance Tests

All of the following are pass/fail acceptance tests the finished implementation must pass
before this methodology can be considered calibrated, independent of the specific numeric
parameter values chosen (which are the *output* of running these tests against the cohort, not
asserted here):

### 4.1 Fabricated claims

Feed the pipeline a company profile containing at least one specific, self-serving, checkable-
sounding claim with no independent corroboration and no verbatim excerpt possible (e.g., a
pitch-deck-style assertion of a precise growth or margin figure with no source backing it in the
supplied research). **Required outcome:** the claim either fails to enter the ledger as a
scorable claim at all (no admissible `source`/`excerpt`) or, if it is a `company_disclosure`
claim retained per spec Part 2.3, it must not move any dimension whose rubric (spec Part 3.3)
requires independent corroboration — most pointedly, Retention/Renewal Signal and Capital
Efficiency must remain `Unscored` under a fabricated or uncorroborated figure, exactly as they
would under a genuinely absent one.

### 4.2 Contradictory sources

Feed the pipeline two sources disclosing different figures for the same metric and reporting
period, with no clear source-type or recency precedence (spec Part 2.3's tie-break rules).
**Required outcome:** both claims are marked `disputed`, linked via `contradicts`, and excluded
from scoring — the dimension they would have backed is `Unscored`, never resolved by picking
whichever number is more flattering or more recent when recency does not actually apply (two
different reporting periods, as spec Part 2.3 specifies, must not be treated as if they
conflict at all).

### 4.3 Stale information

Feed the pipeline evidence for a dimension that is older than that dimension's own staleness
bound (spec Part 3.3's per-dimension `Staleness bound` column). **Required outcome:** the claim
is retained in the ledger (visible in a `get_claims` call, architecture Part 4.3) but excluded
from scoring, and the dimension is `Unscored` with a `stale` reason distinct from `no_evidence`
(architecture Part 7) — the two must be distinguishable in the persisted record, not merged into
one generic "insufficient" label.

### 4.4 Missing evidence

Feed the pipeline a company profile with genuinely minimal public evidence across most
dimensions (mirroring the roster's own sparse-evidence Pre-Seed/Idea cohort members, 2.2).
**Required outcome:** the affected pillars are withheld per the two-gate rule (spec Part 6.2),
the overall score is withheld per its own gates (spec Part 6.5) if enough pillars are affected,
and — critically — the report still surfaces whatever pillars/dimensions *are* scorable, never
collapsing to an empty result (spec Design Principle 9, architecture Part 6).

### 4.5 Score stability

Run the identical evidence (same ledger, same Assessment output — not a fresh research pass,
which would reintroduce ordinary LLM run-to-run variance in a way this specific test is not
designed to measure) through Deterministic Scoring (spec Part 6) twice. **Required outcome:**
bit-for-bit identical Strength/Coverage/Confidence at every level, both times — this is the one
test that must be perfectly deterministic by construction, since Scoring contains no AI call and
no randomness; any variance here is a real implementation bug, not measurement noise.

### 4.6 Stage sensitivity

Take one calibration company's assessed evidence and re-run Scoring with its `stage` field
manually overridden to a different value. **Required outcome:** every stage-indexed Classified
dimension (spec Part 3.3, Part 4.2) produces a different score where the per-stage table says it
should (e.g., the same `Founder Relevant Experience: DIRECT` label scoring differently at
Pre-Seed vs. Growth, per spec Part 4.2's own worked example) and produces the *same* score for
any dimension the table does not differentiate by stage — confirming the stage-indexed lookup
table is actually being read, not silently ignored.

### 4.7 Identity-blindness (per Design Principle 10, in addition to the task's explicitly listed test types)

Run the same underlying evidence/claims through the Classified-dimension calls twice: once
naturally (with the real company name reachable during research, as normal) and once with the
company's name and obviously identifying brand terms redacted from the classification call's own
input (spec Part 5.3). **Required outcome:** identical labels both times, for every Classified
dimension. A difference indicates the classification call is leaking on brand recognition rather
than evidence content, and is treated as a blocking defect, not a calibration-tuning matter.

---

## Part 5 — What This Calibration Plan Deliberately Does Not Do

- It does not set any final parameter value (spec Part 6.7's full list remains open pending
  actual execution against the cohort).
- It does not run any paid AI call, per this phase's explicit constraint — every test in Part 4
  is specified as a test the eventual implementation must pass, not a result already obtained.
- It does not finalize the exact additional-cohort company list — two roles are deliberately
  left to be sourced from current, live-verifiable companies at execution time, following this
  codebase's own prior, hard-learned lesson that a roster designed too far in advance of
  execution risks including a company that has since been acquired or shut down.
- It does not compare this engine's eventual output to the legacy or V3 engine's historical
  scores for the same companies — per the spec's explicit instruction not to inherit or be
  anchored to either prior methodology, a difference from a legacy score is not, by itself,
  evidence of anything in either direction.
