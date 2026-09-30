# LINEAR_001 Remediation (Task 23)

**Status: implemented, tested offline against representative fixtures (32 new tests + 445 prior,
477 total), no network call made, no methodology changed, `LIVE_EVALUATION_LINEAR_001.md` unedited.**
This document is the record of what changed in response to that run's own findings, and — per that
task's own explicit instruction — is precise about what a fix can and cannot prove without a second
live run.

## 1. Defect-by-defect record

### 1.1 Funding evidence misrouted away from Funding History / Stage

- **Observed in LINEAR_001:** a real "$82M Series C, $1.25B valuation" claim was tagged only
  `commercial_validation`/`growth_trajectory` — never `funding_history` or `stage_signal`. Direct cause
  of both the Financial & Funding Signals pillar's total lack of evidence and `Stage` resolving to
  `Undetermined`.
- **Root cause:** `assessment_criteria` was a pure LLM proposal, checked only for "at least one real
  dimension" — nothing validated that a proposed tag was actually consistent with what the fact
  described, and the system prompt gave no explicit routing guidance for funding facts at all.
- **Remediation:** (a) `acquisition/routing.py`'s new `FACT_KIND_ALLOWED_CRITERIA` map deterministically
  intersects `assessment_criteria` against the real, pillar-code-derived allowed set whenever
  `structured_fact.kind == "funding_round"` (→ `funding_history` only) or `"funding_round_type"` (→
  `stage_signal` only); (b) the extraction system prompt (`providers_live.py`) now explicitly instructs
  the model to tag a funding round `funding_history` and, when a round type is stated, additionally emit
  a `funding_round_type` fact for `stage_signal`.
- **Regression test:** `test_extraction_routing_remediation.py::test_funding_round_routes_only_to_
  funding_history`, `test_funding_round_type_routes_only_to_stage_signal`, and the five item-10
  adversarial cases.
- **Category:** primarily **routing** (a); the prompt change (b) is a **recall-adjacent** improvement to
  the untyped case, not fixable by routing alone (see §3).
- **Expected effect on LINEAR_002:** IF the same underlying fact is retrieved again, it should now
  either (i) be typed as `funding_round`/`funding_round_type` and correctly reach `funding_history`/
  `stage_signal`, or (ii) if the model still fails to type it, still be prevented from polluting an
  unrelated dimension — but (ii) alone does not fix the missing Financial & Funding evidence. Whether
  the model actually types it correctly is unverified until a live call.

### 1.2 Founder background misrouted away from Founder Relevant Experience

- **Observed in LINEAR_001:** Saarinen's Airbnb/Coinbase background was tagged only
  `leadership_composition`/`public_track_record`.
- **Root cause:** same as 1.1 — no routing guidance, no deterministic check.
- **Remediation:** `FACT_KIND_ALLOWED_CRITERIA["founder_experience"] = {"founder_relevant_experience"}`;
  prompt now explicitly instructs the model to tag prior-employer/background facts about a founder
  `founder_relevant_experience` (kind `founder_experience`) and/or `team_identity` for a plain identity
  fact, always with `named_entity` set to the real name.
