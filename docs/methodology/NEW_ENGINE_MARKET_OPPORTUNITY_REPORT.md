# VentureGPS Evidence Engine — Market Opportunity Pillar (Task 13)

**Status: implemented and tested — the second production-quality pillar in `app/evidence_engine/`,
built on the exact architecture Product & Technology validated (Tasks 8-12). No shared scoring
philosophy, evidence ledger, classification system, provenance system, confidence model, stage
model, or publication gate was redesigned.** This document does not rewrite
`NEW_ENGINE_LIVE_EVALUATION.md` or `NEW_ENGINE_REMEDIATION_REPORT.md` (Product & Technology's own
historical reports, both untouched by this task).

## 1. Implemented dimensions (spec Part 3.3, unmodified)

All four dimensions from the approved specification, exactly as weighted and staleness-bound
there — no dimension invented, renamed, or dropped:

| Dimension | Weight | Category | Staleness | Admissible evidence (spec) |
|---|---|---|---|---|
| Market Definition & Size | 0.30 | Classified | 24 months | Named customer segment + independently-published market-size figures |
| Market Growth Signal | 0.25 | Classified | 18 months | Independently-published category growth-rate reporting |
| Timing & Catalyst | 0.20 | Classified | 24 months | A named, dated external catalyst, independently reported |
| Competitive Landscape Position | 0.25 | Classified | 18 months | Named competitors + an independently-sourced comparison |

**All four are Classified — no Computed dimension exists for this pillar**, matching the spec's
own table exactly (unlike Product & Technology, which has one Computed dimension).

### 1.1 Closed label sets (a documented, narrow interpretation — the spec itself gives no exact
enum, exactly as was true for Product & Technology's own dimensions in Task 8)

- **Market Definition & Size:** `NOT_DISCLOSED` (Unscored) / `NARROW` (<$1B) / `SUBSTANTIAL`
  ($1B-$10B) / `LARGE` (>$10B).
- **Market Growth Signal:** `NOT_DISCLOSED` (Unscored) / `SLOW` (<10%/yr) / `MODERATE` (10-25%) /
  `FAST` (>25%).
- **Timing & Catalyst:** `NONE_DISCLOSED` (Unscored) / `GENERIC_ONLY` (Unscored — an independent
  claim exists but names no specific catalyst, e.g. "fast-growing industry") / `SPECIFIC_CATALYST`.
- **Competitive Landscape Position:** `NOT_ESTABLISHED` (Unscored) / `FRAGMENTED` / `CONCENTRATED`
  — a read on the market's own structure, never a company-vs-competitor differentiation judgment.

**Why bands, not a raw number:** Design Principle 6 forbids any dimension letting the AI emit a
number directly. A band is a closed, finite label set — structurally a classification, not a
number — with deterministic code owning the label→score mapping and the band cutoffs
(`parameters.py`). This is the narrowest reasonable reading of a "Classified" dimension whose own
approved rubric is explicitly about magnitude.

### 1.2 Every scoring label requires independent evidence (spec's own "Minimum to score" column)

Unlike Product & Technology (where only some labels needed `requires_independent_source`), **every
real label in every Market Opportunity dimension requires it** — directly implementing the spec's
own "independently-published"/"independent-reporting"/"independent (not self-authored)" language
for all four dimensions, and Task 13 item 4's explicit instruction to treat "$50B market," "huge
opportunity," etc. as claims requiring evidence. A company's own TAM slide or growth claim is
never deleted from the ledger (full auditability preserved) but can never, alone, satisfy any
dimension's minimum-to-score bar.

## 2. Pillar boundary (item 3) — enforced mechanically, not by convention

Preserved exactly as instructed: customer/revenue adoption stays out of this pillar entirely
(belongs to Commercial Traction, not yet built); Competitive Landscape Position asks about market
*structure* (fragmented/concentrated), never whether this company's own product is better than a
competitor's (that remains Product & Technology's Differentiation Claim Corroboration). The
mechanism enforcing this is the same one that already enforces every other pillar boundary in this
engine: `assessment_criteria` tagging. A claim never scores a dimension it wasn't tagged for —
confirmed directly by `test_traction_style_evidence_tagged_for_a_different_dimension_does_not_leak_in`
and `test_differentiation_style_evidence_does_not_score_competitive_landscape`
(`test_market_opportunity.py`).

## 3. Stage independence (item 6) — the required documented reasoning

**Every Market Opportunity label→score table is a flat `dict[str, float]`, never stage-indexed —
deliberate, not an oversight.** Product & Technology's dimensions are stage-VARYING because they
measure something about the assessed company relative to its stage (the same evidence is more
remarkable, and scores higher, for a younger company). Market Opportunity measures a property of
the external market: a real $10B category or a named regulatory catalyst means the same thing
regardless of which company's report happens to cite it, and Task 13 item 6 explicitly forbids
giving younger companies an easier market score merely for being younger. `evaluate_pillar_for_
company()` still accepts a `stage` parameter, purely for calling-convention consistency with
Product & Technology (so a future orchestrator can call every pillar with one shared
`determine_stage()` result without special-casing this one) — it is accepted and never consulted,
documented in `market_opportunity.py`'s own module docstring per item 6's explicit instruction.

