# Live Evaluation — Fish Audio (Run 001)

**Task 26, cohort member 3 of 4 (Bullet excluded — see `LIVE_EVALUATION_COHORT_001.md` §0). Real
Tavily/HTTP/OpenAI calls, no manual evidence, no rerun, no fixes.**

- **Run timestamp:** 2026-09-30T05:36:46.623025+00:00 · **run_id:** `cb33d7d78885`
- **Methodology version:** `evidence_engine.v1-provisional-11` (unchanged)
- **Input:** `CompanyAnalysisInput(company_name="Fish Audio", website_url="https://fish.audio")` —
  canonical URL resolved from `live_research/fish_audio.py`'s own existing curated evidence
  (`https://fish.audio/developers/`), not guessed.
- **Configuration:** `AcquisitionBudget()` defaults, identical to the rest of the cohort

## 1. Run completion and timing

Completed cleanly, **25.8s** total — the fastest run this cohort. Retrieval 10.67s, extraction 15.09s;
deterministic evaluation ~0s.

## 2. Provider measurements

- **Search:** 12/12 succeeded, 0 retries.
- **Retrieval:** 28 records, 20 succeeded, 4 failed — 3 HTTP 403 (`traded.co`, `mlq.ai`, `pitchbook.com`)
  and one genuinely unusual **HTTP 202** (`morningstar.com`'s PR Newswire syndication page — an
  "accepted, processing" response our fetcher correctly does not treat as success).
- **Extraction:** 5 batches, **5 real attempts** (first-try, 0 validation retries). Input tokens
  23,382 / output 2,976 / total **26,358**. 4 of 5 batches truncated. 0 sources excluded, 0
  content-filter/length failures.

## 3. Evidence measurements

18 claims accepted, 0 rejected. **Structured-fact rate: 8/18 = 44.4%.** **17 distinct independence
groups from 18 claims** — one real duplicate pair correctly collapsed: the same $52M seed round,
reported independently by Yahoo Finance and valueaddvc.com, both typed `financing_type="Seed"`/
`round_date="2026-07-28"` identically — genuine independent corroboration recognized correctly, not
double-counted. 0 contradictions/disputes. **Source-type composition: 15 `independent_reporting`, 2
`product_documentation` (fish.audio's own docs subdomain), 1 `company_disclosure`** (fish.audio's own
author page) — the most first-party-inclusive run of the cohort, appropriately: as the earliest-stage
company, more of its own public surface (docs, team page) was genuinely relevant.

**Routing status distribution:** `routed`: 13, `rejected_invalid_routing`: 3, `context_only`: 1,
`unrouted_insufficient_structure`: 1. **Zero unexplained outcomes.**

## 4. Task 25 hypothesis checks — a precise, new confirmation of the cohort's central pattern

- A `founding_year` claim (`0eed8e5a889c4008`, about a DIFFERENT, unrelated "Big Fish Audio" loop-
  library company Tavily's own search conflated with the target — see §9 below) uses `"amount"` not
  `"value"` — the exact same field-name mismatch first found in `LIVE_EVALUATION_LINEAR_002.md`,
  confirmed here a third time.
- Both real `funding_round` claims about the genuine $52M seed round carry `financing_type="Seed"` —
  **a precise, new instance of the cohort's central pattern, seen for the first time with full
  clarity:** the model is populating `financing_type` with the ROUND LABEL ("Seed") rather than the
  LEGAL FINANCING STRUCTURE (`"equity"`) `evaluate_funding_history()` actually requires
  (`P.FUNDING_HISTORY_COUNTED_FINANCING_TYPES = {"equity"}`) — these are two genuinely different
  concepts the extraction prompt does not currently distinguish clearly enough. Both claims were
  correctly typed and (where proposed) correctly routed; both are `UNROUTED_INSUFFICIENT_STRUCTURE`/
  `REJECTED_INVALID_ROUTING` for this one precise, now well-understood reason.
- A `funding_round_type` claim correctly populates `value="unfunded"` (about the unrelated "Big Fish
  Audio," §9) — proving the model CAN populate the categorical `value` field correctly when the prompt
  context makes it unambiguous; it simply does so inconsistently across kinds.
- Two `disclosed_scale`/`growth_trajectory`-routed `traction_metric` claims (ARR $21M, 8M users) —
  same three-part completeness gap as Notion (`metric="ARR"` does match `TRACTION_MONEY_METRICS`
  correctly here, a positive case — but `value_type` is absent from both, so neither still qualifies).

## 5. Pillar results

| Pillar | Published | Strength | Coverage | Confidence | Scored/Total |
|---|---|---|---|---|---|
| Market Opportunity | No | — | 0.0% | Low | 0/4 |
| **Product & Technology** | **Yes** | **7.67** | 75.0% | High | 3/4 |
| Team & Leadership | No | — | 0.0% | Low | 0/3 |
| Commercial Traction | No | — | 0.0% | Low | 0/5 |
| Execution & Momentum | No | — | 0.0% | Low | 0/3 |
| Financial & Funding Signals | No | — | 0.0% | Low | 0/3 |

The cohort's ONLY dimension besides the two recurring Product & Technology ones to score:
`product_existence_maturity`: 7.0, from a real LinkedIn founder post. `differentiation_claim_
corroboration`: 8.0 (6 claims). `defensibility_signal`: 8.0 (2 claims, both from fish.audio's own
docs/product pages — the ONLY company this cohort where the company's own product surface
contributed to a scored dimension).

**Company-level:** Coverage 13.5% (the highest this cohort, though still far below the 40% floor),
Confidence High, **not publishable**. **Stage: Undetermined.** Zero cross-pillar audit findings.

## 6. Comparison against curated evidence (Tasks 14-19)

The curated Fish Audio fixture (`live_research/fish_audio.py`) is deliberately sparse (Task 11's own
"early-stage, real research" roster entry) — `product_existence_maturity`, `technical_depth_signal`,
`differentiation_claim_corroboration`, `stage_signal`, explicitly noting no `defensibility_signal`
evidence was ever found by hand either. This live run found **more** evidence than the curated fixture
in several respects (the $52M seed round with two independent sources, ARR/user-count figures, a
`defensibility_signal` result the manual research never achieved) — a genuinely encouraging result for
an earlier-stage, sparser-evidence company. **Missed:** `technical_depth_signal` (0 claims this run,
present in the curated fixture). **Incorrectly extracted:** see §9 below (the Big Fish Audio
conflation) — the one real extraction-quality concern this run. **Incorrectly rejected:** none (0
rejections). **Correctly withheld:** Market Opportunity, Team & Leadership, Commercial Traction,
Execution & Momentum, Financial & Funding Signals.

## 7. Note — a name-collision finding worth flagging separately from routing

Two claims (`0eed8e5a889c4008`, `5633985ce1b8b401`) are about **"Big Fish Audio,"** a real but
**unrelated company** (a decades-old royalty-free sample-library provider, `founded 1986`), sourced
from a Tracxn company-profile page that Tavily's own search surfaced for the query "Fish Audio funding
round investors raised" purely on name similarity. Both claims are internally self-consistent and
correctly grounded IN that source, and neither reached a scored dimension (they are the `founding_
year`/`funding_round_type` claims discussed in §4) — so no incorrect score resulted. This is a
genuine **acquisition/relevance-adjacent finding**, distinct from the `subject_relationship` mechanism
(which addresses a THIRD PARTY discussing the target company, not a DIFFERENT company sharing a
similar name) — see the cohort report §12 for its own classification.
