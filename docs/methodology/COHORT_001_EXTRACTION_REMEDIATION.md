# Cohort 001 Extraction Remediation (Task 27)

Remediation of `docs/methodology/LIVE_EVALUATION_COHORT_001.md` §7 Finding S1 — the cohort's central
finding: structured facts were consistently grounded, correctly typed, and (after Task 25) correctly
routed, and still could not score, because their `structured_fact`'s own field **values** did not
match the exact vocabulary each dimension's real classifier requires. This document records what was
built, the regression fixtures reproducing the cohort's own exact real failures, the offline
before/after classifier-readiness measurement, and what remains unresolved.

## 1. Root cause (restated, precisely, per finding)

| Real, cited failure | Root cause |
|---|---|
| `metric="annual revenue"` / `"annual recurring revenue"` / `"users"` / `"paying customers"` (Notion) | Free-text paraphrase instead of the exact 6-value enum `_parse_scale_point()` checks by string equality |
| `value_type` never populated on any `traction_metric` claim across the cohort | The extraction prompt never named this field as a required categorical value at all |
| `amount="400 million"` / `"21 million"` etc. never parses as `float()` | The prompt never instructed a bare numeric string |
| `financing_type="Seed"` (Fish Audio, both real claims) | **The single most important, precisely-diagnosed insight**: the model conflates the legal financing STRUCTURE (`equity`/`debt`/`grant`) with the round/stage LABEL (`Seed`/`Series B`) because one candidate carries only one `structured_fact` dict, and the prompt never told it these are two different facts needing two different candidates |
| `founding_year` field populated as `"amount"` instead of `"value"` (Notion, Fish Audio, Linear 002 — 3 independent occurrences) | `stage.py::determine_stage()` reads `"value"`; the prompt never named this exact key |
| `founder_experience.value` / `track_record.value` / `retention_signal.value` never populated (Stripe ×2, ×1) | Correctly typed and routed, but the categorical `value` field's own vocabulary (ADJACENT/DIRECT, PRIOR_EXIT/PRIOR_VENTURE_ROLE, WEAK/MODERATE/STRONG) was never named in the prompt |

## 2. What was built

1. **`app/evidence_engine/acquisition/fact_contracts.py`** — the canonical, code-derived contract for
   all 20 fact kinds. See `docs/methodology/CLASSIFIER_READY_EXTRACTION_CONTRACT.md` for the full
   reference (categorical vocabularies, required fields, the funding/metric/team/retention/
   product/market contracts, the schema-level-vs-deterministic-only tradeoff).
2. **`routing.py`'s `_APPLICABILITY_CHECKS`** extended from Task 25's 3 verified kinds to all 18
   kind-gated kinds, via `check_classifier_readiness()` — the same eligibility-vs-applicability
   mechanism Task 25 built, now covering the full vocabulary Finding S1 identified, not a new
   mechanism.
3. **`providers_live.py::_StructuredFactSchema`** — `financing_type` and `value_type` are now real,
   OpenAI-structured-output-enforced `Enum` fields (`FinancingLegalType`, `TractionValueType`); the
   model cannot propose an out-of-vocabulary value for either. `_schema_candidate_to_extracted()`
   updated (`model_dump(..., mode="json")`) so enum values serialize as plain strings, keeping every
   downstream `fact.get(...) == "..."` comparison unchanged.
4. **`providers_live.py`'s `_SYSTEM_PROMPT_TEMPLATE`** — rewritten routing-guidance section: names the
   exact categorical vocabulary per kind (customer_band, founder_experience, track_record,
   retention_signal, capital_efficiency_signal, competitive_structure, traction_metric's
   metric/value_type, product_release's status); explicitly distinguishes `financing_type` (legal
   structure) from a round/stage label and instructs the model to propose **two** candidates when a
   source states both; reinforces `founding_year`'s `"value"` field given its 3-4× recurrence.
5. **Regression fixtures + offline measurement** — `test_cohort_001_extraction_fixtures.py` (item 13),
   detailed in §3-4 below.
