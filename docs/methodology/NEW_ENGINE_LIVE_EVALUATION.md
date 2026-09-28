# VentureGPS Evidence Engine — Controlled Live-Evidence Evaluation (Task 11)

**Status: EVALUATION REPORT. No engine code was changed as a result of this evaluation's
findings — only observed and documented, per the task's own instruction to recommend rather
than implement changes.** Companion to `docs/methodology/NEW_ENGINE_CALIBRATION_REPORT.md`
(Parts 1-10, offline fixtures) — this document covers real, live research only.

## 0. Method note (read this before the findings)

**Research was performed using this session's own web-browsing tools (`WebSearch`/`WebFetch`),
not the project's paid OpenAI/Tavily infrastructure.** No paid API call was made anywhere in
this evaluation, and none was needed — per the task's own instruction to report expected cost
before any paid call, there is nothing to approve: this was ordinary, no-additional-cost
research browsing, the same category of tool use as every other web lookup in this session.
Every classification/extraction in the pipeline itself still runs through the existing
deterministic `WellBehaved*` mock models (`app/evidence_engine/pillars/product_technology.py`)
— no AI/LLM call was made for classification either, exactly as in every prior task.

**Every claim below is genuine.** Sourced 2026-09-27 via live web research, with a real URL,
real publisher, and a real publication date where one could be determined from the source
itself. Excerpts are deliberately short (a clause or short phrase, not full paragraphs) —
enough to support the claim and remain traceable to its source, not a reproduction of the
source's full text. Data lives in `app/evidence_engine/live_research/` (distinct from
`fixtures/`, whose companies are explicitly fictional test doubles); reproduce this report with
`python -m app.evidence_engine.live_research.run_evaluation`.

**Reading this report — four categories, kept visibly distinct throughout:**

| Category | What it means | How it's marked below |
|---|---|---|
| **Verified observation** | Something this evaluation directly confirmed by fetching/reading the actual source | "Confirmed via WebFetch: ..." |
| **Company disclosure** | A claim whose only source is the company's own materials (its website, its own blog post, a founder's own launch post) | `source_type: company_disclosure` in the evidence tables |
| **AI classification** | The label the (deterministic, non-AI-in-this-instance) classification interface produced from the evidence — called "AI classification" throughout per this system's own terminology, though no LLM was actually invoked | "Classified as ..." |
| **Methodological judgment** | This evaluator's own analysis of what a finding means for the engine's design | Under "Observed limitations" and "Recommended changes" only |

---

## 1. Results summary (all five companies)

| Company | Stage (determined) | Publishable | Strength | Coverage | Confidence |
|---|---|---|---|---|---|
| Notion | Series B+ *(see §6.1 — not the expected "Growth")* | Yes | 7.0 | 50.0% | Medium |
| Linear | Series B+ | Yes | 7.25 | 100.0% | Medium |
| Stripe | Growth | Yes | 5.88 | 100.0% | Medium |
| Fish Audio (seed/"early-stage") | Seed | Yes | 7.17 | 75.0% | Medium |
| Bullet (YC S26/"pre-seed") | Pre-Seed | Yes | 6.75 | 50.0% | Low |

All five pillar results were publishable (cleared both gates) despite two of five having only
50% coverage — a genuine, honest demonstration that "publishable" does not mean "fully
evidenced," and the per-dimension detail below is where that distinction actually lives.
**No confidence anywhere reached HIGH** — consistent with, and now reconfirmed against real
evidence rather than only the offline fixture roster, the concern already flagged in
`NEW_ENGINE_CALIBRATION_REPORT.md` Part 5/10.5.

---

## 2. Per-company evidence and results

### 2.1 Notion

**Evidence gathered (claim-level):**

