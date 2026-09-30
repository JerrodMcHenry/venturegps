# Live Evaluation — Notion (Run 002)

Task 28 — the second live run against Task 27's classifier-ready structured extraction contract.
Baseline: `LIVE_EVALUATION_NOTION_001.md` (unmodified). Input:
`CompanyAnalysisInput(company_name="Notion", website_url="https://www.notion.com")` — same canonical
URL as run 001, reused unchanged. Same unmodified `AcquisitionBudget()`, research plan, pipeline, and
6-pillar methodology as Fish Audio's run above and as Notion's own run 001. Run exactly once, after
Fish Audio, with **no code, prompt, schema, query, or budget change made between the two runs** — both
companies tested the identical frozen implementation. Provider-internal retries (configured, bounded)
allowed. **Primary metric: classifier-ready rate, not Coverage or pillar publication.**

## 1. Run completion and timing

Completed successfully, one run, no fatal errors. **34.02s total** (vs. 27.71s for 001). Stage
breakdown: source_discovery_and_retrieval 13.37s (23 sources, unchanged from 001), evidence_extraction
20.65s (**13 claims accepted, down from 23** — real search/extraction variance, not a regression; 0
rejected either run).

## 2. Provider measurements

| | Tavily | HTTP | OpenAI (gpt-4.1-mini) |
|---|--:|--:|--:|
| Calls | 12 | 25 | 6 |
| Succeeded | 12 | 23 | 6 |
| Failed | 0 | 2 (HTTP 403, unrelated to Task 27) | 0 |
| Provider attempts beyond first | 0 | 0 | 2 (two batches needed a validation-feedback retry, both succeeded) |

Tokens: **45,865 total** (41,966 input / 3,899 output) vs. 001's 32,551 (29,016/3,535) — input tokens
rose materially even though FEWER claims were accepted this run (13 vs 23); this tracks the longer
system prompt (same, already-documented Task 27 tradeoff) rather than claim volume. 6/6 batches
truncated on input both runs (unchanged). 0 output truncation, 0 content-filter failures, 0 sources
excluded for budget.

## 3. Evidence measurements

**13 claims accepted, 0 rejected** (vs. 23/0 for 001). **Structured-fact rate: 8/13 = 61.5%** — up from
001's 47.8%, though this reflects a smaller, differently-shaped claim set (search variance), not
necessarily a Task 27 effect on its own.

### The primary metric: classifier readiness

| | Run 001 (reconstructed*) | Run 002 (measured directly) |
|---|--:|--:|
| Relevant typed claims (kind has a deterministic consumer) | 8 | 5 |
| Classifier-ready claims | **0** | **2** |
| **Classifier-ready rate** | **0.0%** | **40.0%** |

*Run 001 predates `check_classifier_readiness()`; reconstructed by applying that same unmodified
function to 001's preserved `ledger_claims`, without touching `LIVE_EVALUATION_NOTION_001.md`.

**A real, material, positive change** — and for the first time in this cohort's live-run history
(spanning both Linear runs, Stripe, Notion, and Fish Audio), **a dimension other than Product &
Technology's own three scored at all** (§7).

## 4. Categorical semantic correctness (§5) — the metric validation (§7)

**Metric vocabulary is fixed for two of three traction claims, confirmed directly.** 001's real
extracted values were `"annual revenue"`, `"annual recurring revenue"`, `"users"`, `"paying customers"`
— none matched the required enum. 002's real values: `metric="revenue"` (exact match) for the $500M
figure, `metric="active_users"` (exact match) for the 100M-users figure — both a genuine, confirmed fix
of the Task 26 paraphrasing pattern. `value_type="actual"` is now correctly populated on both (001
populated it on zero claims).

**But neither is classifier-ready, for a new, different reason: `period_date` is missing from both.**
`TRACTION_METRIC_CONTRACT` requires `period_date`; neither real excerpt-derived fact this run supplies
one (the source articles state the figures without an explicit as-of date the model captured into this
field). This is not the metric-vocabulary or value_type gap Task 27 targeted — both of those are
confirmed fixed here — it is a different, still-open completeness gap.

**A third traction claim was correctly, appropriately excluded**: `metric="valuation"`, `value=
"10000000000"` — `"valuation"` is not in the traction-metric vocabulary at all (correctly), since a
valuation is not a traction/revenue signal. This is the contract working as intended, though it also
shows the model still occasionally applies the `traction_metric` kind to a fact that is not really a
traction metric.

**No `funding_round` claim was extracted at all this run** — the same acquisition/retrieval-variance
pattern Task 26 found for Stripe (a company/run where the funding topic's own queries retrieved sources
but produced no funding-tagged claim). Per §13's own instruction, this is correctly classified as **Not
observed**, not a Task 27 failure.

## 5. The most important finding of this validation — two schema-valid, semantically wrong categorical labels

