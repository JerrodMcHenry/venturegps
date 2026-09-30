# Live Evaluation — Notion (Run 001)

**Task 26, cohort member 2 of 4 (Bullet excluded — see `LIVE_EVALUATION_COHORT_001.md` §0). Real
Tavily/HTTP/OpenAI calls, no manual evidence, no rerun, no fixes.**

- **Run timestamp:** 2026-09-30T05:36:11.812527+00:00 · **run_id:** `dddc75458e7f`
- **Methodology version:** `evidence_engine.v1-provisional-11` (unchanged)
- **Input:** `CompanyAnalysisInput(company_name="Notion", website_url="https://www.notion.com")`
- **Configuration:** `AcquisitionBudget()` defaults, identical to the rest of the cohort

## 1. Run completion and timing

Completed cleanly, **27.7s** total. Retrieval 10.18s, extraction 17.52s; deterministic evaluation ~0s.

## 2. Provider measurements

- **Search:** 12/12 succeeded, 0 retries.
- **Retrieval:** 25 records, 23 succeeded, 1 failed (`salesintel.io`'s TAM-explainer page, HTTP 403).
- **Extraction:** 6 batches, **6 real attempts** (every batch first-try, 0 validation retries). Input
  tokens 29,016 / output 3,535 / total **32,551**, the highest token cohort. 6 of 6 batches truncated
  on input. 0 sources excluded, 0 content-filter/length failures.

## 3. Evidence measurements

23 claims accepted (the most in the cohort), 0 rejected. **Structured-fact rate: 11/23 = 47.8%.**
**21 distinct independence groups from 23 claims** — one genuine duplicate pair (two `competitive_
structure` claims about Notion's competitive landscape) correctly collapsed. 0 contradictions/
disputes. All 23 claims `independent_reporting`.

**Routing status distribution:** `routed`: 18, `rejected_invalid_routing`: 1, `unrouted_insufficient_
structure`: 1, `context_only`: 3 (all `team_identity`). **Zero unexplained outcomes.**

## 4. Task 25 hypothesis checks and the cohort's central finding

- Both routing edge cases have full, inspectable reasons: a `founding_year` claim (`0162ef0fbded50f7`,
  "Notion was founded in 2016") proposed `["public_track_record"]` — categorically wrong, no fallback
  exists (eligible: `stage_signal`) → `REJECTED_INVALID_ROUTING`. A `funding_round` claim
  (`3aee0b09ddd54676`, "Notion has raised a total of $344.1M...") proposed the CORRECT
  `["funding_history", "stage_signal"]` — but the fact itself carries no `financing_type`/`round_date`/
  `status` → `UNROUTED_INSUFFICIENT_STRUCTURE`, correctly and honestly explained.
- **The cohort's single most important finding, confirmed here with full precision by reading the real
  code:** four `traction_metric` claims (revenue $400M, users 100M, paying customers 4M, ARR $600M)
  were all correctly typed and correctly routed to `disclosed_scale`/`growth_trajectory` — **and none
  of them can ever score**, for three compounding, verified reasons in `commercial_traction.py::_
  parse_scale_point()`: (1) `metric` must be an EXACT match to `{"revenue","arr","gmv","bookings",
  "active_users","paying_customers"}` — the extracted values ("annual revenue," "annual recurring
  revenue," "users," "paying customers") never exactly match; (2) `value_type` must literally equal
  `"actual"` — none of these four claims populate `value_type` at all; (3) `amount` must parse as a
  bare `float()` — "400 million"/"100 million"/"4 million"/"600 million" do not. This is a routing
  SUCCESS (the dimension was correctly reached) and an extraction-completeness FAILURE (the fact's own
  fields don't meet the dimension's real evidence contract) — see the cohort report §7 for the full,
  cross-company pattern this generalizes to.
- The same "annual revenue" claim also reveals a related gap in the Task 17 cross-pillar reuse rule:
  `finalize_claim()`'s own auto-tag only fires when `metric == "revenue"` EXACTLY — "annual revenue"
  never triggers it, so `revenue_disclosure` is never auto-added here either.

## 5. Pillar results

| Pillar | Published | Strength | Coverage | Confidence | Scored/Total |
|---|---|---|---|---|---|
| Market Opportunity | No | — | 0.0% | Low | 0/4 |
| **Product & Technology** | **Yes** | **8.0** | 50.0% | High | 2/4 |
| Team & Leadership | No | — | 0.0% | Low | 0/3 |
| Commercial Traction | No | — | 0.0% | Low | 0/5 |
| Execution & Momentum | No | — | 0.0% | Low | 0/3 |
| Financial & Funding Signals | No | — | 0.0% | Low | 0/3 |

`differentiation_claim_corroboration`: 8.0 (CORROBORATED, 4 claims). `defensibility_signal`: 8.0
(CORROBORATED_MOAT, 3 claims) — from jotform.com (an independent integrations-roundup blog) and
pcmag.com's own review, not notion.com itself.

**Company-level:** Coverage 9.0%, Confidence High, **not publishable** — same two-gate reasons as
Stripe. **Stage: Undetermined** (the `founding_year`/`funding_round` claims above never reached
`stage_signal`). Zero cross-pillar audit findings.

## 6. Comparison against curated evidence (Tasks 14-19)

The curated Notion fixture (`live_research/notion.py`, `fixtures/notion.py`) covers `market_
definition_size`, `market_growth_signal`, `competitive_landscape_position`, `customer_base_breadth`,
`stage_signal`, `technical_depth_signal`, `product_existence_maturity`, `disclosed_scale`,
`differentiation_claim_corroboration`, `defensibility_signal`, `timing_catalyst` — real hand-sourced
market-sizing and stage evidence Task 13/18/19's own real research found.

This live run found genuinely new, real evidence (revenue/ARR/user-count figures the curated fixture,
built earlier, did not have) but **missed** the market-sizing evidence entirely (Market Opportunity
scored 0/4, same as every other company this cohort) and could not use its own traction/funding
figures for the field-completeness reasons above. **Incorrectly extracted:** none found. **Incorrectly
rejected:** none (0 rejections). **Correctly withheld:** every pillar besides Product & Technology —
no dimension had genuinely sufficient, usable live evidence.
