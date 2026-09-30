# Live Evaluation — Stripe (Run 001)

**Task 26, cohort member 1 of 4 (Bullet excluded — see `LIVE_EVALUATION_COHORT_001.md` §0). Real
Tavily/HTTP/OpenAI calls, no manual evidence, no rerun, no fixes.**

- **Run timestamp:** 2026-09-30T05:35:28.749938+00:00 · **run_id:** `8ab8dba3eb59`
- **Methodology version:** `evidence_engine.v1-provisional-11` (unchanged)
- **Input:** `CompanyAnalysisInput(company_name="Stripe", website_url="https://stripe.com")`
- **Configuration:** `AcquisitionBudget()` defaults, identical to both Linear runs

## 1. Run completion and timing

Completed cleanly, **26.5s** total. Retrieval 13.11s, extraction 13.41s (the two real stages);
deterministic evaluation ~0s.

## 2. Provider measurements

- **Search:** 12/12 succeeded, 0 retries.
- **Retrieval:** 29 records, 19 succeeded, 5 URLs failed (all HTTP 403 — `getapp.com`, `6sense.com`,
  `comparably.com`, `appsruntheworld.com`, a Medium post) — all ordinary site-side blocks, no SSRF
  rejection.
- **Extraction:** 5 batches, **5 real attempts** (every batch succeeded first try, 0 validation
  retries). Input tokens 23,273 / output 2,680 / total **25,953**. 5 of 5 batches had input
  truncation. 0 sources excluded for budget, 0 content-filter/length failures.

## 3. Evidence measurements

12 claims accepted, 0 rejected. **Structured-fact rate: 9/12 = 75.0%** — the highest of the cohort.
**11 distinct independence groups from 12 claims** — exactly one pair (the two payment-volume
`traction_metric` claims, same metric/period, one from Wikipedia and one from chargeback.io)
correctly collapsed to a shared group — genuine, real corroboration from two independently-owned
sources recognized correctly; every other claim is its own group (no other duplicate/syndicated
source this run). 0 contradictions/disputes. All 12 claims `independent_reporting` (0
`company_disclosure`, 0 `product_documentation` — notably, `stripe.com` itself was never
successfully retrieved as a source this run).

**Routing status distribution:** `routed`: 10, `context_only`: 2 (both `team_identity`). **Zero
claims ended with an unexplained outcome** — every one of the 12 traces to a specific, inspectable
`RoutingDecision`.

## 4. Task 25 hypothesis checks (routing completeness)

- Two `team_identity` claims (John Collison, Patrick Collison) — both correctly `CONTEXT_ONLY`,
  `person_id` correctly backfilled and DIFFERENT for the two brothers (`be7293e38b573ee9` vs.
  `51af5ffff51029a5`) — person-identity normalization working correctly.
- Two `founder_experience` claims (same two people, from the same Wikipedia source) — correctly typed,
  correctly ROUTED to `founder_relevant_experience` (the model's own proposal already matched) — **but
  neither carries a `value` field** (`ADJACENT`/`DIRECT`), so `founder_relevant_experience`'s own
  classifier finds nothing to score despite perfect routing. See cohort report §7 for this pattern
  repeated across the whole cohort.
- Three `traction_metric` claims (payment volume, business count) all correctly routed to
  `growth_trajectory`/`disclosed_scale`.
- One `retention_signal` claim ("Radar users... cut disputes by 17%") correctly typed and routed to
  `retention_renewal_signal` — but carries `amount`/`metric`, never the categorical `value` label
  (`WEAK`/`MODERATE`/`STRONG`) that dimension's own classifier requires.
- **No `funding_round`/`funding_round_type`/`founding_year` claim was extracted at all this run** —
  despite Stripe's funding history being extremely well-documented publicly. The `FUNDING_AND_
  FINANCIALS` topic's own two queries retrieved sources without any retrieval failure recorded, but
  produced zero funding-tagged claims — an acquisition/extraction miss, not a routing one (routing
  never even saw a `funding_round` kind this run).

## 5. Pillar results

| Pillar | Published | Strength | Coverage | Confidence | Scored/Total |
|---|---|---|---|---|---|
| Market Opportunity | No | — | 0.0% | Low | 0/4 |
| **Product & Technology** | **Yes** | **8.0** | 50.0% | High | 2/4 |
| Team & Leadership | No | — | 0.0% | Low | 0/3 |
| Commercial Traction | No | — | 0.0% | Low | 0/5 |
| Execution & Momentum | No | — | 0.0% | Low | 0/3 |
| Financial & Funding Signals | No | — | 0.0% | Low | 0/3 |

`differentiation_claim_corroboration`: 8.0 (CORROBORATED, 3 claims). `defensibility_signal`: 8.0
(CORROBORATED_MOAT, 2 claims). Both from independent commentary/analysis pages
(schematichq.com, research.contrary.com), not Stripe's own site.

**Company-level:** Coverage 9.0%, Confidence High (from the 1 published pillar only), **not
publishable** — `["company-level weighted coverage 9.0% < floor 40.0%", "only 1 published pillar(s) <
floor 2"]`. **Stage: Undetermined.** Zero cross-pillar audit findings.

## 6. Comparison against curated evidence (Tasks 14-19)

The curated Stripe fixture (`live_research/stripe.py`) covers `funding_history`, `stage_signal`,
`disclosed_scale`, `growth_trajectory`, `revenue_disclosure`, `gtm_motion_evidence`, `shipping_
velocity`, `founder_relevant_experience`, `public_track_record`, `technical_depth_signal`,
`product_existence_maturity`, `strategic_consistency`, `commercial_validation` — spanning all six
pillars, hand-researched with real 2019/2020/2023 funding rounds ($7.35B total, Task 17), real 2024/
2025 revenue figures, and Sessions 2026 GA/preview distinctions (Task 16).

This live run found **genuinely new, real evidence the curated fixture did not have** ($159B
valuation, $1.9T 2025 payment volume, 5M businesses, 17% Radar dispute reduction) — all plausible,
correctly grounded. It **missed** every funding-round fact, every shipping/changelog fact, every
market-sizing fact, and (critically) never populated the categorical `value` fields the curated
fixture's own hand-authored claims always carried. **Incorrectly extracted:** none found.
**Incorrectly rejected:** none (0 rejections). **Correctly withheld:** Market Opportunity, Commercial
Traction, Execution & Momentum, Financial & Funding Signals — no dimension in any of these had
sufficient live evidence, and none was scored on a guess.
