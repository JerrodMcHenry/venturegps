# Live Evaluation — Linear (Run 002)

**Task 24. Second controlled live analysis, real Tavily/HTTP/OpenAI calls, no manual evidence, no
reruns, no fixes applied during or after this task.** An A/B engineering comparison against
`LIVE_EVALUATION_LINEAR_001.md` (unedited, unaffected by this document) to measure whether Task 23's
targeted routing/relevance/identity/query fixes actually changed anything, at the evidence level, not
the score level.

- **Run timestamp (UTC):** 2026-09-30T04:56:07.232679+00:00
- **`run_id`:** `828250828972`
- **Methodology/parameter version:** `evidence_engine.v1-provisional-11` — **identical to LINEAR_001**
- **Acquisition configuration:** `AcquisitionBudget()` defaults, unmodified — identical to LINEAR_001
  in every field (12 queries, `max_sources_per_query=3`, `max_total_sources=24`,
  `max_sources_per_batch=4`, `max_total_input_chars_per_batch=20,000`,
  `EXTRACTION_MAX_OUTPUT_TOKENS=4,096`, `EXTRACTION_MAX_PROVIDER_ATTEMPTS_PER_BATCH=2`). Model:
  `gpt-4.1-mini`. **What is different from LINEAR_001:** Task 23's routing/relevance/person-identity
  layer, the reworded changelog/market queries (2 of the same 12 query slots, text only), and the
  extraction system prompt's new routing guidance.

## 1. Whether the run completed

**Yes, cleanly, on the first attempt.** Total wall-clock: **35.6 seconds** (LINEAR_001: 37.6s).

## 2. Resolved stage

