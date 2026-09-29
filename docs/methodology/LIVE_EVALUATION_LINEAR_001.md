# Live Evaluation — Linear (Run 001)

**Task 22. Exactly one controlled live end-to-end analysis, real Tavily/HTTP/OpenAI calls, no manual
evidence, no reruns, no fixes applied during or after this task.** This document is the uncontaminated
record of that single run. Nothing in the codebase was changed before, during, or after it — see
`git status` (clean) alongside this document at the time it was written.

- **Run timestamp (UTC, telemetry `started_at`):** 2026-09-29T01:36:42.965239+00:00
- **`run_id`:** `de494fb0ebb4`
- **Methodology/parameter version:** `evidence_engine.v1-provisional-11` (unchanged — confirmed via
  `git status app/evidence_engine/parameters.py` showing no diff, before and after this run)
- **Acquisition configuration:** `AcquisitionBudget()` defaults, unmodified — 6 topics × 2 queries = 12
  queries; `max_sources_per_query=3`; `max_total_sources=24`; `max_extraction_calls=24`;
  `max_sources_per_batch=4`; `max_total_input_chars_per_batch=20,000`;
  `EXTRACTION_MAX_OUTPUT_TOKENS=4,096`; `EXTRACTION_MAX_PROVIDER_ATTEMPTS_PER_BATCH=2`;
  `max_concurrent_searches=3`/`_retrievals=4`/`_extraction_batches=2`. Model: `gpt-4.1-mini` via
  `client.chat.completions.parse()`.
- **Company input:** `CompanyAnalysisInput(company_name="Linear", website_url="https://linear.app")`

## 1. Whether the run completed

