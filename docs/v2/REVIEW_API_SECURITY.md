# Internal evidence review API: security — Increment 18.4 (updated 18.5)

Scope: `app/v2_review_api.py`, mounted at `/admin/v2-review` in the same FastAPI app as every legacy route
(`app/api.py`). It is the first V2 surface reachable by a human reviewer over HTTP rather than a local CLI
(`app/v2/tools/cli.py`, Increment 18.2/18.3), so it is the first place V2 candidate/evidence data is exposed to
network callers at all — nothing in `app/v2/**` itself changed to make this possible; this file only calls
existing, unmodified V2 services (`app.v2.resolution.human_review`, `app.v2.financing_resolution.promotion`,
`app.v2.classification.service`, and read-only repositories).

**Increment 18.5 additions**: review-queue pagination/filtering/search, a safe explicit evidence-integrity
error classification, and three collection-operations endpoints (`GET /collection-runs`,
`GET /collection-summary`, `POST /collection-runs/trigger`) reusing `app.v2.tools.scheduled_collection`. All
three are gated by the exact same `RequireAdmin` dependency as every other route here — nothing new about
authentication or authorization was introduced.

## Why this file lives outside `app/v2/`

V2's own architecture forbids `app/v2/**` from importing legacy code (`app.auth` among it — see
`docs/v2/ADR-0001-truth-model.md` and `app/v2/tests/architecture/boundary_rules.py`). This module genuinely
needs `app.auth.RequireAdmin` and the verified `AuthenticatedUser.user_id` from a real Clerk session, so it is
a legacy-side file (`app/`, not `app/v2/`) that imports V2, mirroring the one precedent already established for
mounting a V2 router into the legacy app (`app/v2/api.py`'s `v2_capital_router`, `app/api.py:449`). It adds no
canonical business rule of its own: every write goes through the same promotion/classification functions the
Increment 18.2 CLI already used, unchanged, at the same authority-checked boundary.

## Threat model

The reviewer sees byte-exact source evidence and can promote it to canonical company/financing/market-
classification facts. The realistic risks:

1. An unauthenticated or non-admin caller reaching any review data or decision endpoint at all.
2. A caller supplying its own idea of "who is deciding this" (a name, an id, a role claim) instead of the
   server's own verified identity — forging the audit trail.
3. A caller trusting (or the server blindly trusting) the stored `evidence_hash`/byte span on a candidate row
   without checking it still matches the actual payload bytes right now.
4. Replaying a decision request (network retry, double-click, or intentional replay) and getting a second,
   conflicting decision instead of a clean refusal.
5. Reviewing or deciding a financing candidate whose company was never actually promoted to canonical.
6. A failure response leaking a stack trace, a SQL fragment, or unverified evidence text.
7. This mount somehow changing the behavior of any existing legacy route.

## Controls, and exactly where each is enforced

| Control | Enforcement | Test coverage |
|---|---|---|
| Every endpoint requires a valid, verified Clerk session **and** server-side admin authorization | `current_user: AuthenticatedUser = RequireAdmin` on all ten routes — the same unmodified `app.auth.get_current_user`/`require_admin` dependency chain already gating `/admin/analytics` and the startup-claims admin endpoints; no route in this file uses the weaker `RequireAuth` alone | `test_unauthenticated_requests_rejected` (401 on every route), `test_non_admin_authenticated_requests_rejected` (403), `test_forged_signature_rejected` |
| Admin status is never taken from the client | `require_admin` reads `ADMIN_USER_IDS` fresh from the environment server-side (`app/auth.py`, unmodified); nothing in this file's request models has an `is_admin`/`role` field | Same as above — a non-admin's own valid token is still refused |
| Reviewer identity (the `Authority` recorded on every decision) is derived **exclusively** from the verified session | `_authority_for(current_user)` is the *only* place an `Authority` is constructed in this file: `human_authority(f"admin:{current_user.user_id}")`, where `current_user.user_id` is the JWT `sub` claim `app.auth` already verified. `DecideCompanyRequest`, `DecideFinancingRequest` and `ClassifyRequest` have **no** authority/reviewer field of any kind — there is nothing for a client to send | Inside `run_full_workflow`, the company-candidate `decide` call includes forged `authority_id`/`reviewer` fields in the JSON body; the test asserts pydantic silently drops them (unknown fields) and the recorded decision's `authority_id` equals `admin:{ADMIN_USER_ID}` regardless |
| Evidence is re-verified against the **live** payload on every read and every decision, never trusted from the stored row | `_live_payload_and_media_type` re-fetches the current attempt → observation → `RawPayload` (itself hash-verified by `get_raw_payload(..., verify=True)`) fresh on each call, then `verify_proposal`/`verify_financing_proposal` (the same functions `app/v2/candidates/*` already use at write time) re-check every evidence span's exact bytes and hash before anything is shown or acted on | `run_full_workflow` disables `company_candidate`'s database-level append-only trigger for one superuser statement (the only realistic bypass of it) to corrupt a stored `evidence_hash`, re-enables the trigger, then asserts both the detail GET and the decide POST fail with `422 evidence_integrity_failed` rather than showing or acting on unverified content |
| A genuine evidence-integrity failure gets a safe, explicit classification, never a generic error | `_verify_evidence` (Increment 18.5) catches exactly `evidence_hash_mismatch`/`evidence_out_of_bounds`/`payload_hash_mismatch` and returns `422 {"detail": "evidence_integrity_failed"}` — never the hash, byte span or evidence content; any other/unexpected error still falls back to `_run`'s generic 500 | Same tampering assertions, updated to expect `422` and the exact `evidence_integrity_failed` string; response bodies still checked for absence of `Traceback` and of the (unverified) candidate name |
| Duplicate/replayed decisions are refused, never repeated or silently accepted | `_domain_call` maps every `ConflictError` subtype (`CandidateAlreadyResolvedError`, `FinancingCandidateAlreadyResolvedError`, `IdentifierConflictError`, `WrongCompanyError`, `FactAlreadyAcceptedError`, `FactNotAvailableError`, `AlreadyClassifiedError`, `PrimaryAlreadyAssignedError`) to `409`; the underlying refusal is still the same database-enforced uniqueness Increment 18.2 already relies on (`uq_resolution_decision_one_final`, `uq_frd_one_final`) — this file adds no new dedup logic | `run_full_workflow` decides a company candidate, then replays the identical request (409, not a second decision); decides a financing candidate, then replays it (409); rejects a candidate, then attempts a `defer` on the same, already-resolved candidate (409) |
| A rejected/deferred candidate's history is visible and further decisions on a final one are refused | Resolution state is *derived*, never stored (`get_candidate_resolution_state`/`get_financing_candidate_resolution_state`, unmodified reads); a rejected candidate's detail view shows `resolution_state: "rejected"` and its full decision history | `run_full_workflow` rejects a candidate, re-reads its detail (`resolution_state == "rejected"`), then confirms a further decision on it is refused (409) |
| A financing decision is only reachable once the candidate's company is confirmed canonical, checked fresh, not assumed | `get_company(engine, candidate.proposal.company_id)` is called immediately before every financing detail read *and* every financing decide call, independent of the domain's own structural guarantee (`persist_financing_event_candidates` only ever accepts a `company_id` already present in the canonical `company` table) — defense in depth, not the only check | `financing_detail`'s `company_is_canonical` field is asserted `True` in the workflow test after a real create-company decision; the structural guarantee itself means a financing candidate for a non-canonical company cannot be constructed through any legitimate write path, so this is verified by code inspection rather than an independent negative test |
| Facts are explicitly selected, never implicitly copied | `FactSelectionIn` → `FactSelection` passes through unchanged to `financing_resolution.promotion`; `verified_round_amount` can only ever come from the candidate's `ANNOUNCED_ROUND_AMOUNT` and only under `HUMAN` authority — both already enforced inside `promotion.py` itself, unchanged by this file | `run_full_workflow`'s financing decision selects `verified_round_amount: True` and the response's `accepted_verified_round_amount` is asserted `True`, sourced from the real candidate's proposed announced amount |
| A consequential decision requires explicit confirmation | Every decide/classify request model requires `confirm: true`; a pydantic `model_validator` refuses the request (422) otherwise, so a UI cannot submit a decision without its own explicit confirmation step, and the check is server-side, not just a frontend dialog | Enforced by construction — every real decision in `run_full_workflow` passes `"confirm": True` explicitly; omitting it is a pydantic validation failure before any handler code runs |
| No new canonical business rule in this layer | Every write calls an existing, unmodified promotion/classification function (`human_review.create_company_from_candidate`/`attach_candidate_to_company`/`reject_candidate`/`defer_candidate`, `financing_resolution.promotion.create_event_from_candidate`/`attach_candidate_to_event`/`reject_candidate`/`defer_candidate`, `classification.service.classify_company`); this file only shapes HTTP requests/responses around them | `app/v2/tests/architecture/` (894 tests) re-run clean after this increment — no boundary changed |
| Legacy routes unaffected by the new mount | The router is `include_router`ed exactly like `v2_capital_router`, after all legacy route definitions; no legacy route, dependency or migration was touched | `test_legacy_routes_still_behave_normally` (`/health`, `/analyze`'s 401 gate, `/rankings` staying public); the full pre-existing `app/tests/test_backend_authentication.py` (14/14) re-run clean |
| Synthetic/test evidence excluded from ordinary review, never by name matching | `list_company_candidates_for_review`/`list_financing_candidates_for_review` (Increment 18.5) default `include_test_sources=False`, which joins to the candidate's own Source and filters on `source.is_test` — a structural, server-side join, never a string match on the candidate's proposed name or any other content | `run_collection_operations_workflow` builds a "real-looking" candidate name under a source explicitly marked `is_test` and a differently-named candidate under a real source, then asserts the default (test-excluded) listing shows the real one and hides the synthetic one, and that `include_test_sources=true` reveals it |
| The manual collection trigger is admin-gated, server-validated, and cannot run two overlapping collections | `POST /collection-runs/trigger` requires `RequireAdmin`; `TriggerCollectionRequest` validates `max_filings` (1-25) and requires `confirm: true` server-side (a pydantic `model_validator`, same pattern as every decide/classify request); it calls the exact same `run_bounded_collection` the CLI uses, whose single-active-run lock is the database's own partial unique index (`uq_collection_run_one_active_per_job`) — a `CollectionAlreadyRunningError` maps to `409` through `_domain_call`, the same as any other conflict in this file | `run_collection_operations_workflow` starts a run directly via the repository, then asserts a trigger call for the same `job_name` gets `409`; a separate mocked-network trigger call (a different `job_name`) asserts `200` with `triggered_by` equal to the real admin session, never anything client-supplied |

## The one new read added to `app/v2`

`app.v2.classification.service.list_classifications_for_company` (a plain `SELECT`, no write) was added so the
review UI can show a company's existing classifications before a reviewer adds another — it lives in
`classification/service.py` because that module is already the sole writer of
`company_market_classification` and the natural place to read what it wrote; it introduces no new writer and no
new architecture boundary. `app/v2/tests/architecture/` re-run clean (894 passed) after adding it.

## Error mapping

`app/v2_review_api.py` has two error-handling layers, mirroring `app/v2/api.py`'s own convention:

- `_run` — wraps every plain read: `OperationalError`/`DBAPIError` → 503 (generic), anything else unexpected →
  logged (`capture_exception`) and a generic 500. Never leaks a connection string, a query, or a traceback.
- `_domain_call` — wraps every state-changing call (promotion/classification) with the same DB-unavailable/
  unexpected handling, plus typed domain-error → HTTP-status translation using each error's own existing
  `code`/`message` (chosen by the domain, static text, never built from request or payload content — see
  `app/v2/domain/errors.py`'s own doctring): `NotFoundError` → 404, `ConflictError` (and every subtype) → 409,
  `InvalidInputError`/`UnsupportedInputError` → 400, `InvariantViolationError` → 403.

## What this document does not claim

- It does not claim the isolated development database (`venturegps_v2_dev_1801`) used for
  `app/tests/test_v2_review_api.py`'s real, non-mocked end-to-end run is production-grade infrastructure — it
  is the same disposable local Postgres instance the Increment 18.2/18.3 CLI demonstrations already used, never
  the shared preview or production database. Every V2 table except `source` is database-trigger enforced
  append-only (verified directly against this instance during this increment: `information_schema.triggers`
  shows a `BEFORE UPDATE`/`BEFORE DELETE` "is append-only" trigger on every candidate, decision, company,
  financing-event, classification, observation and processing-attempt table) — application-level cleanup after
  a test run is neither possible nor attempted; rows created by real runs accumulate in that disposable
  database by the same design the production system itself uses for its audit trail.
- It does not claim the market-classification decision (`POST /companies/{company_id}/classify`) is backed by
  its own stored evidence record — `classify_company`'s signature (unchanged) takes no evidence parameter; the
  "supporting evidence" the review UI shows before a classification decision is the company's own accepted
  facts (name, identifiers, decision history), not a persisted classification-specific citation. Adding one
  would be a new domain concept, out of scope for this increment.
- It does not add a new authority kind, a new rule, or any automated promotion. Every decision this API can
  produce still requires `AuthorityKind.HUMAN` in practice (`FINANCING_RULE_AUTHORITY` remains empty; company
  attach-by-rule exists in the domain but this API only ever constructs a human authority) — this file cannot
  make VentureGPS decide anything a human reviewer, authenticated as an admin, did not explicitly confirm.
- It does not claim the manual collection trigger is asynchronous or queued. `POST /collection-runs/trigger`
  runs the real, bounded (≤25 filing) collection pipeline synchronously within the HTTP request — there is no
  background job queue anywhere in this codebase (Increment 18.5's own explicit decision against
  Celery/Redis/APScheduler, enforced by the architecture suite's `worker_framework_prefixes` rule). The
  frontend gives this one call a longer timeout than any other request in this file; it is meant for
  occasional operator use, not high-frequency automated triggering (use the `run-collection` CLI on a real
  external schedule for that — see `docs/v2/RUNBOOK_18_5.md`).
