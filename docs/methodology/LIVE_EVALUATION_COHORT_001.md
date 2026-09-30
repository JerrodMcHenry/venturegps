# Live Evaluation — Diverse Cohort 001 (Task 26)

**Real Tavily/HTTP/OpenAI calls for 3 companies. No manual evidence, no reruns, no fixes applied
during or after this task.** This is the first cross-company measurement of the evidence-first
architecture — Linear 001/002 tested one company twice; this cohort tests whether what Task 25 fixed,
and what remains broken, generalizes.

## 0. Bullet — not run, and why

Task 26 required Bullet's canonical website URL be resolved from existing project artifacts, never
guessed, and explicitly instructed: *"If either canonical URL cannot be determined confidently from
existing project artifacts, do not run that company and report the issue. Do not substitute another
company."* An exhaustive search of `app/evidence_engine/live_research/bullet.py`,
`app/evidence_engine/live_research/run_evaluation.py`, and every methodology document referencing
Bullet found **no Bullet-owned domain anywhere in the repository** — every piece of curated evidence
for Bullet is sourced from a single third-party Hacker News launch thread
(`https://news.ycombinator.com/item?id=49283063`), never from a `bullet.*`-style homepage. Bullet was
therefore **not run**, per the task's own explicit instruction, and **no substitute company was run in
its place**. The cohort below is Stripe, Notion, and Fish Audio only (3 of the intended 4).

## 1. Cohort composition and pre-run freeze

| Company | Website | Canonical URL source |
|---|---|---|
| Stripe | `https://stripe.com` | Given directly in the task |
| Notion | `https://www.notion.com` | Given directly in the task |
| Fish Audio | `https://fish.audio` | Resolved from `live_research/fish_audio.py`'s own existing curated source URL (`https://fish.audio/developers/`) |

Pre-run checks (all confirmed before any external call): Task 25 present (`RoutingStatus`, 18
kind-eligibility entries); `evidence_engine.v1-provisional-11` unchanged; `parameters.py` zero diff;
`AcquisitionBudget()` defaults unchanged; routing/relevance telemetry active (`claim_routing`
populated per company, confirmed below); isolation boundary 3/3; `LIVE_EVALUATION_LINEAR_001.md`/
`LIVE_EVALUATION_LINEAR_002.md` both zero diff. Each of the three runs used the identical, unmodified
pipeline/budget/prompt/queries — no configuration change between companies.

## 2. Cohort comparison table

| Metric | Stripe | Notion | Fish Audio | *(Linear 002, reference — not rerun)* |
|---|---:|---:|---:|---:|
| Runtime | 26.5s | 27.7s | 25.8s | *35.6s* |
| Sources retrieved | 19 | 23 | 20 | *20* |
| Claims accepted | 12 | 23 | 18 | *22* |
| Structured-fact % | **75.0%** | 47.8% | 44.4% | *36.4%* |
| Routed claims | 10 | 18 | 13 | — |
| Context-only claims | 2 | 3 | 1 | — |
| Unrouted claims (insufficient structure + invalid) | 0 | 2 | 4 | — |
| Published pillars | 1/6 | 1/6 | 1/6 | *0/6* |
| Company Coverage | 9.0% | 9.0% | 13.5% | *9.4%* |
| Company Confidence | High | High | High | *None* |
| Company publishable | No | No | No | *No* |
| Total tokens | 25,953 | 32,551 | 26,358 | *28,054* |

**Every single company in this cohort, and both Linear runs before it — five real live runs in
total — published at most 1 of 6 pillars, and that one pillar is always Product & Technology.** This
is the cohort's own central, unavoidable finding, detailed in §7.

## 3. Evidence measurements (item 6, aggregated)

53 total claims across the 3 companies, **0 rejected anywhere in the cohort** (grounding/vocabulary
validation never once failed a candidate this cohort — every proposed candidate across 16 real
extraction batches was already well-formed enough to pass). Routing status distribution across all 53
claims: `routed` 41, `context_only` 6, `unrouted_insufficient_structure` 2, `rejected_invalid_routing`
4, `unrouted_no_methodology_consumer` 0. **Zero contradictions/disputes anywhere in the cohort.**
Source-type composition: **50 `independent_reporting` (94.3%), 2 `product_documentation` (3.8%), 1
`company_disclosure` (1.9%)** — see Question F.

## 4. Routing completeness audit (item 7)

**Every one of the 6 non-`routed` claims across the cohort has a specific, inspectable, non-empty
`RoutingDecision.reason`.** None required guessing or inference to explain — each was read directly
from `AcquisitionTelemetry.claim_routing`. Breakdown:

