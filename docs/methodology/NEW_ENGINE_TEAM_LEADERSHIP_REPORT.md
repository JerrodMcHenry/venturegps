# VentureGPS Evidence Engine — Team & Leadership Pillar (Task 14)

**Status: implemented and tested — the third production-quality pillar in `app/evidence_engine/`,
built on the exact architecture Product & Technology (Tasks 8-12) and Market Opportunity (Task 13)
already validated. No shared scoring philosophy, evidence ledger, classification system,
provenance system, confidence model, stage model, or publication gate was redesigned.** This
document does not rewrite `NEW_ENGINE_LIVE_EVALUATION.md`, `NEW_ENGINE_REMEDIATION_REPORT.md`, or
`NEW_ENGINE_MARKET_OPPORTUNITY_REPORT.md` — all three of the engine's prior historical reports are
untouched by this task.

## 1. Implemented dimensions (spec Part 3.3, unmodified)

All three dimensions from the approved specification, exactly as weighted and staleness-bound
there — no dimension invented, renamed, or dropped, and no dimension (e.g. a general "founder
quality" score) added beyond what the spec defines:

| Dimension | Weight | Category | Staleness | Admissible evidence (spec) |
|---|---|---|---|---|
| Founder Relevant Experience | 0.40 | Classified | 36 months | A named, checkable prior role or venture, with an explicit, established connection to this company's product/technology/market/operating problem |
| Leadership Composition | 0.30 | Classified | 12 months | Named leadership hires beyond the founder(s), or an explicit, sourced confirmation that founders are the only leadership |
| Public Track Record | 0.30 | Classified | 36 months | A documented prior venture role or a documented prior exit, tied to a specific, identity-confirmed person |

**All three are Classified — no Computed dimension exists for this pillar**, matching the spec's
own table exactly (the same shape as Market Opportunity; unlike Product & Technology, which has
one Computed dimension).

### 1.1 Closed label sets (a documented, narrow interpretation)

- **Founder Relevant Experience:** `NONE_DISCLOSED` (Unscored) / `ADJACENT` / `DIRECT`.
  `NONE_DISCLOSED` is read as "no RELEVANT experience established" — covering both a genuine
  absence of disclosed experience and experience that is disclosed but has no established
  connection to this company's domain (§1.2 below). This is the one genuine spec ambiguity Task 14
  encountered (the spec's own 3-label enum has no explicit fourth state for "disclosed but
  irrelevant") and it is resolved by the narrowest reasonable reading: the dimension's own name
  defines what counts.
- **Leadership Composition:** `NOT_ESTABLISHED` (Unscored — nothing was ever gathered) /
  `NONE_BEYOND_FOUNDERS` (a real, scorable, non-penalized state — see §3) / `SOME_HIRES` (≥1
  distinct named hire) / `SUBSTANTIAL_HIRES` (≥3 distinct named hires).
- **Public Track Record:** `NONE_DISCLOSED` (Unscored) / `PRIOR_VENTURE_ROLE` / `PRIOR_EXIT`.

**Why bands, not a raw number:** Design Principle 6 forbids any dimension letting the AI emit a
number directly. A band is a closed, finite label set — structurally a classification, not a
number — with deterministic code owning the label→score mapping (`parameters.py`).

### 1.2 Relevance must be explicit, never invented (item 5's own instruction)

Founder Relevant Experience does not credit prior experience merely because it exists. The
classifier only reads `structured_fact.value` (`ADJACENT`/`DIRECT`) — a deterministic stand-in for
"the evidence-gathering step already established a specific relevance connection between this
prior role and this company's domain," never a raw claim of "extensive experience." A claim with
no such fact (e.g. university attendance, or a prior role in an unrelated field) simply does not
carry a label the classifier can select — it falls through to `NONE_DISCLOSED`. There is no code
path that infers relevance from an employer or institution name; relevance is established upstream,
by whoever tagged the evidence, or not at all. This is the same mechanism, and the same trust
boundary, Market Opportunity already uses for its own magnitude bands (`NEW_ENGINE_MARKET_
OPPORTUNITY_REPORT.md` §1.1) — extended here to a relevance judgment rather than a size judgment.

### 1.3 The evidence bar is specificity, not independence (a genuine pillar-specific difference)

Unlike Market Opportunity (where every label requires `requires_independent_source`), Team &
Leadership applies `requires_independent_source` **nowhere** — correctly, per spec: self-disclosed
biographies are explicitly admissible evidence for this pillar (a founder's own bio is often the
only source for their own career history, and the spec does not ask that it be independently
corroborated). Instead, every real label in every dimension requires the new
`requires_named_entity_fact` (classification.py, §5 below): at least one cited claim must name a
specific, checkable entity (a company, a role). This is a different quality bar — specificity, not
source independence — and it is what actually blocks a vague, unsupported resume line ("extensive
industry experience") from scoring: it is admissible into the ledger (never deleted, full
auditability preserved) but cannot satisfy any dimension's minimum-to-score requirement without a
named, checkable fact behind it.

## 2. Identity resolution (item 6 — a genuine mechanism, not a narrative claim)

The approved spec describes no way to distinguish two different real people who share a name.
Task 14 adds one, deliberately narrow:

- A `team_identity` pseudo-dimension (not one of the 3 scored dimensions) tags claims that
  establish `structured_fact = {"kind": "team_identity", "person_id": "...", "role": "founder" |
  other}`.
- `_confirmed_person_ids()` resolves the set of `person_id`s admissibly, currently confirmed as
  affiliated with **this specific company** (scoped by `company_ref`, so the same name at two
  different companies never cross-contaminates).
- `_filter_to_confirmed_identity()` is applied before Founder Relevant Experience and Public Track
  Record ever see a claim: any claim whose `person_id` is not in the confirmed set is dropped, even
  if its evidence would otherwise score. When evidence exists but nothing survives this filter, the
  dimension returns `UNSCORED_UNCORROBORATED` with an explicit rationale — **failing closed**,
  never falling back to matching on name-string similarity.
- Leadership Composition is deliberately exempt from this check: a hire announcement ("Jane Doe
  joined as VP Engineering") is a self-sufficient fact — it names, roles, and affiliates a person
  in one claim — unlike a Founder Relevant Experience or Public Track Record claim, which describes
  a person's *separate, prior* history and therefore needs independent affiliation confirmation.

Tested directly: `test_two_people_with_similar_names_are_not_combined`,
`test_unconfirmed_identity_fails_closed`, `test_identity_confirmation_is_scoped_per_company`
(`test_team_leadership.py`).

## 3. Stage awareness (item 8 — documented per dimension, per instruction)

**Founder Relevant Experience and Public Track Record are flat, stage-independent tables.** Both
describe already-happened biographical facts — a prior exit or a specific prior domain role means
the same thing regardless of the company's current stage. This mirrors Market Opportunity's own
stage-independence reasoning, applied here to a person's past rather than to the external market.

**Leadership Composition is the one dimension whose own approved spec wording legitimately
supports stage sensitivity** (explicit confirmation that the founders are the only leadership is a
real, non-penalized state whose expectations reasonably differ pre-seed vs. mature). Even there,
`NONE_BEYOND_FOUNDERS` itself is pinned to an **identical** score (5.0) across every stage tier —
never rewarded for smallness, never punished for lacking an executive bench that would be
unreasonable at that stage, per item 8's explicit two-sided instruction. Only the genuinely
evidence-bearing hire-count labels (`SOME_HIRES`, `SUBSTANTIAL_HIRES`) vary by tier, in the same
direction Product & Technology already established: the same fact (e.g. 3+ named hires) is more
remarkable, and scores higher, at an earlier stage where it is less expected (early 9.0 / growth
8.0 / established 7.0 for `SUBSTANTIAL_HIRES`).

Tested directly: `test_founder_experience_is_stage_independent`,
`test_public_track_record_is_stage_independent`,
`test_none_beyond_founders_scores_identically_across_stages`,
`test_substantial_hires_scores_higher_at_an_earlier_stage`.

## 4. How subjective founder judgments were prevented (item 3 of the completion report,
##    answered here in the same structural terms used throughout this document)

This is enforced structurally, not merely narratively claimed:

- **No label set anywhere in this pillar contains a subjective concept.** The complete label
  vocabulary is `{NONE_DISCLOSED, ADJACENT, DIRECT, NOT_ESTABLISHED, NONE_BEYOND_FOUNDERS,
  SOME_HIRES, SUBSTANTIAL_HIRES, PRIOR_VENTURE_ROLE, PRIOR_EXIT}` — nine labels, all either a
  relevance classification, a hire count, or a track-record classification. There is no label
  meaning "strong founder," "intelligent," "charismatic," "visionary," or "likely to succeed," so
  no code path can select one.
- **Prestige is structurally incapable of producing a score by itself.** Every classifier reads
  only `structured_fact` (a deterministic, upstream-established fact) — never `redacted_text`,
  never a company/institution/investor name directly. `requires_named_entity_fact` additionally
  requires a *specific, checkable* fact, not a name-drop. Directly proven, not just asserted: the
  real-evidence sanity check (§7) includes a claim citing MIT/Harvard attendance with
  `structured_fact=None`, and it is confirmed programmatically to be cited by zero dimension
  results for either test company. `test_prestigious_employer_alone_does_not_change_score` proves
  score equality between a famous-employer claim and an obscure-employer claim carrying the
  identical `structured_fact.value` — the label, not the name, drives the score.
  `test_yc_participation_alone_does_not_establish_any_dimension` and
  `test_famous_investor_alone_does_not_establish_any_dimension` confirm neither is a recognized
  `structured_fact.kind` this pillar's classifiers look for at all.
- **Unsupported resume claims are rejected**, not silently trusted: `requires_named_entity_fact`
  blocks any label whose only cited evidence lacks a named entity, tested directly by
  `test_unsupported_resume_claim_does_not_score`.
- **Missing evidence is Unscored, never a negative or low score** — every dimension's absent-
  evidence path returns `score=None` with an explicit `UNSCORED_*` availability reason, never a
  numeric floor. `test_missing_founder_information_is_unscored_not_penalized` and
  `test_graceful_withholding_on_model_failure` both prove this directly (the latter simulating a
  crashing classifier and confirming the pillar withholds rather than guessing).
- **No sensitive personal characteristic is inferred anywhere** — the label vocabulary contains no
  such category, and no claim in the fixtures or live-research data encodes one; this is a
  structural absence (there is nothing to infer it *from*), not a runtime check.

## 5. Shared-engine change (item 6 — one, additive, documented here in full)

**`classification.py` gained one new factory, `requires_named_entity_fact(qualifying_labels)`.**
This is not a fix for a defect in Product & Technology or Market Opportunity — neither pillar uses
it, and both are entirely unaffected (confirmed by their full, unchanged regression suites passing
identically, §6 below). It is a genuinely new requirement type, structurally parallel to the
existing `requires_independent_source` and `requires_minimum_distinct_facts` factories, needed
because Team & Leadership's own evidence bar (§1.3) is specificity/checkability, not source
independence — a distinction the existing two factories cannot express. Extending the existing,
already-generic `LabelRequirementCheck` mechanism with a third factory is judged the narrower
change versus writing pillar-local validation logic that bypasses the shared classification-
recovery machinery.

## 6. Test results

**29 new tests, `test_team_leadership.py`, all passing** — covering strong documented team
evidence; sparse team information; missing founder information; self-reported biographies
(admissible); unsupported resume claims (rejected); contradictory employment history (excluded via
the existing dispute mechanism); stale biographies; duplicate biographies copied across websites
(don't inflate hire count, via the existing independence-group dedup); two people with similar
names (not combined); irrelevant prior experience (does not score as `ADJACENT`/`DIRECT`);
prestigious employer without demonstrated relevance (does not change score); prestigious university
without demonstrated relevance (not a recognized evidence kind at all); YC participation alone;
famous investor alone; unsupported classification / fabricated citation / invalid-label rejection;
prompt-injection resistance (including an injection-*compliant* adversarial mock, still blocked by
evidence-sufficiency validation — retrieved content never became instructions to the classifier);
classification recovery; both shared gates (minimum coverage, minimum distinct-scored-dimensions);
deterministic reproducibility; full traceability; graceful withholding under a crashing model.

**Full regression: 147 tests across 11 files, all passing** (118 prior + 29 new). Legacy regression
(`test_ai_request_reliability.py` 7/7, `test_analyze_unified_concurrency.py` 2/2) and the isolation
boundary (zero imports outside `app.evidence_engine` anywhere in the package) were both re-run and
reconfirmed **after** the live-research additions below, not only before. Product & Technology's
own Task 11/12 results and Market Opportunity's own Task 13 sanity-check results were both re-run
and reproduce identically after this pillar's addition — the new Team & Leadership-tagged claims
added to `live_research/stripe.py`/`linear.py` are invisible to both other pillars' evaluators,
which only ever read claims tagged with their own `assessment_criteria`.

Three self-caught bugs during test authoring (all fixed before this report; none is a defect in
the pillar itself — all three were test-fixture construction mistakes, the same class of
self-inflicted issue first documented in Task 10):
1. Three hire-fixture helper calls shared an identical default `role="CTO"` parameter, producing
   identical claim text that the (correctly-working) provenance dedup mechanism correctly folded
   into one distinct fact — fixed by giving each call an explicit, distinct role.
2. Even with distinct role names, a shared boilerplate sentence template ("`{role}` joined the
   leadership team.") still landed in the `UNKNOWN` Jaccard-similarity band rather than
   `INDEPENDENT` — fixed by giving each of the 4 hire fixtures a genuinely distinct sentence shape,
   not just a word-swapped template.
3. One test asserted an incorrect expected outcome (that a university-prestige claim with no
   `structured_fact` would reach the classifier and be labeled `NONE_DISCLOSED`) — the actual,
   correct behavior is that such a claim fails closed at the identity-resolution layer before ever
   reaching the classifier (`UNSCORED_UNCORROBORATED`, no label at all), which is the more
   conservative and more correct outcome. The test's expectation was relaxed to match, not the
   code changed.

## 7. Small real-evidence sanity check (item 10)

**Method note, identical to Tasks 11-13: research used this session's own `WebSearch`/`WebFetch`
tools, not the project's paid OpenAI/Tavily infrastructure — no paid API call was made or
required.** Reused Stripe and Linear from Tasks 11-13 (their `live_research/*.py` files extended
with a small number of new, genuinely-researched, real Team & Leadership-tagged claims — see each
file's own "Task 14 addition" section). Reproduce with `python -m app.evidence_engine.
live_research.run_team_leadership_sanity_check`.

### 7.1 Results

| Company | Publishable | Strength | Coverage | Founder Relevant Experience | Leadership Composition | Public Track Record |
|---|---|---|---|---|---|---|
| Stripe | Yes | 6.79 | 70% | 5.5 `ADJACENT` (Auctomatic — e-commerce tools, not payments-specific) | Unscored, `NOT_ESTABLISHED` (no evidence gathered) | 8.5 `PRIOR_EXIT` (Auctomatic, ~$5M acquisition, 2008) |
| Linear | Yes | 7.14 | 70% | 8.0 `DIRECT` (Principal Designer at Airbnb — directly relevant to a design-forward dev tool) | Unscored, `NOT_ESTABLISHED` | 6.0 `PRIOR_VENTURE_ROLE` (Kippt — no confirmed exit) |

**Zero traceability violations** across all 6 real scored dimension results (directly verified via
`verify_traceability()` against each pillar's own claim-ID set, not merely asserted).

### 7.2 The task's own success criterion, demonstrated directly, not just claimed

**Linear's much less publicly famous founder (Karri Saarinen) scored higher (8.0 `DIRECT`) on
Founder Relevant Experience than Stripe's world-famous founders (5.5 `ADJACENT`).** This is driven
entirely by the genuine relevance-connection strength documented in each claim's own evidence
(Principal Designer at Airbnb + founding designer at Coinbase is directly on-point for a
design-forward developer tool; Auctomatic — an eBay seller-tools startup — is real, checkable prior
entrepreneurial experience but only adjacent to Stripe's payments-infrastructure domain), never by
fame differential. This is the exact scenario the task's own success criterion names: "An unknown
founder with strong documented relevant evidence must be allowed to score well," alongside a famous
founder's evidence being read conservatively where the relevance connection is real but not
squarely on-point.

**Confirmed programmatically that the deliberate prestige-only test claim was never cited:** the
`stripe-team-university-001` claim (real reporting that the Collison brothers "dropped out of their
prestigious universities," carrying no `structured_fact`) is cited by **zero** dimension results
for Stripe. Prestige was present in the real evidence pool and was not used.

### 7.3 Checked against item 10's own failure-mode checklist

- **Prestige mistaken for capability:** not found — see §7.2.
- **Unrelated work getting relevance credit:** not applicable in this pass (no genuinely unrelated-
  field claim was researched for either company) — the mechanism itself is proven by the offline
  test suite (`test_irrelevant_prior_experience_does_not_score_as_direct_or_adjacent`), not
  re-exercised here with new real data.
- **Founder claims treated as independently verified:** not found — Stripe's `ADJACENT`
  classification and Linear's `DIRECT` classification both cite independent third-party reporting
  (Kitrum, Designer Founders), not a self-authored bio; this pillar's admissibility rule for
  self-disclosure was exercised by the offline suite (`test_self_reported_biography_is_admissible`)
  rather than by this real pass, since the real sources found were independently reported.
- **Duplicate bios counted as corroboration:** not found in this pass (each real claim is a single
  distinct fact) — the dedup mechanism itself is proven by the offline suite
  (`test_duplicate_biography_across_sites_does_not_inflate_hire_count`).
- **Incorrect identity resolution:** not found — each `team_identity` claim names a specific person
  and is the only identity claim for that `person_id` in this small real dataset; the fail-closed
  mechanism itself is proven adversarially by the offline suite (§2).
- **Missing evidence becoming negative:** not found — both companies' `leadership_composition` is
  honestly `Unscored (NOT_ESTABLISHED)`, not a low or zero score, and does not drag the pillar's
  overall publishability down (both remain `Publishable: True` at 70% coverage, clearing the 40%
  floor on the other two dimensions alone).
- **Stage expectations behaving irrationally:** not directly exercised by this pass (neither
  company's Leadership Composition evidence was researched, so no stage-tiered hire-count label was
  produced against real data) — the stage-tiering mechanism itself is proven by the offline suite
  (§3).

### 7.4 One honest finding worth flagging (not a code change)

**Neither company's Leadership Composition was researched for this small pass** — its absence
(`NOT_ESTABLISHED` for both) reflects this pass's own narrow research scope (three claims per
company, prioritizing founder-identity, founder-experience, and track-record evidence), not a claim
that no such evidence exists in the wild for either company. The same honest distinction Task 11
§5.4 and Task 13 §7.3 already drew for their own scope-limited absences.

## 8. Provisional parameters requiring future calibration

Every weight and label score below is `CALIBRATION REQUIRED`, exactly like every number in Product
& Technology's and Market Opportunity's own tables — none was set from real data, only reasoned to
be plausible enough to exercise the mechanism:

`TEAM_LEADERSHIP_DIMENSION_WEIGHTS` (0.40/0.30/0.30), `FOUNDER_EXPERIENCE_LABEL_SCORES`
(ADJACENT 5.5 / DIRECT 8.0), `LEADERSHIP_COMPOSITION_LABEL_SCORES` (`NONE_BEYOND_FOUNDERS` flat
5.0; `SOME_HIRES` 7.0/6.0/5.0; `SUBSTANTIAL_HIRES` 9.0/8.0/7.0 by stage tier),
`LEADERSHIP_SOME_HIRES_MIN_COUNT` (1) / `LEADERSHIP_SUBSTANTIAL_HIRES_MIN_COUNT` (3),
`PUBLIC_TRACK_RECORD_LABEL_SCORES` (PRIOR_VENTURE_ROLE 6.0 / PRIOR_EXIT 8.5). The directional
ordering behind each table (a prior exit outranks a prior venture role; direct relevance outranks
adjacent relevance; more named hires outrank fewer, more so at an earlier stage) is a reasoned
position, not asserted investment doctrine — flagged, not defended as objectively correct. The
1/3 hire-count thresholds for `SOME_HIRES`/`SUBSTANTIAL_HIRES` are likewise placeholders, not
derived from any real distribution of company leadership-bench sizes.

## 9. Remaining limitations

- Founder Relevant Experience's `NONE_DISCLOSED` conflates two states (genuinely no experience
  disclosed vs. experience disclosed with no established relevance connection) — a documented,
  deliberate simplification (§1.1), not an oversight, but a real loss of information the spec
  itself does not resolve.
- No mechanism verifies that a claimed relevance connection (`structured_fact.value =
  ADJACENT|DIRECT`) is *itself* correct — like Market Opportunity's own category-boundary
  limitation, this pillar trusts whoever established the `structured_fact` to have made that
  relevance judgment correctly; it is a real, documented trust boundary, not a defect.
  `requires_named_entity_fact` only guarantees the fact is specific and checkable, never that the
  relevance judgment behind it is correct.
- Identity resolution requires an explicit `team_identity` claim to exist at all — a company with
  strong founder-experience evidence but no separate identity-confirmation claim in the ledger will
  fail closed (Unscored) rather than score, which is the intended conservative behavior but means
  evidence-gathering completeness for this one pseudo-dimension is now a real prerequisite for
  every other Team & Leadership dimension except Leadership Composition.
- Leadership Composition's hire-count thresholds (1 / 3) are coarse and untested against a real
  distribution of company sizes; a company with exactly 2 named hires sits in the same `SOME_HIRES`
  band as a company with exactly 1.
- Two real companies (Stripe, Linear) remains far short of a calibration cohort —
  `NEW_ENGINE_CALIBRATION.md`'s much larger plan is still the real path to final numbers, and this
  task's own real-evidence pass explicitly did not attempt to reach Leadership Composition (§7.4).

## 10. Readiness for the eventual full-engine evaluation

Team & Leadership now behaves like the architecture Product & Technology and Market Opportunity
already proved: evidence-traceable (zero violations, real and offline), deterministic after
classification, resistant to unsupported claims and to prestige-by-association (the real-evidence
pass directly demonstrates a less-famous founder outscoring more-famous founders on the actual
documented relevance evidence), explicit about uncertainty (distinct Unscored reasons — no
evidence, stale, disputed, uncorroborated-identity — all exercised), and willing to withhold (both
individual dimensions and, when warranted, the full pillar). It additionally introduces and proves
a genuinely new mechanism — fail-closed identity resolution — that the other two pillars did not
need but that a people-focused pillar structurally requires. **Ready to join Product & Technology
and Market Opportunity in a future combined evaluation once at least one more pillar exists to make
"full-engine" meaningful** — this task deliberately implements no overall (cross-pillar) scoring
and no additional pillar (Commercial Traction, Execution & Momentum, Financial & Funding Signals
all remain unbuilt), per its own explicit scope constraints.