- **Regression test:** `test_founder_experience_routes_only_to_founder_relevant_experience`,
  `test_founder_experience_kept_when_correctly_proposed`, adversarial case #2 (`founder education →
  Market Growth`).
- **Category:** routing + recall-adjacent (same split as 1.1).
- **Expected effect on LINEAR_002:** same caveat as 1.1 — routing is now enforced; whether the model
  types the fact correctly in the first place is unverified until a live call.

### 1.3 Two independent sources of the same person fact not recognized as corroborating

- **Observed in LINEAR_001:** a YouTube video title and a First Round Review podcast page, both
  confirming "Karri Saarinen is co-founder/CEO," resolved to two *different* `independence_group_id`s.
- **Root cause:** `IDENTITY_KEY_FIELDS["team_identity"] = ("person_id",)` keys identity on `person_id`,
  but the extractor supplied `named_entity`/`role` (no `person_id`) on one claim and no `structured_fact`
  at all on the others.
- **Remediation:** `acquisition/person_identity.py::normalize_person_name_to_id()` — a pure, deterministic
  name→id normalizer (case/whitespace/diacritic-insensitive; refuses vague titles like "the CEO" via an
  explicit denylist, per item 6's own instruction; never guesses from a role alone). `claim_identity.py::
  finalize_claim()` now calls `_backfill_person_id()` to inject a derived `person_id` from
  `structured_fact.named_entity` whenever a person-identity-relevant kind (`team_identity`,
  `founder_experience`, `track_record`, `leadership_hire`) carries a name but no id — **never** overwriting
  an explicitly-supplied `person_id`, and **never** inventing a name that was never extracted.
- **Regression test:** the full `test_person_identity_*` group plus
  `test_finalize_claim_backfills_person_id_from_named_entity_when_missing`,
  `test_finalize_claim_never_overwrites_an_explicit_person_id`, and the end-to-end
  `test_two_independent_claims_about_the_same_founder_now_share_an_independence_group` — which
  reproduces LINEAR_001's exact two-source shape and proves both now land in the same
  `independence_group_id`.
- **Category:** **provenance/identity**, not routing.
- **Known limitation, unchanged by this fix:** name-STRING normalization only — two different real
  people who happen to share an identical full name would still collide, and two genuinely different
  spellings of the same name (a typo, a transliteration) would not be recognized as the same person. Out
  of scope for a deterministic, no-network normalizer.
- **Expected effect on LINEAR_002:** if the model reliably supplies `named_entity` on identity/experience
  facts (already true in LINEAR_001 for at least one of the two claims), corroboration recognition for a
  named founder should now work correctly without any change in what gets *retrieved*.

### 1.4 `KNOWN_FACT_KINDS` gap (found while investigating 1.1-1.3, not itself observed as a live failure)

- **Root cause:** re-deriving the true kind vocabulary directly from every pillar file's own `kind ==`/
  `!=` checks (rather than trusting `claim_identity.py::IDENTITY_KEY_FIELDS` was already complete) found
  three kinds a real pillar file reads — `leadership_hire`, `founders_only_confirmed`, `retention_signal`
  — that were **missing** from that table. Since `extraction.py::KNOWN_FACT_KINDS` is built directly from
  its keys (Task 21), any real candidate of one of these three kinds would have been **incorrectly
  rejected** by `validate_candidate()`'s `INVALID_FACT_KIND` check. This did not happen to surface in
  LINEAR_001 (no candidate of these three kinds was ever proposed that run) but is a genuine, latent bug,
  not a hypothetical one.
- **Remediation:** all three kinds added to `IDENTITY_KEY_FIELDS` with correctly-derived identity-key
  sub-fields.
- **Regression:** covered indirectly (no dedicated new test — this table's own completeness is exercised
  by every existing pillar test that already uses these three kinds; a `KNOWN_FACT_KINDS` regression test
  was judged unnecessary since the fix is a table addition with no new logic).
- **Category:** structured-fact completeness / a real Task 21 bug fix.

### 1.5 Low structured-fact population rate (17% in LINEAR_001)

- **Investigation:** the prompt never explained WHY a structured fact mattered beyond "if present, set
  kind to X" — it gave no positive incentive or concrete guidance connecting a fact's real-world shape
  (a funding round, a person's background, a dated release) to which fields the model should actually
  populate.
- **Remediation:** the routing-guidance paragraph added to the prompt (§1.1/1.2/1.3) explicitly names
  which `kind` and which key fields (`named_entity`, `status`, `value`) apply to the exact fact shapes
  LINEAR_001 under-typed. This is a **prompt-content change only** — no schema field was made
  mandatory (item 5's own "missing remains preferable to invented" is unchanged; a claim with no
  structured_fact still passes through, ungated, exactly as before).
- **Category:** recall/completeness. **Cannot be validated offline** — whether the real model's own
  structured-fact population rate actually improves is unverified until a live call (item 14).

### 1.6 Relevance-questionable claim (third-party hobbyist tool)

- **Observed in LINEAR_001:** a personal dev.to blog post about someone else's own tool that merely uses
  the target company's ticket data was accepted as `differentiation_claim_corroboration` evidence — a
  literal, grounded quote, but not actually about the target company's own product.
- **Root cause:** grounding answers "did the source say it," never "is this materially about the target
  company," and the four Product & Technology dimensions this could inflate
  (`differentiation_claim_corroboration`, `defensibility_signal`, `product_existence_maturity`,
  `technical_depth_signal`) have no positive `structured_fact.kind` gate of their own (Tasks 8-9's own
  original, free-text design) — so no existing kind-based check could ever have caught this case.
- **Remediation:** a new, optional, four-value typed field, `subject_relationship`
  (`acquisition/relevance.py`), populated by the extractor per candidate. A candidate marked
  `unrelated_third_party` has exactly those four kind-agnostic dimensions stripped from its
  `assessment_criteria` — `product_integration`/`customer_or_partner` (item 9's own explicit "do not
  reject legitimate ecosystem/partner evidence") are never touched by this rule, and absent/unknown
  behaves exactly as before this task (fully additive, non-breaking default).
- **Regression test:** the full `test_*subject_relationship*`/`test_*third_party*` group, plus
  `test_full_sanitize_pipeline_end_to_end_on_the_linear_001_dev_to_shape`, which reproduces the exact
  LINEAR_001 shape end-to-end through the real, shipped `_sanitize_assessment_criteria()`.
- **Category:** **relevance**, a genuinely new control this engine did not have before.
- **Expected effect on LINEAR_002:** if the model correctly marks a similarly tangential claim
  `unrelated_third_party`, it will no longer be able to inflate Product & Technology's score the way the
  dev.to claim did. Whether the model reliably self-classifies this way in practice is unverified until a
  live call.

### 1.7 Changelog / market-report acquisition misses

- **Observed in LINEAR_001:** `linear.app/changelog` (5 real dated releases in the prior manually-curated
  fixture) and a real, public market-sizing report were never retrieved, despite existing search queries
  already targeting roughly the right topics.
- **Investigation (item 7/8):** the existing query text ("{company} changelog product launch release",
  "{company} market size industry category") is reasonable but generic; Tavily's own `search_depth=
  "basic"`/`max_results=5` simply did not surface an equivalent source this particular run. No domain-
  or Linear-specific logic was added — per the task's own explicit prohibition.
- **Remediation:** `research_plan.py`'s two query templates were reworded (NOT a new query, NOT a change
  in query count — still exactly 12 total, still exactly 2 per topic):
  - `"{company} changelog product launch release"` → `"{company} official changelog release notes
    product updates"` (biases toward the three standard names companies use for first-party update
    pages, per item 7's own list — generalizes to any company, no domain named).
  - `"{company} market size industry category"` → `"{company} total addressable market size report
    analysis"` (biases toward the CONTENT TYPE an analyst market-sizing report actually is, rather than
    toward general competitor/category pages — generalizes to any company, no category named).
