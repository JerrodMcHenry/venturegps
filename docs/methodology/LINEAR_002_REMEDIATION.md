# LINEAR_002 Remediation (Task 25)

**Status: implemented, tested offline against representative fixtures (27 new tests + 477 prior,
504 total), no network call made, no methodology changed, neither `LIVE_EVALUATION_LINEAR_001.md`
nor `LIVE_EVALUATION_LINEAR_002.md` edited.** This document records what changed in response to
LINEAR_002's own two findings: a correctly-typed fact silently losing all `assessment_criteria`, and
`subject_relationship` being unobservable after extraction.

## 1. The defect

`LIVE_EVALUATION_LINEAR_002.md` §9: a `funding_round` claim and a `founding_year` claim were both
correctly *typed* by the extractor, but both ended up with `assessment_criteria == []` after Task 23's
own routing step — permanently un-citable by any dimension, with no record of why.

## 2. Root cause

Task 23's `route_assessment_criteria()` answered exactly one question — **eligibility**: which
dimension(s) may a given `structured_fact.kind` ever legally reach? It intersected the model's own
proposed criteria against that set and returned whatever survived, including nothing. Nothing then
checked whether "nothing survived" was itself a problem, or preserved any explanation. Two DIFFERENT
questions were being conflated: eligibility (a property of the kind alone) and **applicability** (does
*this specific* fact's own field values actually meet the dimension's real evidence contract?) — item
2's own required distinction.

Re-reading the two real consumers directly confirmed exactly what was missing:

- `pillars/financial_funding.py::parse_funding_round()` (now split into a reusable `funding_round_
  fields_are_sufficient()`) requires `financing_type`, `round_date`, `status == "completed"`,
  `currency == "USD"`, and a parseable `amount` — LINEAR_002's own claim had none of `financing_type`/
  `round_date`/`status`, and its `amount` field ("$1.25B") does not parse as a float at all. It was a
  **valuation** fact, mislabeled with the round-amount kind.
- `stage.py::resolve_stage()` reads `structured_fact["value"]` for `founding_year` — LINEAR_002's own
  claim used `"amount"` instead. **This is a second, more serious defect this investigation found while
  reading the real code, not merely a routing gap:** had this claim's criteria NOT been empty (i.e., had
  Task 23's own eligibility-only routing let it through to `stage_signal`), `resolve_stage()`'s own
  direct-bracket access `latest.structured_fact["value"]` would have raised an uncaught `KeyError`,
  crashing stage resolution outright. The empty-criteria bug accidentally prevented this crash from ever
  firing in LINEAR_002 — a genuinely lucky coincidence, and exactly why item 3's own "do not
  automatically route to every allowed criterion merely because the LLM failed" matters: a naive fix
  that just re-added the eligible dimension without checking field sufficiency would have introduced a
  new crash.

## 3. Eligibility vs. applicability — the design

- **Eligibility** (`routing.py::FACT_KIND_ALLOWED_CRITERIA`, Task 23, unchanged): which dimension(s) a
  KIND may ever reach. A property of the kind alone.
