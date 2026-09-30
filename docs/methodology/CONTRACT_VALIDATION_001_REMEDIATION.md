# Contract Validation 001 Remediation (Task 29)

Remediation of the four concrete defects `LIVE_EVALUATION_CONTRACT_VALIDATION_001.md` (Task 28's live
validation) found. Full design rationale: `docs/methodology/SEMANTIC_EVIDENCE_CONTRACT.md`. This
document is the defect-by-defect account and its regression coverage.

## 1. Defect 1 — person_id backfilled after routing's applicability check

**Observed** (`LIVE_EVALUATION_FISH_AUDIO_002.md` §5): a `founder_experience` claim about Shijia Liao
was classifier-ready on its FINAL, ledger-stored `structured_fact`, but `assessment_criteria` was
permanently `[]` — routing ran on the pre-backfill fact (no `person_id`), judged it "insufficient
structure," and nothing re-checked the result once `person_id` was backfilled moments later.

**Root cause**: `extraction.py::_sanitize_assessment_criteria()` (routing) ran before `claim_identity.py::
finalize_claim()` (backfill) in the real pipeline call order.

**Fix**: `canonicalization.py::canonicalize_structured_fact()`, called by `_sanitize_assessment_criteria()`
immediately before `route_candidate()`. Reuses `claim_identity.py::backfill_person_id()` (made public,
not re-implemented) — the exact same deterministic derivation. `finalize_claim()`'s own call to the same
function is now a safe, idempotent no-op in the normal path.

**Regression coverage**: `test_canonicalization.py::test_person_id_is_canonical_before_routing_
applicability_runs` / `test_track_record_person_id_ordering_is_also_fixed` (general rule, both
person-identity-relevant kinds); `test_task29_regression.py::test_fixture_person_ordering_founder_
experience_survives_routing` (the exact real Fish Audio shape, named claim text/excerpt, end-to-end
through the real pipeline function).

## 2. Defect 2 — funding amount format ("52M"/"52 million")

**Observed** (`LIVE_EVALUATION_FISH_AUDIO_002.md` §4/§6): `financing_type` conflation already fixed
(Task 27), but all 5 real `funding_round` candidates carried `amount="52M"` or `"52 million"` — neither
parses as `float()`, so zero funding_round claims were classifier-ready despite the conflation fix.