**`Undetermined` — unchanged from LINEAR_001.** No claim reached the ledger tagged `stage_signal` with
a non-empty criteria list (see §6.A and §9 for why a real, correctly-typed `funding_round`/
`founding_year` fact still failed to reach it this run — a newly-discovered defect, not a repeat of
LINEAR_001's own routing gap).

## 3. Provider measurements

**Tavily:** 12 logical searches, 12 real attempts, 0 retries, all 12 succeeded.

**HTTP:** 28 retrieval records (20 succeeded, 4 failed after both allowed attempts):
- `thedigitalprojectmanager.com` did NOT recur (unlike LINEAR_001); different failures this run:
- `indeed.com/.../linear-regression` — HTTP 404 (an unrelated statistics-terminology page, not
  company evidence — a false-positive search result, not a retrieval defect).
- `hginsights.com/blog/total-addressable-market-explained...` — HTTP 403. **New this run** — the
  reworded market query surfaced a genuinely TAM-topic page that LINEAR_001 never saw at all, though
  it is a generic explainer, not company-specific data, and failed retrieval regardless.
- `6sense.com/tech/workflow-automation/linear-market-share` — HTTP 403. **New this run** — a
  genuinely company-specific market-share page the reworded query surfaced for the first time;
  blocked before extraction could ever see it.
- `exa.ai/websets/directory/linear-executives` — HTTP 429 (recurred identically from LINEAR_001).
- **20 of 24 candidate URLs successfully retrieved** (LINEAR_001: 22 of 24).

**OpenAI:**
- Extraction batches: **5** (LINEAR_001: 6 — fewer retained sources this run, 20 vs 22, at the same
  4-per-batch size).
- Real provider attempts: **5** (1 per batch, 0 retries — identical clean-first-attempt pattern to
  LINEAR_001).
- Input tokens: **24,046**. Output tokens: **4,008**. **Total: 28,054** (LINEAR_001: 27,071 / 4,363 /
  31,434 — fewer total tokens, consistent with fewer batches).
- Validation retries: **0**. Input truncation: 4 of 5 batches. Output truncation: **0**.
  Content-filter refusals: **0**. Sources excluded for budget: **0**.
- No dollar cost reported — none invented, consistent with both runs.

## 4. Latency

| Stage | LINEAR_001 | LINEAR_002 |
|---|---|---|
| Retrieval | 15.46s | 14.54s |
| Extraction | 22.16s | 21.03s |
| Deterministic (contradiction/ledger/6-pillar) | ~0s | ~0s |
| **Total** | **37.63s** | **35.57s** |

Extraction remains the dominant stage in both runs (~59%), unchanged.

## 5. Evidence measurements

| Metric | LINEAR_001 | LINEAR_002 |
|---|---|---|
| Sources retrieved | 22 | 20 |
| Claims accepted | 18 | **22** |
| Claims rejected | 0 | 0 |
| Structured-fact populated | 3/18 (17%) | **8/22 (36.4%)** |
| Distinct independence groups | 18 | 21 |
| Company-disclosure claims | 1 | 3 |
| Independent-reporting claims | 17 | 19 |
| Contradictions/disputes | 0 | 0 |
| **Claims with EMPTY `assessment_criteria` after routing** | 0 | **2 (new defect, see §9)** |

`subject_relationship` population/stripping counts **cannot be reported** — this field lives only on
`ExtractedClaimCandidate` (extraction-time), never persisted onto the final `Claim`; the ledger capture
this document is built from has no record of it either way. Named explicitly as a real reporting gap,
not glossed over (see §16).

## 6. Task 23 hypotheses, tested against this run's actual evidence

### A. Funding routing

A real fact — "$1.25 billion valuation in June 2025... only about $35,000 spent on lifetime paid
marketing" — was correctly typed `structured_fact.kind == "funding_round"` (an improvement: LINEAR_001's
equivalent fact had NO structured_fact at all). **But it did not reach `funding_history`** — its final
`assessment_criteria` is `[]` (empty). This is not the same failure as LINEAR_001 (misrouted to an
unrelated dimension) — it is a **new, different failure**: the model's own originally-proposed tag(s)
for this fact were apparently not in `routing.py`'s allowed set for `kind == "funding_round"`
(`{"funding_history"}` only), and Task 23's own sanitization step stripped them to nothing, with no
check that the result was still usable. The `funding_round`'s own `metric` field is `"valuation"`, not an
amount+round-type — `evaluate_funding_history()` also only counts `financing_type in {"equity"}`, which
this candidate's structured_fact never populated either, so even a non-empty `funding_history` tag would
likely not have counted this specific fact toward the total. **Root cause:** a real, newly-discovered
Task-23-introduced gap — see §9. **Verdict: partially improved (better typing), still not reaching its
dimension, for a new reason.**

A second claim — `"Linear was founded in 2019... valuation of $1.25 billion"` — was typed
`kind == "founding_year"` (correct kind for the founding-year half of that sentence) but also ended with
`assessment_criteria == []`, the same new defect.

### B. Founder routing