6. **Consumer/extractor contract tests** — `test_fact_contracts.py` (item 12), 41 tests proving every
   one of the 20 fact kinds' real downstream consumer handles both a classifier-ready and an
   insufficient fact safely — see §5, which also documents the one real bug this testing found and
   fixed.

## 3. Cohort regression fixtures (item 13)

`test_cohort_001_extraction_fixtures.py` contains **14 fixtures**, each citing the exact
`docs/methodology/*.md` report and line(s) that documented the real, as-extracted field shape — 2
Stripe, 6 Notion, 4 Fish Audio, 2 Linear (Linear 002 + LINEAR_002_REMEDIATION.md). Per item 13's own
explicit instruction ("do not manually invent information absent from the source"), every `before`
fixture uses only the field values the cited report actually quotes; unverified fields are left
absent rather than guessed (which can only make the fixture *more* likely to correctly fail, never
falsely pass). Every `after` fixture is the same real, grounded proposition with only the specific
documented gap corrected — never a different, invented fact. Two fixtures where the exact correct
categorical value cannot be determined from the source (Stripe's founder-experience ADJACENT-vs-DIRECT
judgment, Stripe's retention-signal tier) are explicitly labeled representative-only in their own
citation comment, not presented as a claim about what that specific evidence proves.

## 4. Offline classifier-readiness measurement (item 14)

Computed directly from the 14 cited fixtures, **reported separately from raw `structured_fact`
population** (which the cohort reports already measured near-100% for these same claims):

| | Classifier-ready | Rate |
|---|---|---|
| **Before** (the real, as-extracted shape) | 0 / 14 | **0%** |
| **After** (the same real fact, field-corrected per the new contract) | 14 / 14 | **100%** |

**Explicit caveat, restated from the fixture file's own docstring:** this measures whether the *same*
real facts, if correctly shaped, would satisfy each kind's own deterministic contract. It does **not**
predict what a live model, given the updated prompt, will actually produce on a future run — extraction
behavior is not fully deterministic, and this task made no live call to check. Only a real live
evaluation (explicitly not run in this task, per its own constraints) can measure that.

## 5. Consumer/extractor contract tests (item 12) and the regression note

`test_fact_contracts.py` calls the **real** downstream pillar classifier/parser directly (never a
reimplementation) for all 20 fact kinds, both a classifier-ready fact (correctly consumed) and an
insufficient one (safely ignored — no crash, no fabricated label). 40 of 41 tests passed on the first
run; the one failure was a genuine, real bug, not a test bug:

**`stage.py::determine_stage()` crashed with an uncaught `KeyError`** when a `founding_year` claim
reached it with `"amount"` instead of `"value"` — the exact field-name mismatch this cohort documented
three independent times (Notion, Fish Audio, Linear 002). The existing `try/except (TypeError,
ValueError)` around `int(latest.structured_fact["value"])` does not catch `KeyError`, which direct
bracket access raises when the key is simply absent. This is the same latent defect
`LINEAR_002_REMEDIATION.md` first documented as "confirmed real but never triggered live" (Task 24
found it only because a *different*, since-fixed bug had accidentally prevented the malformed claim
from ever reaching admissibility). Task 27's own test — built the same way the calibration suite or
any hand-constructed ledger fixture legitimately can (bypassing extraction-time routing entirely) —
reproduced the crash directly, proving the risk was still real and no longer merely theoretical for
any ingestion path that does not go through `extraction.py`'s own routing pass.

**Fixed** (both the `funding_round_type` and `founding_year` branches) by switching to
`.get("value")` and treating a missing key the same as an unrecognized/unparseable one — fail closed
to "no stage signal from this claim," never raise. This is defense-in-depth: Task 25's own
`funding_round_type_fields_are_sufficient()` / `founding_year_fields_are_sufficient()` already keep a
malformed fact like this **out** of `stage_signal` on the normal, routed path; this fix protects the
path that check does not gate. All 41/41 tests pass after the fix; the full 549-test regression sweep
(§7) confirms no other file was affected.

## 6. Extraction prompt/schema tradeoff (item 10, cross-referenced)

See `docs/methodology/CLASSIFIER_READY_EXTRACTION_CONTRACT.md` §4 for the full "schema-level vs.
deterministic-only enforcement" reasoning. Summary: `financing_type`/`value_type` are real Pydantic
enums (unambiguous regardless of kind); `value`/`metric`/`status` stay free-text at the schema level
(their vocabulary depends on the sibling `kind` field, which OpenAI's structured-output schema cannot
express without a full discriminated union per kind) and are instead validated deterministically, one
step later, by `fact_contracts.py::check_classifier_readiness()` — exactly where Task 25's own
applicability mechanism already lives.

## 7. Regression verification (items 15, 20)

Full sweep, all 25 `app/evidence_engine/tests/test_*.py` files, run after every change in this task:

```
549 tests across 25 files — 0 failures
  (504 prior + 41 test_fact_contracts.py + 4 test_cohort_001_extraction_fixtures.py)
test_isolation_boundary.py: 3/3 (fact_contracts.py imports only within app.evidence_engine)
test_routing_completeness_and_observability.py: 27/27 (routing/applicability extension unregressed)
test_extraction_routing_remediation.py: 32/32 (Task 23's routing/relevance/identity work unregressed)
```

Tasks 23-25's specific guarantees re-verified as part of this sweep, not merely assumed unchanged:
deterministic kind-based routing (Task 23), person-identity normalization/backfill (Task 23),
relevance/`subject_relationship` stripping (Task 23), eligibility-vs-applicability routing with full
observability (Task 25), provenance/independence-group deduplication and contradiction-handling
(unchanged since Tasks 10-12, exercised throughout the pillar test files). One test
(`test_founder_background_task_23_behavior_unaffected` in
`test_routing_completeness_and_observability.py`) needed updating: extending
`_APPLICABILITY_CHECKS` from 3 to 18 kinds means a fully-structured `founder_experience` fact is now
correctly rescued by the fallback where it previously was not (Task 25's own scope was narrower) — an
intended coverage extension, documented in the test's own updated docstring, not a regression.

Confirmed zero-diff throughout this task: `parameters.py`; all six historical
`LIVE_EVALUATION_*.md`/`*_REMEDIATION.md` reports; acquisition search/retrieval/query text/budgets. No
live/network call was made anywhere in this task.

## 8. What remains unresolved

- **Market recall** (item 9) — inspected, not fixed. `market_size_usd`/`category_growth_rate_pct`'s
  own contract is sound; whether the acquisition layer retrieves qualifying independent market-sizing
  evidence at all is a separate, unaddressed question (the cohort's own §9-adjacent recall findings
  from Task 22/26 remain open).
- **`team_identity.role` exact-match gap** (§7 of the contract doc) — a realistic extracted role
  string like `"Co-Founder and CEO"` will never exactly equal `"founder"`, the string
  `_confirmed_person_ids(role="founder")` requires. Documented, not touched — normalizing it would be
  a methodology-adjacent change outside this task's scope.
- **Whether the updated prompt actually improves live extraction** — unmeasured by design. This task's
  offline fixtures prove the *contract* correctly discriminates before/after shapes; only a real live
  run (explicitly not performed here) can show whether the model's real output shifts.
- **Financial & Funding Signals' 0-for-5 live-run scoring streak** (Finding S2, `COHORT_001.md` §7) —
  directly downstream of the `financing_type`/`founding_year` field-shape issues this task's contract
  now targets, but not itself re-tested against a live run in this task.

## 9. Recommendation for the next live validation

**Fish Audio and Notion**, re-run once (not performed in this task). Reasoning: these are the two
companies in the cohort whose documented field-completeness failures are the most varied and the most
squarely targeted by this task's specific fixes — Fish Audio for the `financing_type="Seed"` round-
label conflation (the cohort's clearest, first-observed instance of that exact bug) and its
`value_type`-only traction gaps, Notion for the `metric` paraphrase pattern (4 distinct paraphrases in
one run) and the `funding_round` missing-fields case. A re-run of either would give the most direct,
information-dense signal on whether the updated prompt/schema actually shifts real model output toward
classifier-readiness — more so than Stripe (whose main gap was a same-run extraction miss on funding
entirely) or Linear (already run twice; a third run adds less new signal about a *different* company's
extraction behavior). Explicitly: **neither company was run as part of this task.**