**Fix**: `canonicalization.py::canonicalize_numeric_amount()` — converts `"$52M"`/`"52M"`/`"52 million"`/
comma-formatted bare numbers to the canonical bare-number form, applied to every field a kind's real
contract (`fact_contracts.py`) lists as `numeric_fields`. A range, a vague quantifier ("tens of
millions", "over $50M"), or anything else ambiguous is returned completely unchanged — the anchored
regex fails to match, so ambiguity fails closed by construction. Currency is never touched.

**Regression coverage**: `test_canonicalization.py` — 9 unit tests (suffix forms, comma-separated,
already-bare, ambiguous-range/quantifier fail-closed, currency preservation, missing-currency
non-invention) plus `test_funding_amount_canonicalization_makes_the_real_fish_audio_shape_classifier_
ready` (the exact real shape); `test_task29_regression.py::test_fixture_funding_amount_dollar_m_
becomes_classifier_ready` (end-to-end).

## 3. Defect 3 — metric period/date missing even when explicit in source

**Observed** (`LIVE_EVALUATION_NOTION_002.md` §4): `metric`/`value_type` vocabulary confirmed fixed, but
`period_date` absent from both real traction claims, blocking classifier readiness.

**Finding, on closer inspection**: the real Notion 002 source articles genuinely never stated an
explicit as-of date the model captured for these two figures — this is correctly "remain incomplete,"
not a canonicalization opportunity (item 5's own closing instruction). What Task 29 DOES fix: a claim
whose source DOES state a fully explicit date, just in a non-ISO textual form ("August 5, 2026", "Aug 5
2026", "2026/07/28"), now canonicalizes correctly. A bare year, a year-month, or a vague quarter/season
— which would require inventing a day or month never stated — is deliberately left unchanged.

**Fix**: `canonicalization.py::canonicalize_explicit_date()`.

**Regression coverage**: `test_canonicalization.py` — 8 unit tests (month-name forms, already-ISO,
slash-YMD, bare-year/year-month/quarter/season remain-incomplete, None-safety) plus `test_metric_period_
canonicalization_matches_a_real_task_28_notion_shape` (both directions — explicit date canonicalizes,
genuinely-absent date stays absent); `test_task29_regression.py` — two dedicated fixtures, one per
direction, both against the real Notion revenue-claim shape.

## 4. Defect 4 — schema-valid, semantically unsupported categorical values

**Observed** (`LIVE_EVALUATION_NOTION_002.md` §5, `LIVE_EVALUATION_CONTRACT_VALIDATION_001.md` §5 —
the most important Task 28 finding): `retention_signal="STRONG"` assigned to a "90% multiplayer usage"
adoption statistic; `competitive_structure="fragmented"` inferred from a bare, uncharacterized
competitor list. Both structurally/schema valid; neither supported by the cited excerpt.

**Fix**: a new, independent, deterministic gate — `semantic_fit.py` — wired into `routing.py::
route_candidate()` as a new, distinct outcome (`RoutingStatus.UNROUTED_SEMANTICALLY_UNSUPPORTED`,
separate from `UNROUTED_INSUFFICIENT_STRUCTURE`). Full rule design, generalization reasoning, and the
explicit list of categorical fields deliberately left to future/probabilistic judgment:
`docs/methodology/SEMANTIC_EVIDENCE_CONTRACT.md` §4.

**Regression coverage**: `test_semantic_fit.py` — 21 tests: the two real false-positive excerpts
(verbatim from the live reports), 5 additional negative-proxy cases per item 7's exclusion list
(customer count, logos, testimonials, longevity, growth/popularity), 5 positive controls (item 14 —
explicit retention/churn/renewal language, explicit fragmentation/concentration reports), a
fragmented-vocabulary-does-not-validate-concentrated-value cross-check, `NOT_APPLICABLE` correctness for
kinds with no rule, company-name invariance (4 companies, identical decision), a signature-level proof
the function cannot read a score/coverage argument, and 6 routing-integration tests (distinct typed
status, empty `final_criteria`, grounded proposition preserved unmutated, structurally-ready-but-
semantically-wrong claims correctly blocked from `check_methodology_readiness()`).
`test_task29_regression.py` adds the two named, real-shaped fixtures end-to-end.

## 5. Before / after, the two real defect claims

| Claim | Before (Task 28) | After (Task 29) |
|---|---|---|
| Fish Audio founder_experience (Shijia Liao) | `assessment_criteria == []` (routing ran pre-backfill) | `assessment_criteria == ["founder_relevant_experience"]` |
| Fish Audio funding_round (`amount="52M"`) | `UNROUTED_INSUFFICIENT_STRUCTURE` (unparseable amount) | `ROUTED`, `amount="52000000"` |
| Notion traction_metric (explicit-date variant, synthetic) | `UNROUTED_INSUFFICIENT_STRUCTURE` (non-ISO period_date) | `ROUTED`, `period_date` canonical ISO |
| Notion traction_metric (real, no period stated) | `UNROUTED_INSUFFICIENT_STRUCTURE` | Unchanged — correctly still incomplete, no fabrication |
| Notion retention_signal (adoption evidence) | `ROUTED` (Task 27; a real regression risk) | `UNROUTED_SEMANTICALLY_UNSUPPORTED` |
| Notion competitive_structure (bare competitor list) | `ROUTED` (Task 27; a real regression risk) | `UNROUTED_SEMANTICALLY_UNSUPPORTED` |

## 6. Full regression sweep

608 tests across 28 files, 0 failures (549 prior + 28 `test_canonicalization.py` + 21
`test_semantic_fit.py` + 10 `test_task29_regression.py`). Isolation boundary 3/3 (both new modules import
only within `app.evidence_engine`). No existing test's observable outcome changed — the new semantic-fit
gate only fires for `retention_signal`/`competitive_structure`, and no existing fixture in any prior test
file used those kinds through the acquisition-layer routing path (confirmed by direct grep before
writing any new code).

## 7. What was NOT changed

`parameters.py` — untouched. Every pillar file's own scoring/gating logic — untouched (Task 27's own
`stage.py` crash-guard fix remains, per this task's own explicit allowance; no further change to
`stage.py`). `research_plan.py`, `AcquisitionBudget`, provider configuration, concurrency — untouched
(confirmed via `git diff --stat`). All six historical `LIVE_EVALUATION_*.md` reports (including the two
new Task 28 ones) — untouched. No live/network call was made anywhere in this task — every test uses
hand-built fixtures/direct function calls, no `FakeSearchProvider`/`FakeEvidenceExtractor` network
substitute even needed, since all new logic is exercised at the pure-function level that the real
pipeline calls identically.

## 8. Remaining known limitations

- The semantic-fit rule set covers exactly 2 of 20 fact kinds — deliberately narrow (§4 above); several
  other kinds (`track_record.value`, `product_release.status`) are plausible future candidates but were
  not added without their own confirmed real-failure evidence.
- `team_identity.role`'s exact-match gap (documented since Task 27) remains unfixed — out of this task's
  four-defect scope.
- Market-recall (whether the acquisition layer retrieves qualifying market-sizing evidence at all)
  remains untouched, per this task's own explicit "no changelog/market-recall work" instruction.
- No live run has yet confirmed whether these fixes change REAL model output/behavior at the acquisition
  layer (as opposed to the deterministic pipeline's own handling of representative fixtures) — see the
  completion report's own pre-integration gate answer and recommendation.