| Company | Claim | Kind | Status | Why |
|---|---|---|---|---|
| Notion | founding_year (2016) | `founding_year` | `REJECTED_INVALID_ROUTING` | Proposed `public_track_record`, categorically outside eligible (`stage_signal`) |
| Notion | funding_round ($344.1M) | `funding_round` | `UNROUTED_INSUFFICIENT_STRUCTURE` | Correctly proposed `funding_history`, but missing `financing_type`/`round_date`/`status` |
| Fish Audio | founding_year (1986, unrelated company — §12) | `founding_year` | `REJECTED_INVALID_ROUTING` | Proposed `competitive_landscape_position`/`timing_catalyst`, categorically outside eligible |
| Fish Audio | funding_round_type ("unfunded", unrelated company) | `funding_round_type` | `REJECTED_INVALID_ROUTING` | Same as above |
| Fish Audio | funding_round (#1, $52M) | `funding_round` | `REJECTED_INVALID_ROUTING` | Proposed `public_track_record` only |
| Fish Audio | funding_round (#2, $52M) | `funding_round` | `UNROUTED_INSUFFICIENT_STRUCTURE` | Correctly proposed `funding_history`; `financing_type="Seed"` (a round label, not the required `"equity"` legal structure) |

**No claim's outcome could not be explained.** This is a clean, confirmed pass of item 7's own explicit
test.

## 5. Evidence-quality audit (item 8, cohort-wide)

- **Grounding:** no issue found in any of the 53 claims — every excerpt genuinely supports its own
  claim_text across all three companies.
- **Target relevance:** one genuine issue — Fish Audio's two "Big Fish Audio" claims (§12), a
  different, real company conflated by name similarity. No `subject_relationship`-flagged issue
  observed (cannot be fully confirmed either way — the field is not persisted onto `Claim`, a known,
  documented limitation since Task 25).
- **Fact typing:** correct in every structured-fact-bearing claim inspected (18/18 across the cohort
  used a real, recognized kind matching what the claim actually describes).
- **Structured representation:** THE cohort's central weakness — see §7.
- **Routing:** 100% explained, §4.
- **Provenance/independence:** correct in every case checked, including Fish Audio's own real
  duplicate-source pair (§12) and Stripe's own real Wikipedia/chargeback.io pair — both genuinely
  independent restatements correctly recognized as the same fact.
- **Contradictions:** none arose this cohort to evaluate.

## 6. Comparison against curated evidence (item 9, summary — full detail in each per-company report)

All three companies' curated fixtures (Tasks 13-19) cover multiple pillars each; all three live runs
scored only Product & Technology. Each per-company report documents specific rediscovered, missed, and
newly-found evidence. Pattern: **live runs consistently find real, new, plausible evidence the
curated fixtures (built earlier) did not have, especially for recent commercial-traction and funding
facts — but consistently fail to convert that evidence into a scored dimension outside Product &
Technology**, for the structural reasons in §7.

## 7. Cross-company patterns — the most important section

### SYSTEMIC — confirmed across all 3 companies (and both Linear runs)

**Finding S1 (the cohort's central finding): structured facts are typed and routed correctly, but
consistently lack the exact field values their own consuming dimension requires.** Read directly from
the real pillar code, confirmed against real extracted claims from all three companies:

- `commercial_traction.py::_parse_scale_point()` requires `metric` to EXACTLY match
  `{"revenue","arr","gmv","bookings","active_users","paying_customers"}`, `value_type == "actual"`
  literally, and `amount` to parse as a bare `float()`. Real extracted values across the cohort:
  `"annual revenue"`, `"annual recurring revenue"`, `"users"`, `"paying customers"` (none match);
  `value_type` populated on **zero** of the cohort's traction_metric claims; amounts like `"400
  million"`/`"21 million"` (none parse as float). **Every single `traction_metric` claim in this
  cohort that reached `disclosed_scale`/`growth_trajectory` failed to score for one or more of these
  three reasons** — confirmed for Notion (4 claims) and Fish Audio (2 claims).
- `financial_funding.py::funding_round_fields_are_sufficient()` requires `financing_type ==
  "equity"`. Real extracted values: `"Seed"` (Fish Audio, both claims) — **the model is populating
  `financing_type` with the ROUND LABEL (Seed/Series A/etc.) rather than the LEGAL FINANCING
  STRUCTURE (equity/debt/grant) the field actually means** — a genuine, precise, previously-
  undocumented prompt-clarity gap, found for the first time with full clarity by Fish Audio.
- `stage.py::resolve_stage()` reads `structured_fact["value"]` for `founding_year`; the extracted
  field across the cohort is consistently `"amount"` instead (confirmed for Notion and Fish Audio,
  the exact same mismatch `LIVE_EVALUATION_LINEAR_002.md` first found for Linear).
- `team_leadership.py`'s `founder_experience`/`track_record` classifiers require a categorical
  `value` (`ADJACENT`/`DIRECT`, `PRIOR_VENTURE_ROLE`/`PRIOR_EXIT`) — **zero** of the cohort's
  `founder_experience` claims (Stripe ×2) populate it at all, despite correct typing and correct
  routing.
- `commercial_traction.py`'s `retention_signal` classifier requires a categorical `value`
  (`WEAK`/`MODERATE`/`STRONG`) — Stripe's one `retention_signal` claim carries `amount`/`metric`
  instead.

  **This is one unifying root cause, not five separate bugs:** the extraction prompt asks the model
  for descriptive fields (amount, metric, named_entity, role, period_date) it reliably populates, but
  does not clearly enough distinguish them from the small set of CATEGORICAL fields (`value`,
  `value_type`, `financing_type`, `status`) each dimension's own classifier actually gates on, nor
  constrain `metric`'s own vocabulary to the exact strings the parsers expect.

**Finding S2: Financial & Funding Signals has never once scored a dimension across five real live
runs** (both Linear runs, Stripe, Notion, Fish Audio) — directly downstream of S1 (`funding_round`
evidence exists in 4 of 5 runs, always insufficiently structured the same way).

**Finding S3: Product & Technology is the only pillar that has ever published across five real live
runs**, and always via the same two kind-agnostic, free-text, corroboration-count-based dimensions
(`differentiation_claim_corroboration`/`defensibility_signal`) that Task 23 specifically identified as
having no positive structural gate at all — the two dimensions with the LEAST structural requirements
are the only ones evidence-density differences (Stripe/Notion vs. Fish Audio, well-funded vs.
early-stage) have ever been able to move.

**Finding S4: retrieval failures are overwhelmingly HTTP 403 (site-side bot-blocking), not SSRF
rejections or malformed URLs** — 9 of 10 cohort-wide retrieval failures across Stripe/Notion/Fish
Audio are 403s from third-party analytics/comparison sites (`getapp.com`, `6sense.com`,
`comparably.com`, `appsruntheworld.com`, `salesintel.io`, `traded.co`, `mlq.ai`, `pitchbook.com`), the
tenth a genuine HTTP 202 (Fish Audio). No security-boundary issue anywhere; this is ordinary anti-
scraping behavior from sites this engine has no relationship with.

### COMPANY/SOURCE-SPECIFIC

**Finding C1 (Fish Audio only): name collision with an unrelated real company** — Tavily's own search
surfaced "Big Fish Audio" (a 1986-founded, unrelated sample-library company) for a funding-related
query, purely on name similarity. Both resulting claims correctly stayed unscored (for the same S1/S2
reasons, incidentally), so no incorrect score resulted — but this is a real, distinct failure mode
(entity disambiguation) neither routing.py nor relevance.py currently addresses; `subject_relationship`
covers a third party DISCUSSING the target company, not a DIFFERENT company sharing its name.

**Finding C2 (none observed this cohort):** no company-specific SSRF rejection, malformed URL, or
provider-instability issue.

### EXPECTED LIMITATIONS

Market Opportunity scoring zero dimensions across all three companies is consistent with — not
contradictory to — this engine's own standing "no reputation-based calibration, no self-published TAM"
discipline: no independent market-sizing REPORT (as opposed to a competitor-comparison page) was ever
successfully retrieved for any of the three companies this run, an honest acquisition gap, not a
methodology defect (§13, Question G).

### METHODOLOGY LIMITATIONS

None identified this cohort beyond what LINEAR_001/002 already found and Task 25 already addressed —
every observed withholding traces to acquisition/extraction completeness (S1-S4), never to a
questionable scoring/gating decision given the evidence actually available.

## 8. Answers to the specific questions (item 13)

### A. Is public-web acquisition viable?

**Partially.** All three companies retrieved real, grounded, zero-rejection evidence and reliably
scored at least one meaningful dimension (Product & Technology) — the pipeline itself (search →
retrieval → structured extraction → routing → ledger → six pillars) runs end-to-end, cleanly, on real
data, for a well-known enterprise company, a well-known consumer/productivity company, and a genuinely
obscure early-stage startup alike. It is NOT yet viable for a useful MULTI-pillar assessment — Finding
S1/S2/S3 show the structural-completeness gap is the actual blocker, not source discovery.

### B. Does evidence density behave sensibly?

**Yes, where it can be observed.** Fish Audio (the sparsest, earliest-stage company) achieved the
HIGHEST company Coverage (13.5%) of the cohort — not because it had more evidence overall (it had
fewer sources than Notion), but because its own product-documentation/company-disclosure pages
legitimately contributed to `product_existence_maturity` scoring, a dimension Stripe/Notion never
scored. Evidence density is not being misread as poor performance anywhere in this cohort — every
withholding traces to a specific, honest, named reason (S1/S2), never a default-to-low-score.

### C. Is routing now reliable?

**Yes, unambiguously.** §4's own audit found zero unexplained outcomes across 53 real claims. Every
routing decision — success or failure — is precisely attributable. Task 25's own objective is fully
met by this cohort's evidence.

### D. Is structured extraction reliable?

**No — this is now the clearly-identified primary bottleneck.** Structured-fact population itself is
reasonably common (44-75% across the cohort, cohort-wide 52.8%), but the POPULATED fields are
frequently not the ones each dimension's own classifier actually requires (S1). Extraction reliably
produces typed, well-grounded, well-routed facts; it does not yet reliably produce SCORABLE facts.

### E. Is search recall the dominant remaining bottleneck?

**No, not anymore — extraction/structuring completeness (S1) now dominates.** Where real evidence was
clearly retrieved (funding rounds for Notion and Fish Audio, founder background for Stripe), it still
failed to score, for field-completeness reasons unrelated to whether it was found. Search recall
remains a real, separate, partially-open question (Market Opportunity's own zero-dimension result
across the cohort is more plausibly a recall gap than a structuring one — no market-sizing-shaped
source was ever successfully retrieved at all, as opposed to being retrieved-but-malformed).

### F. Are first-party sources overrepresented?

**No — the opposite.** Cohort-wide source-type composition: 94.3% `independent_reporting`, 3.8%
`product_documentation`, 1.9% `company_disclosure`. First-party (company-controlled) sources are
substantially UNDER-represented relative to independent third-party reporting, not over-represented.

### G. Is the engine appropriately conservative?

**Yes.** Fish Audio's own withholding pattern (0/6 published except Product & Technology, same as the
two much larger companies) reflects genuinely sparse/insufficiently-structured evidence, not an
arbitrary low score — no dimension anywhere in the cohort was scored on a guess, and the one dimension
that DID distinguish Fish Audio from the other two (`product_existence_maturity`, scored only for Fish
Audio) did so because real, qualifying evidence existed, not because of any stage-based leniency.

### H. Are there methodology problems?

**No new ones found this cohort.** Every correctly-acquired, correctly-routed piece of evidence
produced a defensible methodology outcome; every gap traces to acquisition/extraction (S1-S4), not to
scoring/gating logic itself.

## 9. Failure classification counts (item 14)

| Category | Count | Notes |
|---|---:|---|
| Acquisition failure | 3 | Market-sizing report never retrieved for any of the 3 companies |
| Retrieval failure | 10 | All ordinary site-side blocks (9× HTTP 403, 1× HTTP 202), 0 SSRF |
| Extraction failure | 0 | No malformed/hallucinated candidate observed |
| Grounding/validation failure | 0 | 0 rejections across the entire cohort |
| Routing failure | 0 | Every non-ROUTED outcome is a real, explained UNROUTED/REJECTED state, not a routing defect |
| Relevance failure | 1 (possible) | Fish Audio's Big Fish Audio name collision (C1) — not a `subject_relationship` mechanism failure, a distinct entity-disambiguation gap |
| Provenance/dedup failure | 0 | Both real duplicate pairs (Stripe, Fish Audio) correctly recognized |
| Contradiction failure | 0 | None arose |
| Methodology limitation | 0 | None found |
| Expected withholding | 15 | Every non-Product-&-Technology pillar across all 3 companies (5 pillars × 3 companies) |

## 10. Engineering state (item 15)

**B — one systemic acquisition defect needs remediation first.** Finding S1 is exactly this: a single,
repeated, generalizable acquisition/extraction-completeness problem (categorical/classifier-required
fields not reliably populated, distinct from the kind/dimension-routing question Task 25 already
solved) that materially prevents useful multi-pillar analysis across every company in this cohort, not
one. It is not state A (acquisition is not yet sufficiently reliable for broader calibration — every
company published only 1 of 6 pillars). It is not state C (no methodology defect was found — every
outcome given the evidence actually available is defensible). It is not state D (search, retrieval, and
routing all worked; the pipeline is not failing to obtain evidence, it is failing to structure evidence
it already obtained).

## 11. Recommended single next engineering task

**Strengthen the extraction system prompt's field-completeness guidance for the specific categorical/
classifier-required fields Finding S1 identified** — explicitly distinguish `financing_type` (legal
structure: equity/debt/grant) from round label (Seed/Series A, which belongs in `funding_round_type`'s
own `value` field); explicitly require `value_type: "actual"` whenever a real, current (non-projected)
figure is stated; constrain `metric` to the exact recognized vocabulary
(`revenue`/`arr`/`gmv`/`bookings`/`active_users`/`paying_customers`, not a paraphrase); and add the
missing categorical-value guidance for `founder_experience`/`track_record`/`retention_signal`. This is
a prompt-content-only change (mirroring Task 23's own prior successful prompt work), explicitly not a
methodology, routing, or parser change — verify with mocked tests reproducing this cohort's own exact
real field shapes before any fourth live run.