## 4. Shared-engine change (item 9) — one, additive, documented here in full

**`classification.py::EvidenceItem` gained one new field, `structured_fact: dict[str, str] |
None = None`, propagated in `to_evidence_items()` from `Claim.structured_fact` (which has existed
since Task 9 for stage-signal claims).** This is not a fix for a defect — Product & Technology's
four dimensions never needed it and are entirely unaffected (all still decide their label from
`source_type`/`independence_group_id` alone, confirmed by the full, unchanged Product & Technology
test suite passing identically). It closes a real gap in how completely the engine's existing
typed-fact concept (`Claim.structured_fact`) was threaded through to the classification interface:
Market Opportunity's own approved rubric requires magnitude-bearing dimensions (a market-size
figure, a growth-rate percentage) that a Classified dimension's classifier has no other
deterministic way to bucket into a closed band without either (a) real NLP a mock cannot perform,
or (b) under-implementing the spec's own explicit "market-size/report figures" evidence
requirement. Extending an already-existing, already-generic field through an already-generic
interface is judged the narrower change versus inventing a second, parallel typed-fact mechanism
specific to this one pillar.

## 5. Test results

**23 new tests, `test_market_opportunity.py`, all passing** — covering strong/sparse/completely-
missing evidence, stale evidence, disputed evidence, non-disputed contradictory sources (the
documented "first admissible candidate, in stable order" convention, unchanged from the rest of
the engine), duplicated/syndicated market reports, company self-reported TAM (alone, and alongside
a real independent source), generic hype-language rejection, unsupported "no competitors"-style
claims, two dedicated pillar-boundary tests, fabricated-citation and invalid-label rejection,
prompt-injection resistance (including an injection-*compliant* mock model, still blocked by
evidence-sufficiency validation), classification recovery, the shared coverage and count gates
(plus a Market-Opportunity-specific structural finding — §6 below), deterministic reproducibility,
full traceability, and graceful withholding under a crashing model.

**Full regression: 118 tests across 11 files, all passing** (95 prior + 23 new). Legacy regression
(`test_pipeline_concurrency.py` 14/14, `test_methodology_v2_1.py` 21/21) and isolation boundary
(zero imports outside `app.evidence_engine`) both reconfirmed. Product & Technology's own Task
11/12 live-evaluation results were re-run and reproduce byte-for-byte identically after this
pillar's addition (the new Market-Opportunity-tagged claims added to `live_research/notion.py`/
`linear.py` are invisible to Product & Technology's evaluators, which only ever read claims tagged
with their own dimension keys).

## 6. A genuine structural finding about this pillar's own weights

No single Market Opportunity dimension can clear the shared 40% coverage floor alone (the largest,
Market Definition & Size, is 0.30). For this pillar specifically, the coverage gate alone already
blocks every single-scored-dimension case — the minimum-distinct-dimension gate is not
independently load-bearing under these real weights (it remains generically proven necessary by
Product & Technology's own synthetic test in `test_coverage_boundaries.py`, which every pillar
shares). Documented directly as `test_no_single_real_dimension_can_clear_coverage_alone_for_this_
pillar`, replacing an initially-attempted test that assumed (incorrectly, an error caught before
this report was written) a single dimension could reach the floor here the way it can for Product
& Technology.

## 7. Small real-evidence sanity check (item 8)