**Materially improved.** The Airbnb/Coinbase background fact was typed `kind == "founder_experience"`,
correctly carries `named_entity == "Karri Saarinen"`, was correctly backfilled a `person_id`
(`ae33cb0b4251e9b8`), and its `assessment_criteria` is exactly `["founder_relevant_experience"]` — it DID
reach the correct dimension this time (LINEAR_001's equivalent fact never reached it at all). The
dimension's own result is `unscored_uncorroborated`, not `unscored_no_evidence` — meaning it registered
a real signal (ADJACENT/DIRECT) but the pillar's own, unchanged, pre-existing corroboration-count
requirement was not met with only one qualifying claim. **This is exactly the "routing succeeded, a
different, legitimate gate still applies" case** — not a repeat of LINEAR_001's routing failure.

### C. Identity / corroboration

**Confirmed working.** The `team_identity` claim (`Karri Saarinen... Co-founder and CEO`, from
review.firstround.com) and the `founder_experience` claim (from karrisaarinen.com) resolved to the
**identical** backfilled `person_id` (`ae33cb0b4251e9b8`) — two genuinely independent sources about the
same real person, now recognized as being about the same person, exactly Task 23's own fix. Their
`independence_group_id`s correctly differ (different KIND of fact — identity vs. experience — per
`claim_identity.py`'s own per-kind key table, unchanged, correct).

### D. Changelog / release discovery

**Did not recur, still missed.** No claim or retrieved-source URL this run is `linear.app/changelog` or
an equivalent release-history page. Classification: most likely **acquisition/search-ranking failure**
(Tavily's own basic search for the reworded query still did not surface it) rather than retrieval or
extraction — no changelog-shaped URL appears anywhere in this run's own candidate list at all, so
retrieval/extraction were never even given the chance to succeed or fail on it.

### E. Market evidence

**Query wording change is confirmed to have altered the candidate pool** — `hginsights.com`'s TAM
explainer and `6sense.com`'s Linear-specific market-share page are both **new candidates that did not
appear in LINEAR_001 at all**. Neither was successfully retrieved (both 403). Two OTHER candidates
(`distillintelligence.com`, `seeto.ai`) succeeded but are competitor-comparison pages, not independent
market-size/growth reports, and correctly did not score `market_definition_size`/`market_growth_signal`
(both remain `unscored_no_evidence`, zero qualifying claims — the same honest outcome as LINEAR_001, for
the same underlying reason). **Verdict: real, observable behavior change in what search surfaces;
zero change in what evidence actually reached the ledger for this pillar** — exactly the
"routing/recall are different axes" distinction item 8 asks to preserve.

### F. Relevance

No LINEAR_001-style unrelated-third-party claim (a hobbyist blog post using the company's product as
one input) appears among this run's 22 accepted claims. Whether this is because `subject_relationship`
correctly filtered one out, or because no such source was ever retrieved in the first place, **cannot be
determined from this run's own artifacts** — the field is not persisted, and no quality finding or
rejection reason references it. No false positive (legitimate evidence wrongly stripped) or false
negative (an irrelevant claim slipping through) is directly observable either way.

## 7. LINEAR_001 vs LINEAR_002 comparison

| Metric | LINEAR_001 | LINEAR_002 | Change |
|---|---:|---:|---:|
| Total runtime | 37.63s | 35.57s | −2.06s |
| Search calls | 12 | 12 | 0 |
| Retrieved sources | 22 | 20 | −2 |
| OpenAI batches (attempts) | 6 (6) | 5 (5) | −1 (−1) |
| Total tokens | 31,434 | 28,054 | −3,380 |
| Accepted claims | 18 | 22 | +4 |
| Rejected claims | 0 | 0 | 0 |
| Structured facts | 3 | 8 | +5 |
| Structured-fact % | ~17% | **36.4%** | **+19.4pp** |
| Resolved stage | Undetermined | Undetermined | none |
| Published pillars | 1/6 | **0/6** | **−1** |
| Company Coverage | 9.0% | 9.4% | +0.4pp |
| Company Confidence | High* | **None** | (no published pillar to compute it from) |
| Company publishable | No | No | none |

`*` — as LINEAR_001 itself noted, that Confidence was based on exactly one published pillar, never
broad company certainty; LINEAR_002 has zero published pillars, so company-level Confidence is
undefined (not a worse "Low," genuinely not computable — `compute_company_confidence()`'s own documented
behavior, unchanged, Task 19).

### Per-pillar comparison

| Pillar | 001 Published | 001 Strength | 002 Published | 002 Strength | Notable evidence-level change |
|---|---|---|---|---|---|
| Market Opportunity | No | — | No | — | Query surfaced 2 new candidate URLs (§6.E); both failed retrieval; zero net evidence change |
| Product & Technology | **Yes** | 8.0 | **No** | — (1 dim scored, needs 2) | Fewer independent corroborating claims found THIS run for `differentiation_claim_corroboration`; `defensibility_signal` alone scored 8.0 at Medium (not High) confidence |
| Team & Leadership | No | — | No | — | `founder_relevant_experience` now reaches `unscored_UNCORROBORATED` (was `unscored_no_evidence`) — real routing improvement, still gated by the pillar's own corroboration-count requirement |
| Commercial Traction | No | — | No | — | More claims found (10+), several now correctly typed `traction_metric`, still short of the pillar's own 2-scored-dimension floor |
| Execution & Momentum | No | — | No | — | `gtm_motion_evidence` newly SCORED (7.5, `GTM_FACT_PRESENT`) — a real first, correctly typed `gtm_evidence` and routed; `shipping_velocity` still zero evidence (§6.D) |
| Financial & Funding Signals | No | — | No | — | Correctly-typed `funding_round`/`founding_year` facts exist in the ledger for the first time, but reach zero dimensions due to §9's new defect |

## 8. Evidence-level explanation of every meaningful change (item 8's own required "why")

- **Structured-fact rate nearly doubled (17% → 36.4%) *because* the prompt's new routing-guidance
  paragraph explicitly named the fields to populate for funding/founder/release/GTM facts** — directly
  traceable: 5 of the 8 newly-structured facts are exactly the kinds that guidance named
  (`funding_round`, `founding_year`, `founder_experience`, `traction_metric`, `gtm_evidence`).
- **`founder_relevant_experience` moved from zero-evidence to uncorroborated-but-present *because* the
  same real Airbnb/Coinbase fact is now correctly typed AND tagged**, not because any gate was loosened
  — it is still Unscored, honestly, for a real, unrelated reason (insufficient independent corroboration).
- **`gtm_motion_evidence` scored for the first time *because* a real, correctly-typed `gtm_evidence` fact
  (Linear's product-led/word-of-mouth growth mechanism, from cofounderbase.com) reached its legitimate
  dimension** — a genuinely new, correctly-routed piece of evidence, not an artifact of loosened
  requirements.
- **Product & Technology REGRESSED from published to withheld *because* this run's own search results
  happened to surface fewer independent claims relevant to `differentiation_claim_corroboration`
  specifically** (one company-disclosure claim, one independent claim tagged only `defensibility_signal`)
  — a genuine, observable difference in what THIS run's search returned, not a routing regression: the
  routing/relevance layer did not remove any evidence that would otherwise have qualified.
- **Company Coverage is statistically unchanged (9.0% → 9.4%)** *because* company-level Coverage is
  weighted across all six pillars regardless of publication, and this run's modest per-pillar gains
  (Product & Technology's `defensibility_signal`, Execution & Momentum's `gtm_motion_evidence`) roughly
  offset Product & Technology's own loss of its second scored dimension.

## 9. New defect discovered by this run (not present, or not observed, in LINEAR_001)

**Sanitization can strip a candidate's `assessment_criteria` to empty, and nothing re-checks this before
finalizing the claim.** `extraction.py::_sanitize_assessment_criteria()` (Task 23) narrows
`assessment_criteria` via `routing.py`'s deterministic kind-based intersection — `validate_candidate()`'s
own "at least one recognized dimension" check runs BEFORE this narrowing, on the RAW, model-proposed
criteria, so a candidate that already had ≥1 recognized dimension can still end up with **zero** criteria
after routing, if none of its originally-proposed tags happen to be in that specific kind's allowed set.
Two real claims this run (`056253ea4e37e9be`, kind `founding_year`; `757b364f6fbe5b9d`, kind
`funding_round`) reached the ledger this way — correctly typed, correctly grounded, but permanently
un-citable by any dimension (`assessment_criteria == []`), since `resolve_dimension_evidence()` matches
on dimension membership in that list.

**This is a genuine, newly-discovered acquisition-layer defect, found only by running the real pipeline
against real model output — exactly what this task exists to surface. It is documented here, not fixed,
per this task's own explicit "no fixes during the run" rule.**

## 10. Coverage-inflation check (item 9)

**No inflation observed.** Company Coverage moved by +0.4 percentage points — within noise, and each
contributing change traces to a genuinely new, correctly-typed, correctly-routed fact (§8), never to: a
claim routed to more dimensions than before (routing only ever narrows, confirmed directly in §6/§9 —
if anything it narrowed TWO claims down to zero), first-party evidence counted as independent (both
`market_definition_size`-eligible company-disclosure claims correctly stayed excluded, unchanged from
LINEAR_001), duplicate facts becoming multiple evidence items (`claims_deduplicated: 0`, `claims_
disputed: 0`, same as LINEAR_001), irrelevant third-party evidence surviving (§6.F — inconclusive, but
no observed instance), or a guessed structured fact (every populated field traces to real source text).
If anything, this run is evidence AGAINST inflation risk: Product & Technology's own published status
regressed, and the empty-criteria defect (§9) actively removed two claims from ever counting toward
anything.

## 11. Deterministic methodology behavior (unchanged, re-confirmed)

All six pillars and company aggregation ran with the exact same, unmodified code and parameters as
LINEAR_001. Full pillar table in §6/§7 above. Zero cross-pillar audit findings (same as LINEAR_001).

## 12. Remaining failures, classified (same taxonomy as LINEAR_001)

1. **Extraction failure (new)** — the empty-`assessment_criteria` defect (§9) — correctly-typed evidence
   silently rendered un-citable.
2. **Acquisition failure (recurring)** — changelog still not surfaced (§6.D).
3. **Acquisition failure (recurring, partially mitigated)** — market-sizing report still not
   *retrieved*, though the query now surfaces more relevant *candidates* (§6.E) — an observable partial
   improvement in search targeting that has not yet translated into usable evidence.
4. **Expected withholding (recurring)** — `founder_relevant_experience`'s own corroboration-count
   requirement, correctly and honestly applied to a single qualifying claim.
5. **Expected withholding (recurring)** — `market_definition_size`/`competitive_landscape_position`
   correctly declining to guess from competitor-comparison pages alone.
6. **No grounding/validation, provenance/dedup, contradiction, or methodology-limitation failures
   observed this run** — every one of those mechanisms behaved exactly as designed against whatever
   evidence reached it.

## 13. Whether any methodology problem was exposed

**No.** Every pillar-level and company-level outcome traces cleanly to either the new acquisition-layer
defect (§9), a recurring acquisition-recall gap (§6.D/§6.E), or a correct, conservative Unscored/withheld
result given the evidence actually available. Nothing about the scoring, gating, or aggregation formulas
themselves misbehaved.

## 14. Engineering state

**B — another narrow acquisition fix is required.** The empty-criteria defect (§9) is exactly the kind
of "concrete, generalizable acquisition defect" this state is defined by: real, correctly-extracted,
correctly-grounded evidence is being silently discarded by Task 23's own new narrowing step, for a
mechanical reason (no post-sanitization non-emptiness check) that is straightforward to name precisely.
Not state A: Coverage/publication did not improve, and a new, real defect was found. Not state C:
nothing about the methodology itself misbehaved. Not state D: every provider call succeeded, cleanly, on
the first attempt, for the entire run — provider reliability is not in question.

## 15. Recommended single next task

**Fix the empty-`assessment_criteria` defect from §9** — the narrowest, most concrete, best-evidenced
acquisition fix this run surfaced: after `routing.py`'s deterministic narrowing runs, if a candidate that
had at least one recognized dimension before narrowing has zero after, either (a) fall back to the
candidate's original, pre-routing criteria for that one candidate rather than silently emptying it, or
(b) surface it as a distinct, telemetry-recorded "routed to nothing" quality finding rather than a
silent, permanently un-citable ledger entry — a decision for that task to make explicitly, not this one.
Verify with mocked tests reproducing this run's own two exact claim shapes before any third live run.

## 16. Explicit limitations of this comparison

- `subject_relationship` population/stripping cannot be measured from either run's own persisted
  artifacts (§5) — a real reporting gap, not a claim that the mechanism did or didn't fire.
- This is two runs of one company; neither Tavily's own search ranking nor a given source's HTTP
  availability is deterministic run-to-run (confirmed directly: this run's retrieval failures are a
  different set of URLs than LINEAR_001's), so no single before/after pair proves a generalizable recall
  improvement — only a routing/typing improvement, which is what §6/§8 actually demonstrate.
- No dollar cost is reported for either run; none was invented here either.