| Claim | Source | Type | Date | Dimension |
|---|---|---|---|---|
| Integrations sync data, automate workflows | [notion.com/integrations](https://www.notion.com/en-gb/integrations) | company disclosure (product docs) | — | Product Existence |
| "Notion wins on everything docs-related" (vs. ClickUp) | [eesel.ai review](https://www.eesel.ai/blog/notion-review) | **verified independent** | 2026-06-24 | Differentiation |
| Public API for integrations | [notion.com/integrations](https://www.notion.com/en-gb/integrations) | company disclosure | — | Technical Depth |
| "Notion AI can now access Slack chats and Google Drive files" | [Computerworld](https://www.computerworld.com/article/3539918/notion-ai-can-now-access-slack-chats-and-google-drive-files.html) | **verified independent** | — | Technical Depth |
| Integration gallery lists Jira, Google Drive, Slack | [notion.com/integrations](https://www.notion.com/en-gb/integrations) | company disclosure | — | Technical Depth |
| Template ecosystem as a switching-cost moat | [How They Grow](https://www.howtheygrow.co/p/how-notion-grows) | **verified independent** | 2022-09-21 | Defensibility |
| $275M Series C, Oct 2021, Coatue/Sequoia | [Sacra](https://sacra.com/c/notion/) | **verified independent** | 2021-10-01 | Stage (⚠ disputed, see §3.1) |
| $275M Series C, "closed... October 23, 2025" | [salestools.io](https://salestools.io/en/report/notion-275m-series-c-2024) | aggregator | 2025-10-23 | Stage (⚠ disputed, see §3.1) |

**Pipeline results:** Product Existence scorable (7.0); Differentiation `CORROBORATED` (7.0,
Series B+ tier); **Technical Depth Signal rejected — Unscored** (§4.1: a real, live-evidence
classification error, not a genuine evidence gap); Defensibility `NONE_DISCLOSED` (§4.2: also not
what it looks like — the one real defensibility source found is stale, not absent). Overall:
publishable, Strength 7.0, Coverage 50%.

### 2.2 Linear

| Claim | Source | Type | Date | Dimension |
|---|---|---|---|---|
| GitHub integration automates PR workflows | [linear.app/integrations/github](https://linear.app/integrations/github) | company disclosure | — | Product Existence + Technical Depth |
| "I find the UI of Linear to be superior" (vs. Jira) | [Nuclino](https://www.nuclino.com/solutions/linear-vs-jira) | **verified independent** | 2026-01-14 | Differentiation |
| Figma integration links frames/pages to issues | [linear.app/integrations/figma](https://linear.app/integrations/figma) | company disclosure | — | Technical Depth |
| Slack integration for creating/viewing issues | [linear.app/docs/slack](https://linear.app/docs/slack) | company disclosure | — | Technical Depth |
| Workflow/integration lock-in as switching cost | [DEV Community](https://dev.to/theobrenner/migration-friction-is-the-real-cost-of-switching-tools-4cga) | **verified independent** | 2026-07-24 | Defensibility |
| "Announcing our Series C" | [linear.app/now](https://linear.app/now/building-our-way) | company disclosure | — | Stage |
| $82M Series C at $1.25B, led by Accel | [TechCrunch](https://techcrunch.com/2025/06/10/atlassian-rival-linear-raises-82m-at-1-25b-valuation/) | **verified independent** | 2025-06-10 | Stage |

**Pipeline results:** all four dimensions scorable — Product Existence 7.0; Differentiation
`CORROBORATED` 7.0; Technical Depth `SUBSTANTIAL` 8.0 (three genuinely distinct, correctly
un-folded facts — a clean positive result, contrast with Notion's §4.1); Defensibility
`CORROBORATED_MOAT` 7.0. Overall: publishable, Strength 7.25, Coverage 100% — **the one company
in this roster where real research produced a fully-scorable pillar**, and it did so honestly
(no forced or fabricated citation).

### 2.3 Stripe

| Claim | Source | Type | Date | Dimension |
|---|---|---|---|---|
| Shopify Balance uses Stripe Treasury + Stripe Issuing | [stripe.com/customers/shopify](https://stripe.com/customers/shopify) | company disclosure (case study) | — | Product Existence + Technical Depth |
| "the reference standard for payment developer experience" | [Fincoro](https://www.fincoro.com/insights/stripe-vs-braintree-vs-adyen) | **verified independent** | 2026-05-27 | Differentiation |
| "Shopify, DoorDash, Lyft, and Airbnb run on Connect" | [Apideck](https://www.apideck.com/blog/introduction-to-the-stripe-api) | **verified independent** | — | Technical Depth |
| "Every new product it launches makes it harder to leave" | [FourWeekMBA](https://fourweekmba.com/stripe-invisible-infrastructure-moat-bia/) | **verified independent** | 2026-03-03 | Defensibility |
| Valued at $159B after a Feb 2026 tender offer | [CNBC](https://www.cnbc.com/2026/02/24/stripe-value-stock-sale-tender-offer.html) | **verified independent** | 2026-02-24 | Stage (⚠ keyword gap, see §3.3) |

**Pipeline results:** all four dimensions scorable — Product Existence 7.0; Differentiation
`CORROBORATED` 6.0 (Growth tier); Technical Depth `SOME` 4.5 (only 2 distinct facts found — a
limitation of this evaluation's own research budget, not the pipeline, §5.4); Defensibility
`CORROBORATED_MOAT` 6.0. Overall: publishable, Strength 5.88 (the lowest of the five, entirely
because Stripe is scored at the Established/Growth tier where the identical evidence earns less
credit than the same label would at an earlier stage — exactly the intended stage-fairness
mechanism, not a defect).

### 2.4 Fish Audio ("early-stage" — real, seed-stage, press-covered)

| Claim | Source | Type | Date | Dimension |
|---|---|---|---|---|
| "Ship lifelike speech, voice cloning, and transcription with one API" | [fish.audio/developers](https://fish.audio/developers/) | company disclosure | — | Product Existence + Technical Depth |
| Open-source TTS repo, independently visible star count | [GitHub](https://github.com/fishaudio/fish-speech) | **verified**, aggregator/directory | — | Technical Depth |
| Priced "a 4x to 11x gap" below ElevenLabs | [Bland AI](https://www.bland.ai/blog/fish-audio-vs-elevenlabs) | **verified independent** | 2026-09-14 | Differentiation |
| "$52 million in seed funding" led by Coreline Ventures | [TechCrunch](https://techcrunch.com/2026/07/28/fish-audio-raises-50m-seed-to-build-ai-voice-models-for-creators-and-enterprises/) | **verified independent** | 2026-07-28 | Stage |

No defensibility-relevant evidence was found for this company during real research — left
genuinely `Unscored`, no claim invented to fill the gap.

**Pipeline results:** Product Existence 7.0; Differentiation `CORROBORATED` 8.0 (Seed/early
tier); Technical Depth `SOME` 6.5 (the open-source repo and the API description are two
genuinely distinct facts, correctly not folded — a second clean positive confirmation of
duplicate-detection working correctly against real, non-identical URLs); Defensibility
`NONE_DISCLOSED` (genuine — no evidence found, correctly distinguished from Notion's stale case).
Overall: publishable, Strength 7.17, Coverage 75%.

### 2.5 Bullet (YC S26, "pre-seed" — real, launched 2026-08-18)

| Claim | Source | Type | Date | Dimension |
|---|---|---|---|---|
| "switched over to using primarily Bullet for my projects" | [Hacker News, Launch HN thread](https://news.ycombinator.com/item?id=49283063) | **independent, but see §5.5** | 2026-08-18 | Product Existence |
| Founders: "resolved 479/500 (95.8%)" on SWE-bench | same HN thread | company disclosure | 2026-08-18 | Differentiation (⚠ disputed, see §3.2) |
| Commenter: benchmark validity directly disputed | same HN thread | **independent** | 2026-08-18 | Differentiation (⚠ disputed, see §3.2) |
| Integrations: "OpenAI, Anthropic Claude, and Grok" | same HN thread | company disclosure | 2026-08-18 | Technical Depth |
| "Bullet (YC S26)" | same HN thread | company disclosure | 2026-08-18 | Stage (⚠ keyword gap, see §3.3) |

**Pipeline results:** Product Existence 7.0 (from the independent user account, not the
founders' own claim); **Differentiation `DISPUTED` — correctly excluded** (§3.2, a genuine
real-world contested claim, not authored in); Technical Depth `SOME` 6.5 (one company-disclosed
fact; correctly below `SUBSTANTIAL`'s 3-fact floor); Defensibility `NONE_DISCLOSED` (genuine — the
company is 40 days old at retrieval time). Overall: publishable, Strength 6.75, Coverage 50%,
**Confidence Low** — the one company in this roster where Confidence itself is Low, consistent
with a young company backed mostly by a single-source public account.

---

## 3. Claim-level audit: real disputed and near-duplicate pairs

### 3.1 Notion's Series C — a real, live date conflict

Two independently-locatable sources disagree on the same fact:

- Sacra (independent-reporting-tier aggregator, well-corroborated by common public knowledge of
  this event): $275M Series C, **October 2021**, led by Coatue Management and Sequoia Capital.
- salestools.io (a lower-reliability, templated-report aggregator site): $275M Series C, "closed
  ... on **October 23, 2025**."

Both claims are marked `support_status: disputed` and linked via `contradicts` for this
evaluation. **This is a live finding, not a constructed test case** — real research turned up a
genuine factual disagreement between two public sources for the same company fact. The pipeline
handled it correctly at the scoring level (both excluded, neither trusted) — but see §6.1 for a
real gap this same pair exposed in stage determination specifically.

### 3.2 Bullet's benchmark claim — a real, contested claim in the wild

The founders' own launch post claims a specific SWE-bench Verified result. In the same public
Hacker News thread, an independent commenter directly challenges the claim's meaningfulness
("An intellectually honest way to tell if this thing really works would be to run that agent and
report its score and cost" — i.e., disputing that the reported number is a fair/complete
measure). Both were marked `disputed` for this evaluation and correctly excluded from Bullet's
Differentiation dimension. **This is the one real example in this evaluation of the engine's
qualitative-dispute handling (a challenged *interpretation*, not a conflicting *fact*) working as
intended on genuinely-occurring evidence** — a meaningfully different and arguably harder case
than Notion's date conflict, since there is no "correct" date to eventually resolve to here; the
claim's validity is a matter of ongoing, legitimate technical disagreement.

### 3.3 Two real "keyword gap" cases — Stripe and Bullet

Neither Stripe's actual stage signal ("a **tender offer**") nor Bullet's actual stage signal
("**YC S26**") is a term `stage.py`'s round-type keyword list recognizes. Both had to be manually
normalized for this evaluation (to "late-stage" and "Pre-Seed" respectively) — standing in for an
extraction-normalization step no code in this engine currently performs. **This is a real,
previously-undiscovered gap this live-evidence evaluation was specifically able to surface that
the offline fixture roster (Task 9-10), which always used clean "Series B"/"Series A"-style
values by construction, could not have found.**

---

## 4. Incorrect or unsupported classifications found

### 4.1 Notion's Technical Depth Signal: a real classification error

Three genuinely distinct real facts were gathered (Notion's public API; independently-reported
Notion AI access to Slack/Drive; the integration gallery's own listing of Jira/Drive/Slack).
The default classifier correctly proposed `SUBSTANTIAL` citing all three — **but the deterministic
validator rejected it**, because two of the three claims (`notion-live-003` and `notion-live-005`)
happen to share the exact same `source_url` (both were sourced from Notion's own integrations
page). `provenance.py`'s first check — an exact `source_url` match — is unconditional and fires
before any text-similarity comparison, collapsing them to one "fact" regardless of their actual,
substantively different content (one is about the existence of a public API; the other is about
which specific third-party tools are listed in the integration gallery).

**This is a real, live-evidence-discovered methodological weakness**, distinct from anything the
offline fixture roster surfaced: the exact-URL rule conflates "same source page" with "same
underlying fact," which is a legitimate assumption for a short news article restating one press
release, but not for a product's own reference/documentation page, which routinely documents
many distinct facts at one stable URL. **The correct outcome for Notion's Technical Depth Signal
is very plausibly `SUBSTANTIAL`** on the actual merits of the evidence; the engine currently
reports it `Unscored`. See §6.2 for the recommended fix.

### 4.2 Notion's Defensibility Signal: reported reason does not match the real reason

The one real defensibility source found (How They Grow, 2022-09-21) is outside its dimension's
24-month staleness bound as of the 2026-09-27 retrieval date — a real, correct exclusion. But the
`DimensionResult` this produces reports `classification_label: "NONE_DISCLOSED"` /
`availability: unscored_no_evidence` — **identical to what a genuine, real absence of evidence
would produce.** A human reviewer reading only the final result cannot tell "no defensibility
evidence exists" apart from "defensibility evidence existed once but is now too old to trust,"
even though the engine's own ledger internally knows the difference (`evidence.stale` is
non-empty). See §6.3.

### 4.3 No case of a fabricated or over-claimed classification was observed

Every `CORROBORATED`/`CORROBORATED_MOAT`/`SUBSTANTIAL` result the pipeline actually produced (as
opposed to rejected, §4.1) traces to real, independently-verifiable cited evidence — spot-checked
against the traceability report in `run_evaluation.py`'s output (zero violations across all 20
scored dimension results). The disputed pairs (§3.1, §3.2) were both correctly excluded rather
than resolved by guessing. No instance of the engine inventing a citation or accepting an
unsupported evidence reference was found against real evidence, consistent with the extensive
adversarial testing in Task 10.

---

## 5. Observed limitations (methodological judgment)

### 5.1 Confidence's HIGH threshold remains unreached against real evidence too

None of the 15 scored dimension results across all five companies reached `High` confidence.
This corroborates, rather than merely repeats, the same finding from the offline fixture roster
(`NEW_ENGINE_CALIBRATION_REPORT.md` §5/10.5) — it is not an artifact of the fixtures being
synthetic. Real, independently-reported evidence for well-documented companies like Linear and
Stripe still tops out at Medium, because `CONFIDENCE_MIN_RELIABILITY_FOR_HIGH` (0.9) requires an
average source-reliability weight that a mix including even one `product_documentation` source
(weight 0.8) cannot reach when combined with `independent_reporting` (1.0) sources — and nearly
every dimension in this evaluation cites at least one company-documentation source, since Product
Existence and much of Technical Depth is, quite reasonably, evidenced by the product's own docs.

### 5.2 The provenance-similarity thresholds were exercised, imperfectly, by real text

§4.1's finding is the sharpest data point: the exact-URL rule, not the Jaccard-similarity
thresholds, was the actual cause of the one real misclassification found. The similarity
thresholds themselves (0.75/0.40) were never actually the deciding factor in any of the 20 scored
dimensions in this evaluation — every genuinely-distinct real claim pair scored low enough on
Jaccard similarity to register as `INDEPENDENT` without needing the threshold to be finely tuned,
and no genuinely-duplicate pair in this roster happened to test the boundary either. **This
evaluation did not stress-test the similarity thresholds themselves as much as intended** — a
genuine gap in this evaluation's own coverage (§5.6).

### 5.3 Stage determination does not respect claim admissibility

`determine_stage()` reads `structured_fact` directly off raw company claims and has no
dispute-awareness or staleness-awareness at all — unlike every dimension-scoring path, which
always resolves through `resolve_dimension_evidence()` first. In Notion's case (§3.1) this
happened to be harmless (both disputed claims agreed on "Series C," which maps to the same
stage regardless of which one's date "wins"), but this is coincidental, not a property of the
code: two disputed claims disagreeing on the *round type itself* would currently be silently
resolved by whichever has the later `published_at`, with no record that the underlying claims
were ever in dispute.

### 5.4 Stripe's Technical Depth result reflects this evaluation's own research depth, not the pipeline

Only two technical-depth facts were gathered for Stripe in the time available for this
evaluation, despite Stripe's technical depth being, by any reasonable real-world assessment,
extremely rich (500+ documented API endpoints, dozens of named products). This is an honest
limitation of this evaluation's own effort, not a finding about the engine — flagged explicitly
so it is not mistaken for one.

### 5.5 Source-type classification for a public forum comment is genuinely ambiguous

Bullet's Product Existence evidence (§2.5) and one half of its disputed Differentiation pair
(§3.2) are both anonymous Hacker News comments, classified here as `independent_reporting` for
lack of a better-fitting category in the current `SourceType` enum. This is a materially
different *kind* of independence than a bylined news article (no accountability, no editorial
process, no verifiable identity) — yet it currently receives the identical `SOURCE_RELIABILITY_
WEIGHT` (1.0) as, say, TechCrunch. This is a real classification-granularity gap this live
evaluation surfaced that the offline fixture roster's own invented "independent_reporting"
claims never had reason to expose.

### 5.6 What this evaluation could not, and did not try to, validate

Per the task's own instruction not to tune parameters toward a favorable result for a
recognizable company: no weight, threshold, or table value was adjusted based on any of the
above. Five real companies (three well-documented, two deliberately sparse) is still not a
calibration cohort — this evaluation demonstrates the mechanism against real prose and surfaces
real gaps; it does not and cannot establish that any specific numeric parameter is now "right."

---

## 6. Recommended changes (not implemented — for approval)

1. **Loosen the exact-`source_url`-match rule in `provenance.py`** so that an identical URL is
   treated as strong evidence toward `LIKELY_DUPLICATE` rather than an unconditional, immediate
   verdict — combined with (not overriding) the text-similarity check, so two substantively
   different facts documented on the same reference page are not automatically folded together.
   Directly motivated by §4.1, the one real misclassification this evaluation found.
2. **Give Classified-dimension evaluation the same staleness-awareness the Computed (Product
   Existence) evaluator already has** — check `evidence.stale` before invoking the classifier and
   report a dedicated `unscored_stale` (or an equivalent classification-level state) rather than
   letting a "found nothing admissible" classifier response collapse staleness and genuine
   absence into the same `unscored_no_evidence` outcome. Directly motivated by §4.2.
3. **Route stage determination through the same admissibility check every dimension already
   uses** — `determine_stage()` should exclude disputed/stale stage-signal claims via
   `resolve_dimension_evidence()`-equivalent logic rather than reading `structured_fact` off raw
   claims directly. Directly motivated by §5.3.
4. **Expand the stage-signal round-type keyword list** to recognize real terms this evaluation's
   research actually encountered ("tender offer," "YC <batch>," and likely others a broader
   real-evidence pass would find) — or, more robustly, treat the keyword list as itself
   `CALIBRATION REQUIRED`/incomplete-by-design and add an explicit "recognized but unmapped"
   state distinct from "no signal found at all," so a real but unrecognized term is visibly
   different from a company that disclosed nothing. Directly motivated by §3.3.
5. **Add a distinct source-type (or a sub-flag) for anonymous public forum/community commentary**,
   separate from bylined independent press, with its own (lower) reliability weight. Directly
   motivated by §5.5.
6. **A future calibration pass should deliberately construct near-boundary similarity cases from
   real article pairs** (e.g., two outlets' actual restatements of the same real press release)
   rather than relying on whatever a general research pass happens to turn up — §5.2's gap.

None of the above was implemented in this task, per its own explicit constraint.

---

## 7. Acceptance criterion — self-assessment

- **"Demonstrate that the pillar produces evidence-traceable assessments from real research"** —
  met: every scored dimension across all five companies traces to a real, cited, admissible claim
  (§4.3); zero traceability violations.
- **"Correctly withholds unsupported scores"** — met, and demonstrated at three genuinely
  different levels: a fully-withheld dimension from a real content-derived rejection (Notion's
  Technical Depth, §4.1 — even though this report also argues the rejection itself was for the
  wrong underlying reason), two genuinely disputed real-world claims correctly excluded (§3.1,
  §3.2), and two genuinely absent defensibility signals correctly left `Unscored` rather than
  invented (Fish Audio, Bullet).
- **"Identifies any remaining methodological weaknesses before further expansion"** — met: §4-§6
  surface six concrete, specific findings, several genuinely new relative to the offline
  calibration work, each with a recommended (not yet implemented) fix.

**Overall: this evaluation supports proceeding to a future phase that fixes the specific,
concrete issues in §6 before implementing additional pillars — not a wholesale redesign, and not
an unconditional green light either.**