**Method note, identical to Tasks 11-12: research used this session's own `WebSearch`/`WebFetch`
tools, not the project's paid OpenAI/Tavily infrastructure — no paid API call was made or
required.** Reused Notion and Linear from Tasks 11-12 (their `live_research/*.py` files extended
with a small number of new, genuinely-researched, real Market-Opportunity-tagged claims — see
each file's own "Task 13 addition" section). Reproduce with `python -m app.evidence_engine.
live_research.run_market_opportunity_sanity_check`.

### 7.1 Results

| Company | Publishable | Strength | Coverage | Notes |
|---|---|---|---|---|
| Notion | Yes | 6.2 | 100% | All 4 dimensions scored from real, independent, dated sources |
| Linear | Yes | 5.88 | 80% | 3 of 4 scored; no timing-catalyst evidence was found (or sought — see §7.3), left honestly `Unscored`, never invented |

**Zero traceability violations** across all 8 real scored dimension results (directly verified,
not merely asserted).

### 7.2 Checked against item 8's own failure-mode checklist

- **Bogus TAM interpretation:** not found. Notion's real $6.56B (2023) figure correctly bucketed
  `SUBSTANTIAL`; Linear's real $1.78B (2025) figure correctly bucketed `SUBSTANTIAL`. Neither
  figure was invented or rounded up from a vaguer claim.
- **Inappropriate company-disclosure reliance:** not found. Every one of the 7 real scored
  dimension results across both companies cites only `independent_reporting` sources (Market.us,
  Gartner, Next Move Strategy Consulting) — zero company-disclosure citations among them.
- **Duplicate market reports counted as independent:** not directly stress-tested by this small,
  real dataset (each dimension had exactly one real candidate claim in this pass) — the mechanism
  itself is already proven generically (`test_duplicated_syndicated_market_report_does_not_double_
  count`); a larger real pass would be needed to exercise it against genuinely duplicated real
  reports.
- **Evidence assigned to the wrong dimension:** not found — each claim was tagged deliberately and
  singly for the one dimension it was researched for.
- **Company traction leaking into Market Opportunity:** not found — no customer/revenue/usage
  claim was added to either company's market-tagged evidence.
- **Unsupported classifications:** not found — see the zero-violations traceability check above.

### 7.3 Two genuine findings worth flagging (methodological judgment, not a code change)

- **Both companies' Competitive Landscape Position resolved `CONCENTRATED`.** From only two real
  data points this is an observation, not a conclusion — but it is worth watching: reputable market
  research reports for well-covered software categories seem to routinely name one dominant
  incumbent even when many named competitors exist (Linear's own source names ten competitors, one
  "dominant"), which may mean `CONCENTRATED` will turn out to be the structurally more common real
  outcome for any well-documented category, independent of the assessed company's actual
  competitive position. Not addressed here — a real calibration question.
- **Category-boundary ambiguity in the market-size evidence itself.** Real market-research
  coverage rarely maps 1:1 onto a specific company's actual addressable niche — Notion's cited
  $6.56B "collaboration software" figure describes a broader category dominated by Microsoft/
  Google/Zoom than Notion's own narrower workspace/notes competitive position, a real ambiguity
  this evaluation's own research encountered directly (documented as a `limitations` note on the
  claim itself) and did not attempt to resolve algorithmically.
- **This evaluation did not specifically search for a Linear timing catalyst** — its absence
  reflects this small pass's own research scope, not a claim that no such evidence exists in the
  wild (the same honest distinction Task 11 §5.4 already drew for Stripe's Technical Depth Signal).

## 8. Provisional parameters requiring future calibration

Every weight, band cutoff, and label score below is `CALIBRATION REQUIRED`, exactly like every
number in Product & Technology's own tables — none was set from real data, only reasoned to be
plausible enough to exercise the mechanism:

`MARKET_OPPORTUNITY_DIMENSION_WEIGHTS` (0.30/0.25/0.20/0.25), `MARKET_SIZE_NARROW_MAX_USD` /
`_SUBSTANTIAL_MAX_USD` ($1B/$10B cutoffs), `MARKET_SIZE_LABEL_SCORES` (4.0/6.5/8.5),
`MARKET_GROWTH_SLOW_MAX_PCT` / `_MODERATE_MAX_PCT` (10%/25% cutoffs), `MARKET_GROWTH_LABEL_SCORES`
(4.0/6.5/8.5), `TIMING_CATALYST_LABEL_SCORES` (7.5), `COMPETITIVE_LANDSCAPE_LABEL_SCORES`
(7.5/4.5). The directional interpretation behind Competitive Landscape Position (fragmented =
more opportunity than concentrated) is explicitly stated as a reasoned position, not asserted
investment doctrine — flagged, not defended as objectively correct.

## 9. Remaining limitations

- No automatic resolution for genuinely conflicting, non-disputed numeric estimates (two
  independent sources giving different market sizes without either being marked `disputed`) — the
  documented "first admissible candidate in stable order" convention applies, unchanged from every
  other numeric-disagreement case in this engine since Task 10.
- The `FRAGMENTED`/`CONCENTRATED` binary does not cleanly capture a "many named competitors, one
  explicitly dominant" market (§7.3) — a real, observed limitation of the closed label set itself.
- No mechanism verifies that an independently-published market-size figure's stated category
  actually matches the assessed company's real competitive niche (§7.3's category-boundary
  finding) — currently relies entirely on whoever tags `assessment_criteria` making that judgment
  correctly, the same trust boundary every other dimension in this engine already has.
- Five (now effectively two, for this pillar) real companies remains far short of a calibration
  cohort — `NEW_ENGINE_CALIBRATION.md`'s much larger plan is still the real path to final numbers.

## 10. Readiness for the eventual full-engine evaluation

Market Opportunity now behaves like the architecture Product & Technology already proved:
evidence-traceable (zero violations, real and offline), deterministic after classification,
resistant to unsupported claims (company TAM slides and generic hype never score), explicit about
uncertainty (three distinct Unscored reasons — no evidence, stale, uncorroborated/generic — plus
disputed exclusion, all exercised), and willing to withhold (the full pillar withholds cleanly on
zero evidence; individual dimensions withhold on thin evidence without dragging the others down).
**Ready to join Product & Technology in a future combined evaluation once at least one more pillar
exists to make "full-engine" meaningful** — this task deliberately implements no overall
(cross-pillar) scoring and no additional pillar, per its own explicit scope constraints.