- **Applicability** (`routing.py::_APPLICABILITY_CHECKS`, new): given the fact's OWN field values, is a
  specific eligible dimension actually usable? Implemented for exactly the three kinds this
  investigation found or confirmed a real gap for — `funding_round`, `funding_round_type`,
  `founding_year` — each reusing the real consumer's own validation logic directly (`funding_round_
  fields_are_sufficient()` split out of `parse_funding_round()`; `funding_round_type_fields_are_
  sufficient()`/`founding_year_fields_are_sufficient()` added to `stage.py`, calling its own `map_round_
  type()` and mirroring its own `int(value)` parse exactly), never a second, parallel, driftable check.

For the other 15 recognized kinds, no applicability check exists — `applicable` defaults to `eligible`
so a *correctly*-proposed tag still routes normally, but **the deterministic fallback (adding a tag the
model never proposed at all) is deliberately restricted to kinds with an explicit, verified check.** A
first implementation applied the fallback to every eligible kind by default and was caught by this
task's own test suite: it would have "routed" a `founder_experience` fact to `founder_relevant_
experience` even when missing the `value` field that dimension's own classifier actually requires —
technically harmless (the classifier would still find nothing usable) but a misleading `RoutingDecision`
claiming success where none was verified. Restricting the fallback to evidence-verified kinds only is
the more conservative, better-justified choice, and is itself now a directly-tested invariant
(`test_founder_background_task_23_behavior_unaffected`).

## 4. Funding-round behavior (item 4)

- **Funding History:** a `funding_round` fact reaches it only when `funding_round_fields_are_
  sufficient()` passes — the exact same five-field contract `evaluate_funding_history()` itself already
  enforces, reused, not re-derived.
- **Stage Signal:** a `funding_round` fact NEVER reaches `stage_signal` — confirmed by re-reading
  `stage.py::resolve_stage()` directly, it only ever reads `funding_round_type`/`founding_year` kinds,
  never `funding_round`. `FACT_KIND_ALLOWED_CRITERIA["funding_round"]` correctly has always been
  `{"funding_history"}` only (unchanged from Task 23). A `funding_round_type` fact reaches `stage_
  signal` only when its own `value` maps to a real `Stage` via `stage.py::map_round_type()` (reused
  directly) — never from amount, investor prestige, or vague language, per item 4's own explicit list.

## 5. Founding-year decision (item 5)

**A real methodology consumer exists** (`stage.py`'s own `stage_signal` pseudo-dimension) — this is
NOT contextual metadata with no consumer, and `NO_METHODOLOGY_CONSUMER` would have been the wrong,
dishonest status for it. The correct status when a `founding_year` fact is insufficiently structured
(LINEAR_002's own exact shape, `"amount"` instead of `"value"`) is `UNROUTED_INSUFFICIENT_STRUCTURE`/
`REJECTED_INVALID_ROUTING` (depending on whether the model's own proposal at least named `stage_signal`)
— a well-formed `founding_year` fact (correct `value` field) now routes to `stage_signal` correctly.

## 6. Routing statuses introduced (item 6)

`routing.py::RoutingStatus`:

| Status | Meaning |
|---|---|
| `ROUTED` | Reached ≥1 legitimate, applicable dimension (from the model's own proposal, or via the verified deterministic fallback) |
| `CONTEXT_ONLY` | Kind is identity/context data BY DESIGN (`team_identity`, `strategic_statement`) — never a scored dimension, criteria pass through unchanged, zero Strength impact |
| `UNROUTED_INSUFFICIENT_STRUCTURE` | The model's proposal named an eligible dimension, but the fact's own fields don't meet its evidence contract |
| `UNROUTED_NO_METHODOLOGY_CONSUMER` | The kind itself has no real consumer at all (mechanism implemented and tested; not reachable by any of this engine's current 18 real kinds — see §9) |
| `REJECTED_INVALID_ROUTING` | The model's proposal named nothing this kind can ever reach, and no verified fallback exists either |

Full decision — `status`, `reason`, `fact_kind`, `proposed_criteria`, `eligible_criteria`, `final_
criteria`, `removed_criteria`, `added_criteria` — is a `RoutingDecision` (see §7).

## 7. Relevance persistence (item 7)

**LINEAR_002's own observability gap, closed.** `subject_relationship` was already used to strip
dimensions (Task 23) but never survived past extraction — no way to inspect what the model proposed vs.
what survived. `RoutingDecision` (a new `pydantic.BaseModel`, `acquisition/models.py`) now carries
`proposed_subject_relationship`, `final_subject_relationship`, and `relevance_removed_criteria`
alongside the routing fields, attached to `ExtractedClaimCandidate.routing_decision` — **never to
`Claim`** (item 8's own "rather than polluting core scoring models"; verified by a structural test,
`test_routing_decision_lives_on_candidate_not_on_claim`). Source content still cannot self-assign
relevance (unchanged from Task 23 — `subject_relationship` only ever narrows, and only when explicitly
`unrelated_third_party`).

## 8. Routing/relevance telemetry (items 8-9)

`pipeline.py::_extract_claims()` pairs each accepted candidate's own `routing_decision` with the
`claim_id` `finalize_claim()` produces (`ClaimRoutingRecord`), collected into `AcquisitionTelemetry.
claim_routing` — no signature change to `finalize_claim()` itself was needed; this is the one place
both values are already available together. A future live-run report can now answer, for any claim,
exactly why it did or did not reach a pillar — proven end-to-end (not just at the unit level) by
`test_pipeline_populates_claim_routing_telemetry_end_to_end`, which runs the real, unmodified pipeline
against a fake extractor proposing the WRONG criteria for a well-structured funding round and confirms
both the corrected ledger claim and the matching telemetry record.

## 9. AI/deterministic authority boundary (item 10)

Every invariant item 11 lists is now a directly-tested property of `route_candidate()`:

- **Invalid model routing cannot broaden evidence** — `final_criteria` is always a subset of
  `applicable` (itself a subset of `eligible`); the model can never widen it.
- **A bad/empty proposal does not destroy deterministically applicable evidence** — the verified
  fallback (§3) rescues a well-structured fact even from an entirely wrong proposal.
- **Context remains context** — `team_identity`/`strategic_statement` never enter the eligibility
  machinery; proven end-to-end that a mistagged context claim still scores nothing on a real pillar
  evaluator (`test_context_remains_context_never_counted_by_a_real_classifier`).
- **AI cannot invent a criterion, convert context into scored evidence, or declare independent
  corroboration** — all unchanged, pre-existing structural guarantees (Task 20-21's vocabulary/kind
  validation, `provenance.py`'s own corroboration logic), reconfirmed still true after this task's own
  changes, never touched.

## 10. Regression fixtures from LINEAR_002 (item 12)

All in `test_routing_completeness_and_observability.py`:

- **Funding round:** the exact real (insufficiently-structured) LINEAR_002 shape stays honestly
  unrouted with a real reason; a well-structured equivalent is rescued despite an identical bad
  proposal.
- **Founding year:** the exact real (wrong-field-name) LINEAR_002 shape stays honestly unrouted; a
  correctly-structured equivalent (`"value"` field) now correctly reaches `stage_signal`.
- **Founder background:** Task 23's own routing/person-identity behavior reconfirmed unchanged.
- **Person identity:** two independent sources still resolve to the same `person_id`.
- **Relevance:** an unrelated-third-party claim's final disposition (proposed/final relationship,
  removed criteria) is now directly inspectable via `routing_decision`.

## 11. What this task deliberately did NOT fix

- **The changelog/market-search recall gaps** (LINEAR_001 §1.7/LINEAR_002 §6.D/§6.E) — explicitly out
  of scope this task (item 13); the 12 research queries are unchanged.
- **Applicability checks for the other 15 kinds** — no evidence from either live run showed a real
  problem with them; adding speculative checks without evidence would be exactly the over-generalization
  this engine's own discipline avoids. `UNROUTED_NO_METHODOLOGY_CONSUMER` and the fallback-restriction
  design are both ready to extend the moment real evidence justifies it.
- **A live third run.** Per item 15/18, no Tavily/OpenAI/HTTP call was made, and Linear was not
  analyzed again.

## 12. Files changed

- `app/evidence_engine/acquisition/routing.py` — `RoutingStatus`, `RoutingResult`, `route_candidate()`,
  `CONTEXT_ONLY_KINDS`, `_APPLICABILITY_CHECKS`. Task 23's own `route_assessment_criteria()`/`strip_
  kind_agnostic_dimensions_for_owned_kind()` left unchanged (still directly tested/used by Task 23's own
  test file).
- `app/evidence_engine/acquisition/models.py` — new `RoutingDecision`/`ClaimRoutingRecord` models;
  `ExtractedClaimCandidate.routing_decision` field; `AcquisitionTelemetry.claim_routing` field.
- `app/evidence_engine/acquisition/extraction.py` — `_sanitize_assessment_criteria()` now calls `route_
  candidate()` and attaches the full decision.
- `app/evidence_engine/acquisition/pipeline.py` — `_extract_claims()` now returns `ClaimRoutingRecord`s
  alongside claims; `run_acquisition_pipeline()` includes them in telemetry.
- `app/evidence_engine/pillars/financial_funding.py` — `_parse_funding_round` renamed public
  (`parse_funding_round`); its dict-level validation split out as reusable `funding_round_fields_are_
  sufficient()`. No behavior change to `evaluate_funding_history()` itself.
- `app/evidence_engine/stage.py` — `_map_round_type` renamed public (`map_round_type`); two new
  reusable helpers, `funding_round_type_fields_are_sufficient()`/`founding_year_fields_are_sufficient()`.
  No behavior change to `resolve_stage()` itself.
- `app/evidence_engine/tests/test_routing_completeness_and_observability.py` (new, 27 tests).

**Not changed:** any pillar's own scoring/gating logic, `parameters.py`, the 12 research queries, the
extraction system prompt, `LIVE_EVALUATION_LINEAR_001.md`, `LIVE_EVALUATION_LINEAR_002.md`.

## 13. Test results

**504 tests across 23 files, all passing** (477 prior + 27 new). Legacy regression (7/7, 2/2) and the
isolation boundary (3/3) reconfirmed. All six pillars' own real sanity-check scripts reproduce their
exact historical `Strength` values, byte-for-byte unchanged. The 7-company full-engine cohort evaluation
reproduces its exact prior audit totals (0 ERROR, 1 WARNING, 1 INFO) unchanged. No network access
anywhere in this task.

## 14. Readiness for a diverse live cohort

**Ready, with the specific defect class LINEAR_002 found now closed and verified offline.** The engine
has now been exercised through two real live runs plus this offline-only remediation; the deterministic
core (grounding, source-type classification, contradiction detection, publication gates, and now
routing/applicability) has shown no methodology-level defect across either run. The recall-side
limitations (changelog/market discovery) remain open and are exactly what a diverse cohort — spanning
company stage, evidence density, business model, and source availability — would test for
generalization, rather than continuing to tune around one company's own search results.

### Recommended composition and size (not run)

3-5 companies, chosen to vary independently on the four axes item 17 names:

1. A well-documented, funded, later-stage company with rich independent press (tests whether the
   funding/founder routing fix generalizes beyond Linear).
2. An early-stage/seed company with genuinely sparse public evidence (tests honest withholding under
   real scarcity, not just Linear's own moderate case).
3. A company in a different vertical from developer tools (e.g. consumer or fintech) to test whether
   the market-query wording generalizes.
4. A company with a genuinely public, well-known changelog/release-notes page (a direct test of whether
   the changelog-discovery gap is Linear-specific or general).
5. (Optional, if budget allows) A company with public financial disclosures (e.g. a company that has
   filed with a regulator) to exercise `PUBLIC_FILING` source-type handling and `funding_round`/`stage_
   signal` routing against a genuinely different evidence shape than press-reported funding rounds.

This is a recommendation only — per item 18, this task does not run it.