Two claims reached a scored dimension for the first time this cohort. Both are schema-valid. Neither is
semantically well-supported by its own cited excerpt.

**`competitive_structure="fragmented"`** — cited excerpt: *"Notion competitors — View the competitive
landscape for Notion, featuring companies like Microsoft, Atlassian, and Airtable."* This is a **bare
list of named competitors with no structural characterization at all** — not a single word in the
excerpt says the market is fragmented (or concentrated). `COMPETITIVE_STRUCTURE_CONTRACT`'s own notes
are explicit: *"never inferred from a bare list of named competitors."* The model did exactly that.

**`retention_signal="STRONG"`** — cited excerpt: *"He added that about 90% of the business comes from
'multiplayer usage,' or teams of workers."* This is an **adoption/usage-pattern statistic** — what
fraction of usage is team-based versus solo — not a statement about customers renewing, retaining, or
churning at all. Task 28's own §9 instruction states this precisely: *"Customer logos, user counts,
testimonials, adoption, longevity, or brand popularity must not become retention."* This claim is
exactly that: adoption became retention.

**Why this happened, precisely.** `check_classifier_readiness()` and the real downstream classifiers
(`WellBehavedCompetitiveLandscapeClassifier`, `WellBehavedRetentionRenewalClassifier`) were never
designed to, and structurally cannot, verify that a chosen categorical value is the value THIS SPECIFIC
excerpt actually supports — they verify only that the field is present and the value is in the allowed
vocabulary. That has been true since these classifiers were first built (Tasks 13/15); it is not a
defect Task 27 introduced or a change to the contract's own logic. What changed is that Task 27's
prompt now encourages the model to populate these categorical fields far more often — which is
precisely what raised the classifier-ready rate — and, as an unavoidable consequence, also raises the
rate at which a wrong-but-valid value can now slip through to a scored dimension, where before it
simply never got populated at all and stayed correctly Unscored. **This is the single most important
finding of Task 28** — see `docs/methodology/LIVE_EVALUATION_CONTRACT_VALIDATION_001.md` §5 and §9 for
the full cross-company treatment and its role in the decision gate.

## 6. Team validation

Three `team_identity` claims, all about Ivan Zhao (co-founder/CEO), from three independent sources.
**`person_id` correctly, consistently backfilled to the same id (`27177bab9f68d8d1`) across all three**
— identity resolution is working correctly. All three route to `leadership_composition` (context-only,
correct). **The `role`-exact-match gap documented in
`docs/methodology/CLASSIFIER_READY_EXTRACTION_CONTRACT.md` §7 is confirmed still present**: the three
extracted role strings (`"co-founder and CEO"`, `"CEO"`, `"Founder and CEO"`) never exactly equal
`"founder"`, so `_confirmed_person_ids(role="founder")` would not admit this person for
`founder_relevant_experience` gating even if a founder-experience claim about him existed this run (none
did). Pre-existing, documented, not caused by Task 27; not fixed here per this task's own rules.

## 7. Fail-closed behavior

0 claims rejected. Routing status distribution: `routed` 7, `context_only` 3,
`unrouted_insufficient_structure` 3, `rejected_invalid_routing` 0. All 3 unrouted claims trace to §4's
period_date gap. No fabrication of a missing field observed anywhere in this run.

## 8. Pillar results

| Pillar | Published | Strength | Coverage | Confidence | Scored dimensions |
|---|---|--:|--:|---|---|
| Market Opportunity | No | — | **25.0%** (was 0.0%) | **Medium** (was Low) | competitive_landscape_position (§5) |
| Product & Technology | **Yes** | 8.0 | 50.0% | High | differentiation_claim_corroboration, defensibility_signal |
| Team & Leadership | No | — | 0.0% | Low | none |
| Commercial Traction | No | — | **15.0%** (was 0.0%) | **Medium** (was Low) | retention_renewal_signal (§5) |
| Execution & Momentum | No | — | 0.0% | Low | none |
| Financial & Funding Signals | No | — | 0.0% | Low | none |

Company Coverage rose to **17.0%** (from 9.0%), Confidence High, still not publishable (no pillar beyond
Product & Technology meets its own coverage/scored-dimension floor). **Two dimensions scored real
numeric values for the first time this cohort** — directly traceable to §5's two classifier-ready
claims. Given §5's semantic-accuracy finding, this Coverage increase should **not** be read as an
unqualified success — the underlying evidence for both newly-scored dimensions is questionable.

## 9. Comparison against LIVE_EVALUATION_NOTION_001.md

See `docs/methodology/LIVE_EVALUATION_CONTRACT_VALIDATION_001.md` §4 for the full 001→002 comparison
table (both companies) and the consolidated cross-company analysis. Summary: classifier-ready rate rose
from 0% to 40%; metric-vocabulary paraphrasing confirmed fixed; `period_date` is the new blocker for
traction; two dimensions scored for the first time, but both on semantically questionable grounds (§5);
zero claims rejected either run.