**Yes, cleanly, on the first attempt.** Total wall-clock: **37.6 seconds**. No exception propagated out
of `run_acquisition_pipeline()`. No credential was missing (a purely local `.env`-path issue in the
throwaway invocation script — not `app/evidence_engine/` code — was fixed before any external call was
made; zero external calls occurred before that fix, consistent with item 10's own exception clause).

## 2. Resolved stage and company reference

- **`company_ref`:** `linear`
- **Resolved `Stage`: `Undetermined`** — no claim in the ledger carries a `stage_signal`-tagged fact.
  See §9 (Extraction failure #1) for why real, retrieved funding-round evidence did not produce one.

## 3. Research plan (all 12 queries, unchanged from the deterministic template)

| # | Topic | Query text |
|---|---|---|
| 1 | product_and_technology | Linear product features integrations |
| 2 | product_and_technology | Linear review comparison independent |
| 3 | market_and_competition | Linear market size industry category |
| 4 | market_and_competition | Linear competitors competitive landscape |
| 5 | team_and_leadership | Linear founder co-founder background |
| 6 | team_and_leadership | Linear executive team leadership hires |
| 7 | traction_and_customers | Linear customers revenue users |
| 8 | traction_and_customers | Linear growth retention case study |
| 9 | execution_and_shipping | Linear changelog product launch release |
| 10 | execution_and_shipping | Linear partnership sales go-to-market |
| 11 | funding_and_financials | Linear funding round investors raised |
| 12 | funding_and_financials | Linear valuation financials margin |

## 4. Search, retrieval, extraction — what actually happened

- **Search:** 12/12 queries succeeded on the first attempt (0 retries). All Tavily calls used
  `search_depth="basic"`, `include_answer=False`, `max_results=5` — real, unmodified configuration.
- **Retrieval:** 26 retrieval records (22 succeeded, 2 URLs failed both their allowed attempts — 4
  failed records total, unrelated pairs):
  - `https://thedigitalprojectmanager.com/tools/best-linear-alternatives` — HTTP 403 both attempts
    (site-side bot/anti-scrape block, not an SSRF rejection).
  - `https://exa.ai/websets/directory/linear-executives` — HTTP 429 both attempts (rate-limited by
    that third-party site, not by our own request rate).
  - **22 sources successfully retrieved and passed to extraction** (of 24 candidates that survived
    cross-query URL dedup and the per-query/total caps).
- **Extraction:** 22 retained sources → **6 batches** (default `max_sources_per_batch=4`: five batches
  of 4, one of 2). **Every batch succeeded on its first real attempt** — `provider_attempts=1` and
  `validation_retries=0` on all 6 — no transient failure, no grounding-retry needed, zero content-filter
  or output-length truncation events. **3 of 6 batches had their INPUT content truncated** to fit the
  20,000-character budget (expected and correct — several retained pages, e.g. Linear's own `/about`
  page, comfortably exceeded the per-source 6,000-character retrieval cap before batching even began).
- **18 claims accepted, 0 rejected** (`claims_rejected=0` at both the telemetry-count and the
  `rejected_count` level). Every proposed candidate across all 6 batches passed grounding validation on
  the first pass.
- **Deduplication:** 0 exact-duplicate search-result URLs collapsed this run (all 22 retained sources
  were distinct URLs). **0 claims marked `disputed`** (no structured-fact-level contradiction detected).

## 5. Evidence Ledger summary

18 claims, all `support_status=directly_supported`, all `contradicts=[]`. Source-type distribution:
17 `independent_reporting`, 1 `company_disclosure` (`linear.app/about`). `structured_fact` was populated
on only **3 of 18 claims (17%)** — see §9 (Extraction observation).

Claim-by-claim summary (full text in the raw capture, §12):

| Claim | Source | `assessment_criteria` | `structured_fact` |
|---|---|---|---|
| AI agents (triage/PR review) | spyingbee.com | defensibility_signal, differentiation_claim_corroboration | — |
| AI agents (workspace member) | spyingbee.com | defensibility_signal, differentiation_claim_corroboration | — |
| 3rd-party "autonomous dev team" using Linear tickets | dev.to (personal blog) | differentiation_claim_corroboration, timing_catalyst | — |
| #5 adoption rank, 15% share | ramp.com | competitive_landscape_position | `competitive_structure`, value="15% adoption rate" |
| Adoption by company size | ramp.com | competitive_landscape_position | — |
| Key capabilities (issue tracking, workflows) | ramp.com | differentiation_claim_corroboration, defensibility_signal | — |
| Competitor list (Jira, Asana, Notion...) | seeto.ai | competitive_landscape_position | — |
| Positioning ("purpose-built... AI era") | seeto.ai | competitive_landscape_position, strategic_consistency | — |
| Competitor list (2nd article) | seeto.ai | competitive_landscape_position | — |
| Karri Saarinen = CEO (video title) | youtube.com | leadership_composition, public_track_record | — |
| Karri Saarinen = CEO | review.firstround.com | leadership_composition | `team_identity`, no `person_id` |
| Saarinen's Airbnb/Coinbase background | karrisaarinen.com | leadership_composition, public_track_record | — |
| Full leadership list + ~200 employees + investors | linear.app/about | leadership_composition | — |
| 28,359 companies, 650 churned, 1,749 renewing | bloomberry.com | commercial_validation, retention_renewal_signal | — |
| $75M+ ARR, 50%+ YoY growth | valueaddvc.com | commercial_validation, growth_trajectory | `traction_metric`, metric=ARR |
| NRR >130% | valueaddvc.com | retention_renewal_signal, commercial_validation | — |
| **$82M Series C, $1.25B valuation, June 2025, ~178 employees** | libraryofllm.com | commercial_validation, growth_trajectory | — |
| Growth motion (PLG, word of mouth) | cofounderbase.com | commercial_validation, growth_trajectory, retention_renewal_signal | — |

## 6. Pillar results

| Pillar | Published | Strength | Coverage | Confidence | Scored | Unscored | Primary withhold reason |
|---|---|---|---|---|---|---|---|
| Market Opportunity | No | — | 0.0% | Low | 0/4 | 4/4 | 0 scored dimensions (< floor 2) |
| **Product & Technology** | **Yes** | **8.0** | 50.0% | High | 2/4 | 2/4 | — |
| Team & Leadership | No | — | 0.0% | Low | 0/3 | 3/3 | 0 scored dimensions (< floor 2) |
| Commercial Traction | No | — | 0.0% | Low | 0/5 | 5/5 | 0 scored dimensions (< floor 2) |
| Execution & Momentum | No | — | 0.0% | Low | 0/3 | 3/3 | 0 scored dimensions (< floor 2) |
| Financial & Funding Signals | No | — | 0.0% | Low | 0/3 | 3/3 | 0 scored dimensions (< floor 2) |

**Product & Technology's own two scorable dimensions:**
- `differentiation_claim_corroboration`: **8.0** (CORROBORATED, High confidence) — 4 supporting claims
  (spyingbee.com ×2, dev.to, ramp.com).
- `defensibility_signal`: **8.0** (CORROBORATED_MOAT, High confidence) — 3 supporting claims
  (spyingbee.com ×2, ramp.com).
- `product_existence_maturity` and `technical_depth_signal`: both `unscored_no_evidence` — **zero**
  claims tagged for either dimension this run.

**Company-level:** Coverage **9.0%** (< 40% floor), Confidence **High** (computed only over the one
published pillar), **not publishable** — `["company-level weighted coverage 9.0% < floor 40.0%", "only 1
published pillar(s) < floor 2"]`. **No overall 0–100 score exists or was computed** — none is defined in
this methodology.

## 7. Cross-pillar audit

**Zero findings** (no ERROR, WARNING, or INFO) — the audit ran against a genuinely sparse ledger and
found nothing to flag; this is expected and correct for a run this thin, not evidence the audit "didn't
try."

## 8. Provider usage (measured, real)

**Tavily:** 12 logical searches, 12 real attempts (0 retries), 12 succeeded. (Results-per-search count
was not separately telemetered this run — only the post-cap retained-source count is recorded; see §19.)

**HTTP:** 24 URLs attempted (from the deduped/capped candidate pool), 22 succeeded, 2 failed (both after
2 real attempts each — 4 failed retrieval records), 0 SSRF rejections.

**OpenAI:**
- Model: `gpt-4.1-mini`, via `client.chat.completions.parse()` (structured output).
- Extraction batches: 6.
- Real provider attempts: **6** (1 per batch — no batch needed a second attempt).
- Input tokens: **27,071**. Output tokens: **4,363**. **Total: 31,434.**
- Validation retries: **0**.
- Input truncation: 3 of 6 batches. Output truncation (`finish_reason == "length"`): **0**. Content-filter
  refusals: **0**.
- No dollar cost is reported — no `ProviderPricing` was configured for this run, and none is invented
  here (per the standing "never invent a cost figure" rule).

## 9. Latency report

| Stage | Duration | Share of total |
|---|---|---|
| Research planning | 0.00s | 0% |
| **Source discovery + retrieval** | **15.46s** | **41%** |
| **Evidence extraction** | **22.16s** | **59%** |
| Contradiction detection | 0.00s | 0% |
| Ledger construction | 0.00s | 0% |
| Six-pillar evaluation + aggregation | 0.00s | 0% |
| **Total** | **37.63s** | 100% |

**Dominant stage: evidence extraction (59% of total wall-clock)** — consistent with it being the only
stage making large-payload (up to ~5,000-token) external calls; deterministic downstream stages
(contradiction detection, ledger construction, six-pillar evaluation) are effectively instantaneous, as
expected for pure Python with no I/O.

## 10. Evidence-quality review (mechanical, per claim — item 7)

**Grounding (excerpt actually supports the proposition):** 17/18 claims are cleanly grounded — the
excerpt is a real, literal, contextually sound quote supporting its `claim_text`. **One claim is
questionable on RELEVANCE, not literal grounding:** the "autonomous AI dev team" claim (dev.to) is a
**personal blog post about a third-party hobbyist tool that USES Linear's ticket data as one input** —
the excerpt is literally present and accurately quoted, but the underlying substance says nothing about
Linear's own product differentiation or defensibility; it is evidence about someone else's side project,
not about Linear. It nonetheless fed `differentiation_claim_corroboration`'s 8.0 score as one of four
corroborating claims. Flagged, not silently accepted as unproblematic.

**Attribution:** all 18 claims point to the correct, actually-retrieved source URL — no misattribution
found.

**Fact typing:** 3/18 claims carry a `structured_fact`; all 3 use a correct `kind` for what they
describe (`competitive_structure`, `team_identity`, `traction_metric`). One is incompletely populated
(`team_identity` without `person_id` — see §9 Provenance finding below).

**Methodology routing (assessment_criteria correctness):** **the weakest area this run** — see §9,
Extraction failures #1 and #2, for two concrete, well-evidenced misroutings (a funding round tagged away
from `funding_history`/`stage_signal`; founder background tagged away from `founder_relevant_experience`).

**Source type:** all 18 classifications look correct given the deterministic URL-only rule —
`linear.app/about` → `company_disclosure` (correct); everything else on a non-Linear domain →
`independent_reporting` (correct, including lesser-known domains like `spyingbee.com`/`seeto.ai`/
`bloomberry.com`/`valueaddvc.com`/`libraryofllm.com`/`cofounderbase.com` — none of which are on the
aggregator/filing/community allowlists, so the conservative default applied correctly; their own
EDITORIAL reliability is a separate question this classifier was never designed to answer, see §14).

**Independence:** see §9, Provenance finding — two genuinely independent sources confirming "Karri
Saarinen is CEO" (YouTube video title, First Round Review podcast page) ended up in two DIFFERENT
`independence_group_id`s instead of being recognized as corroborating the same fact.

**Contradiction handling:** nothing to evaluate — 0 claims disputed, and manual inspection found no
genuinely conflicting facts in the 18 claims (the closest candidate, ARR "$75M+" vs. no competing revenue
figure, is not actually a conflict — no second, disagreeing revenue claim exists in this ledger).

## 11. Comparison against the prior manually-curated Linear fixture (`live_research/linear.py`, Tasks 14–19)

Read only after the automated run completed, per item 8.

**Evidence categories the manual fixture had that this run did NOT find at all:**
- `product_existence_maturity` / `technical_depth_signal` — the manual fixture cited Linear's own
  GitHub/Figma/Slack integration pages; this run found zero claims for either dimension.
- `shipping_velocity` — the manual fixture cited 5 real, dated entries from `linear.app/changelog`; this
  run found zero.
- `market_definition_size` / `market_growth_signal` — the manual fixture cited a real market-sizing
  report ($1.78B → $5.12B, 11.2% CAGR); this run found neither.
- `stage_signal` — the manual fixture cited both Linear's own funding announcement and an independent
  TechCrunch article for the identical **$82M Series C / $1.25B valuation** fact this run ALSO found
  (via different outlets) — but never tagged it `stage_signal`.
- `founder_relevant_experience` — the manual fixture correctly tagged Saarinen's Airbnb/Coinbase
  background this way; this run found the same fact but tagged it `leadership_composition`/
  `public_track_record` instead.

**New, legitimate evidence this run found that the manual fixture did not have:** real 2026 figures the
manual fixture (built across Tasks 14–19, dated earlier) could not have had — the $75M+ ARR estimate,
>130% NRR estimate, 28,359-company adoption count with churn/renewal figures, AI-agent feature launches,
and category-adoption-rank data. All plausible, well-sourced, genuinely new evidence.

**Incorrectly extracted evidence:** none found that was factually wrong; the dev.to relevance issue (§10)
is the one quality concern, not a factual error.

**Incorrectly rejected evidence:** none — 0 claims were rejected this run, so there is nothing to review
in this category.

**Publication differences:** the manual fixture (hand-curated specifically to make each pillar
publishable for testing purposes) published multiple pillars; this real, automated run published only
Product & Technology. This is an expected, not alarming, difference — the manual fixture was never a
score target (per item 8's own instruction), and a real, unassisted run finding less than a curated
fixture is exactly the kind of honest result this task exists to surface.

## 12. Discrepancies classified by failure category (item 9)

1. **Extraction failure — funding-round evidence not routed to `funding_history`/`stage_signal`.**
   Claim "Linear reached a $1.25B valuation in June 2025 with over 15,000 companies... $82M Series C led
   by Accel" (libraryofllm.com) was tagged only `commercial_validation`/`growth_trajectory`. This is the
   single highest-impact finding of the run: it is the direct, traceable cause of BOTH the
   `Financial & Funding Signals` pillar's complete lack of evidence AND `Stage` resolving to
   `Undetermined`, despite the underlying fact being real, retrieved, and grounded.
2. **Extraction failure — founder background not routed to `founder_relevant_experience`.** The
   Airbnb/Coinbase claim (karrisaarinen.com) was tagged `leadership_composition`/`public_track_record`
   only. Directly comparable to the prior manual fixture's own correct tagging of the identical
   real-world fact (§11).
3. **Provenance/dedup failure — two independent corroborating sources of one fact not recognized as
   corroborating.** The YouTube-video-title claim and the First Round Review podcast-page claim both
   assert "Karri Saarinen is co-founder/CEO of Linear" from genuinely independent outlets, but landed in
   different `independence_group_id`s (one via `team_identity` missing `person_id`, one via the
   text-fallback path) rather than being recognized as two corroborating instances of the same fact.
4. **Acquisition failure (probable) — no market-sizing report surfaced.** `market_definition_size`/
   `market_growth_signal` found zero claims this run, though a real, public, non-paywalled report exists
   (found by the manual fixture via a different search). Classified "probable," not certain — Tavily's
   `search_depth="basic"`/`max_results=5` may simply not have surfaced an equivalent source this
   particular run; this is a plausible single-run acquisition gap, not a demonstrated structural defect.
5. **Acquisition failure (probable) — Linear's own changelog never retrieved.** `shipping_velocity`
   found zero claims despite `linear.app/changelog` being a real, public, crawlable page the manual
   fixture used directly. The `execution_and_shipping` topic's own query ("Linear changelog product
   launch release") is a reasonable query for this; whatever Tavily returned for it either didn't include
   the changelog or didn't survive retrieval/extraction this run.
6. **Extraction quality (minor) — one claim's relevance is questionable despite being technically
   grounded** (§10, the dev.to hobbyist-tool claim feeding `differentiation_claim_corroboration`).
7. **Extraction quality (minor) — an over-broad excerpt.** The `linear.app/about` claim's `excerpt`
   is the entire page (~200 employee names, full investor list), not a minimal relevant quote — still a
   literal substring (passes grounding), just far noisier than useful.
8. **Extraction observation — low `structured_fact` population rate (3/18, 17%).** Several claims that
   plausibly warranted a typed fact (the funding round, the customer/churn counts, the NRR figure) were
   extracted as free text only, meaning even a correctly-routed version of some of these claims might
   still have landed in a Classified rather than Computed evaluation path.
9. **Expected withholding — `competitive_landscape_position` correctly stayed Unscored.** 5 claims were
   tagged for this dimension, but only one carried `structured_fact.kind=="competitive_structure"`, and
   its own `value` ("15% adoption rate") is an adoption statistic, not a "fragmented"/"concentrated"
   structural read — so the methodology's own, deliberately conservative classifier (Task 13's own
   design: never guess market structure from a bare competitor list) correctly returned
   `NOT_ESTABLISHED`. **This is the system working as designed, not a defect** — included here so it is
   not confused with the genuine failures above.
10. **No methodology-limitation finding this run.** Every pillar-level outcome traces cleanly to either a
    genuine acquisition/extraction gap (above) or a correct, conservative Unscored result; nothing
    observed suggests the scoring/gating formulas themselves misbehaved given the evidence they received.

## 13. Security observations (item 14)

- **No source content contained instruction-like text directed at the extractor.** All 18 accepted
  excerpts are ordinary marketing/analyst/blog prose; none resembled a prompt-injection attempt.
- **Source content never influenced `source_type`.** Confirmed structurally (unchanged from Task 21A):
  `classify_source_type()` is a pure function of two URLs, never given page content: `linear.app/about`
  → `company_disclosure`; every other domain → `independent_reporting` by the conservative default,
  regardless of what any page said about itself.
- **No methodology-manipulation attempt observed** in any retrieved content.
- **SSRF protections:** no rejection fired this run — no malformed or unsafe URL appeared in Tavily's own
  results this time; the two real failures (HTTP 403/429) were ordinary site-side responses, not
  security-boundary rejections, and were handled by the existing graceful-degradation path exactly as
  designed.
- **No source content escaped the untrusted-data boundary** — every extracted claim's own `excerpt`
  field is a passive, quoted piece of data; nothing indicates the model treated any source text as an
  instruction (no out-of-vocabulary dimension, no disallowed structured-fact field, no fabricated score
  appeared in the output).

## 14. External failures / retries (item 18, exact)

- Search: 0 failures, 0 retries (12/12 succeeded first attempt).
- Retrieval: 2 distinct URL failures (4 failed records — each URL's own 2 allowed attempts both failed),
  22/24 attempted URLs ultimately succeeded.
- Extraction: 0 failures, 0 retries (6/6 batches succeeded first attempt, 0 validation retries, 0
  content-filter/length events).

## 15. Known limitations exposed by this run (item 19)

- **Assessment-criteria routing is the weakest link observed** — grounding, source-type classification,
  and the deterministic scoring/gating machinery all behaved correctly; the two extraction-failure
  findings above (funding round, founder background) are squarely about the model choosing the wrong
  `assessment_criteria` tag(s) for a fact it otherwise extracted, grounded, and typed correctly.
- **Structured-fact population is inconsistent** — present for only 3/18 claims, limiting how many
  Computed-category dimensions could ever have scored even with perfect routing.
- **Independence-group-id assignment for `team_identity` facts is fragile** when the model omits
  `person_id` (the one field that table actually keys on) in favor of `named_entity`/`role` alone.
- **One run cannot distinguish "Tavily didn't surface X this time" from "X is genuinely hard to find
  publicly"** — the two probable-acquisition-failure findings (market report, changelog) are honestly
  labeled "probable," not confirmed, because this task's own rules forbid a second run to check.
- **No dollar-cost figure exists for this or any future run** unless a `ProviderPricing` is explicitly
  configured — this was known before the run and remains true after it.

## 16. Engineering state (item 20)

**State B — Acquisition fixes required.** The deterministic core (grounding validation, source-type
classification, contradiction detection, publication gates, Strength/Coverage/Confidence computation) all
behaved exactly as designed against whatever evidence reached them — zero methodology concerns were
found. The limiting factor is squarely upstream: real, retrievable, correctly-grounded evidence existed
and was extracted, but a meaningful share of it (the funding round, the founder background) was tagged to
the wrong dimension, and two other dimensions likely went unsearched-for effectively (market sizing,
changelog). This is not a provider-integration failure (D) — every provider call succeeded, cleanly, on
the first attempt, for the entire run. It is not a methodology issue (C) — nothing about the scoring or
gating logic itself produced a questionable result given its actual inputs. It is closer to "ready for
broader calibration" (A) than not, but the two concrete, well-evidenced extraction-routing failures are
exactly the kind of "one or more concrete acquisition/extraction/provenance defects" B is defined by, and
they are worth fixing (in a separate, explicitly-scoped task, not this one) before spending further live
runs on additional companies.

## 17. Recommended single next engineering task

**Improve the OpenAI extraction system prompt's `assessment_criteria` routing guidance for facts that
plausibly span multiple dimension families** (most concretely: any funding-round mention must always
include `funding_history` and, when a stage-defining amount/round-type is present, `stage_signal`; any
biographical/prior-employer claim about a named person already established as a founder/executive must
always include `founder_relevant_experience` alongside `leadership_composition`/`public_track_record`) —
and secondarily, tighten the `team_identity` structured-fact guidance so `person_id` is populated
whenever a `team_identity` fact is emitted, so independence-group-id assignment can actually key on it.
This is a prompt-content change only, explicitly not a methodology, validation, or scoring change, and
should be verified with mocked tests before any second live run is requested.

## 18. What was preserved vs. what was not committed

This document is a curated summary built from the real run's full captured output. Per item 6's own "do
not dump huge raw webpages into the repository," full raw retrieved-page content is not reproduced here
(the pipeline itself never persists it beyond one run in any case — only `Claim.excerpt`, already a short,
grounded quote, survives into the ledger). The complete machine-readable capture (every claim in full,
every telemetry record, every stage timing) was written to this session's own scratchpad directory during
the run and is available for a follow-up task to inspect if useful, but was never committed to this repo.
No API key or other credential appears anywhere in this document or in the scratchpad capture.