- **What was deliberately NOT done:** a domain-biased search using the company's own already-known
  website (e.g. Tavily's `include_domains`) would likely help further but requires passing `website_url`
  into `SearchProvider.search()` — a deeper architecture change this task did not make, named here as
  candidate follow-up work, not attempted.
- **Category:** **recall (acquisition)**, explicitly the one category item 14 says cannot be validated
  offline.
- **Expected effect on LINEAR_002:** **unknown and unclaimed.** Per item 14's own explicit instruction:
  *"if the changelog was never retrieved, you cannot claim this task fixes shipping coverage merely
  because extraction now understands changelog evidence."* This task changed query WORDING; it did not,
  and structurally cannot, guarantee Tavily returns a different result set. If LINEAR_002 still misses
  the changelog/market report, that is a genuine, still-open acquisition question, not evidence this
  fix "didn't work" in the sense of doing what it actually claims to do (improve keyword targeting, not
  guarantee recall).

## 2. What this task explicitly did NOT do (item 15)

- Did not treat `spyingbee.com`/`seeto.ai`/etc. as stronger sources than the deterministic classifier
  already treats them.
- Did not treat any company disclosure as independent corroboration (§1.7's self-published-TAM test
  reconfirms the EXISTING, unchanged filter still excludes this).
- Did not lower any publication gate, coverage floor, or confidence threshold.
- Did not guess a missing structured fact into existence — every fix above either narrows what an
  ALREADY-proposed tag may reach, or backfills an id from a name the model ALREADY supplied; nothing
  invents a fact, a field, or a score.
- Did not convert any `Unscored`/`Undetermined` outcome into a neutral score.

## 3. Routing vs. recall — kept explicitly distinct throughout

| Fix | Routing (deterministic, verified offline) | Recall (acquisition, unverified until live) |
|---|---|---|
| Funding routing (§1.1) | ✅ enforced | prompt change only, unverified |
| Founder routing (§1.2) | ✅ enforced | prompt change only, unverified |
| Person identity (§1.3) | ✅ enforced (provenance, not routing) | N/A |
| `KNOWN_FACT_KINDS` gap (§1.4) | ✅ fixed (structured-fact completeness) | N/A |
| Structured-fact completeness (§1.5) | N/A | prompt change only, unverified |
| Relevance (§1.6) | ✅ enforced | depends on model self-classifying correctly, unverified |
| Changelog/market recall (§1.7) | N/A | query wording only, **unverified, explicitly unclaimed** |

## 4. Files changed

- `app/evidence_engine/acquisition/routing.py` (new) — deterministic fact-kind → allowed-criteria map.
- `app/evidence_engine/acquisition/relevance.py` (new) — `subject_relationship` vocabulary + stripping rule.
- `app/evidence_engine/acquisition/person_identity.py` (new) — deterministic person-name normalization.
- `app/evidence_engine/acquisition/claim_identity.py` — `IDENTITY_KEY_FIELDS` gap fix (§1.4); `finalize_
  claim()` now backfills `person_id` (§1.3).
- `app/evidence_engine/acquisition/extraction.py` — `_sanitize_assessment_criteria()` now applies routing
  + relevance narrowing, in addition to Task 21's own vocabulary filter.
- `app/evidence_engine/acquisition/models.py` — `ExtractedClaimCandidate.subject_relationship` (new,
  optional field).
- `app/evidence_engine/acquisition/providers_live.py` — system prompt gained routing guidance + the
  `subject_relationship` field description; `_CandidateSchema`/`_schema_candidate_to_extracted()` carry
  the new field through structured output.
- `app/evidence_engine/acquisition/research_plan.py` — two query templates reworded (§1.7); query COUNT
  unchanged (still 12 total).
- `app/evidence_engine/tests/test_extraction_routing_remediation.py` (new, 32 tests).
- `app/evidence_engine/tests/test_provider_adapters.py` — one existing test's fixed character budget
  raised from 4,500 to 8,000 chars, to stay meaningful against the now-longer system prompt (a mechanical
  consequence of the prompt getting longer, not a logic change).

**Not changed:** any pillar file, `parameters.py`, `full_analysis.py`, `cross_pillar_audit.py`,
`scoring.py`, `stage.py`, or `LIVE_EVALUATION_LINEAR_001.md`.

## 5. Test results

**477 tests across 22 files, all passing** (445 prior + 32 new). Legacy regression (7/7, 2/2) and the
isolation boundary (3/3) reconfirmed. All six pillars' own real sanity-check scripts reproduce their
exact historical `Strength` values, byte-for-byte unchanged (8.0, 6.2, 6.79, 7.25, 5.92, 8.0). The
7-company full-engine cohort evaluation reproduces its exact prior audit totals (0 ERROR, 1 WARNING, 1
INFO) unchanged. No network access anywhere in this task.

## 6. Whether Linear 002 should be authorized

**Yes, with the scope explicitly limited to measuring whether these specific fixes changed anything —
not to a general re-evaluation.** The routing/provenance/relevance fixes are now offline-proven against
the exact failure shapes LINEAR_001 exposed; the recall-side changes (prompt wording, query wording) are
real but explicitly unverified, and this document does not claim they will change what gets retrieved.
LINEAR_002, run with the same methodology and comparable provider budgets (unchanged, per Task 22's own
requirement), is the only way to learn whether real-world extraction now types funding/founder facts
correctly, whether `subject_relationship` self-classification is reliable in practice, and whether the
reworded queries surface different sources. A third possibility this document takes no position on:
LINEAR_002 might show identical acquisition recall (same sources retrieved) with cleaner routing (correct
dimension tags this time) — which alone would already validate this task's core, verifiable claim.
