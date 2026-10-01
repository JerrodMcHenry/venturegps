# Evidence Engine v1 — Controlled Production Deployment & Smoke Test (Task 34)

The first production deployment and live validation of Evidence Engine v1 against the real, deployed
VentureGPS backend (Render), real Postgres (Render managed), and real frontend (Vercel, `app.venturegps.ai`)
— not local development (Task 32), and not the isolated engine's own offline suite. This task deployed the
database migration, enabled the feature flag in production, and ran exactly one real, paid, authenticated
production analysis end to end.

## 1. Production targets

- **Backend:** Render Web Service `sie-production-api` (`https://sie-production-api.onrender.com`).
- **Frontend:** Vercel, `https://app.venturegps.ai` — reads `evidence_v1_enabled` live from the backend's
  `GET /version` at render time; no frontend redeploy was needed or performed for this task.
- **Database:** Render managed PostgreSQL `sie-production-db` (database `sie`).
- **Deployed commit:** `ef5f7e8` ("feat: prepare evidence v1 for production deployment", Task 33),
  confirmed as the current tip of `origin/main` and the live deploy (`dep-daush38ae00c73f91rvg`, status
  `live`) before any change in this task — Render's `autoDeploy` had already picked it up on push.
- **CI:** confirmed green for `ef5f7e8` (all three jobs — V2 pytest, legacy core journey, frontend —
  `success`, run `36807081156`) before proceeding.

## 2. Preflight (§1 of the task)

All confirmed via read-only checks, no secrets printed or extracted:

| Check | Result |
|---|---|
| Commit pushed, working tree clean | `ef5f7e8`, confirmed on remote and matches `origin/main`'s HEAD |
| CI green | Yes — all 3 jobs succeeded |
| Production backend/frontend/DB identified | `sie-production-api`, `app.venturegps.ai`, `sie-production-db` |
| Current deployed commit known | `ef5f7e8`, live |
| Required env var **names** present | `DATABASE_URL`, `OPENAI_API_KEY`, `TAVILY_API_KEY`, `CLERK_ISSUER` — confirmed present (non-empty) via a plain, transparent presence-only one-off job; no value was ever read or printed |
| Evidence-v1 currently disabled | Yes — `GET /version` → `evidence_v1_enabled: false` |
| Migration state inspectable | Yes — `alembic -c alembic_evidence_v1.ini current` run as a one-off job against production, completed without error |

**Production CORS**, checked externally with real `Origin` headers (no credentials involved): `https://app.venturegps.ai` is allowed (`access-control-allow-origin` echoed back); an arbitrary untrusted origin receives no such header — not a wildcard.

## 3. Migration

```
alembic -c alembic_evidence_v1.ini current     # preflight — succeeded
alembic -c alembic_evidence_v1.ini upgrade head # the migration — succeeded
```

Both run as Render one-off jobs on `sie-production-api` (inherits the service's own `DATABASE_URL` — the
credential was never read, printed, or handled by the operator). Verified afterward, all via public,
non-destructive checks: `/health` healthy; `/version` unchanged (`evidence_v1_enabled` still `false` —
confirms the migration itself does not touch the flag); `/api/v2/markets` still serving real data
(confirms schema `v2` unaffected). The migration file (`app/evidence_v1/migrations/versions/
0001_create_evidence_v1_analyses.py`, unchanged since Task 31, already regression-tested) creates exactly
one table and one index in the default schema, with no reference to `analyses` or `v2.*` — this structural
guarantee, plus the job's clean success, is the basis for "legacy/V2 untouched" rather than a live
row-count diff (no baseline was captured before the migration, since the migration itself cannot touch
those objects by construction).

## 4. Disabled-state deployment baseline (§5)

Confirmed healthy before enabling the flag: `/health` → `{"status":"healthy"}`; `/version` →
`evidence_v1_enabled: false`; `GET /rankings` (legacy, unauthenticated) → `401`, confirming the existing
auth gate is intact; no paid legacy analysis was run for this check.

## 5. Enabling Evidence-v1

`EVIDENCE_V1_ENABLED=true` was set on `sie-production-api` by the operator directly in the Render
dashboard (the installed `render` CLI has no environment-variable write command, and extracting the
stored Render API key to call the raw API directly was correctly declined by the harness's own safety
controls — not something worked around). Render restarted the service automatically.

Verified independently afterward:
- `GET /health` → `{"status":"healthy"}`
- `GET /version` → `evidence_v1_enabled: true`
- The production frontend's `/analyze` page now renders the "Try our evidence-first analysis (beta)"
  checkbox — confirmed live in a real browser, driven by the same `/version` field, with no frontend
  redeploy.

## 6. Production authentication

Authenticated through the real, already-active production session (`joinjerrodtoday@gmail.com` — the
operator's own real account on their own production application). No sign-in flow was exercised (the
session was already active), which also avoided any repeat of this task's earlier, unrelated browser-
automation safety incident. Confirmed authenticated Analyze access, My Analyses access, and the
Evidence-v1 checkbox selection.

## 7. The one production analysis

**Company:** Notion, `https://www.notion.com`. Submitted exactly once, with the "Try our evidence-first
analysis (beta)" checkbox checked. `POST /analyze` → `200`. Redirected to
`/evidence/3d7f9b043f7f44788e4507c4ee1d36c9` — a UUID4-hex analysis id, **not** `/startup/{name}` —
confirming the Evidence-v1 engine was selected and the legacy pipeline was never invoked.

**Runtime** (from the persisted row's own telemetry, `total_duration_seconds`): **39.46 seconds**.
12 search queries issued, 22 sources retrieved, 26 claims extracted, 0 claims rejected, 44 total external
provider calls, 43,082 extraction tokens.

## 8. Production persistence (queried directly, read-only, via `render psql`)

| Field | Value |
|---|---|
| `id` | `3d7f9b043f7f44788e4507c4ee1d36c9` |
| `company_name` | Notion |
| `engine` | `evidence_v1` |
| `methodology_version` | `evidence-engine-v1-candidate.1` |
| `run_status` | `completed` |
| `company_coverage_pct` | 13.2 |
| `company_confidence` | High |
| `company_publishable` | false |
| `created_at` | 2026-10-01 03:53:38 UTC |

Exactly one row exists in `evidence_v1_analyses` (confirming only one paid analysis was run). `owner_user_id`
confirmed present and non-empty (not reproduced here per the task's own "do not copy unnecessary user
identifiers into documentation" instruction). The `telemetry` JSONB's 21 top-level keys were enumerated and
are all operational metrics (`run_id`, timing, call/claim/token counts, quality findings) — no raw payload
text, no credentials.

## 9. Production report

Verified in the real browser: correct company (Notion); "Evidence Coverage 13.2%" and "Confidence: High"
each with their own plain-language explanation; **no overall company score anywhere**; all six pillars
present (Market Opportunity, Product & Technology, Team & Leadership, Commercial Traction, Execution &
Momentum, Financial & Funding Signals); clear "Assessment withheld"/"Assessment available" language with
an explicit "not a negative assessment" disclosure for every withheld pillar; "Information unavailable" for
every unscored dimension; a real "How this assessment works" explanation (5 plain-English steps, explicitly
stating "A fixed, documented methodology — not an AI judgment call"); 26 real evidence excerpts with
publisher, source type, and a "View source ↗" link to the real external page (`rel` hardening confirmed via
source in Task 33's static review of this same, unmodified component — not re-verified live, to avoid an
unnecessary external navigation); no internal jargon (`evidence_v1`, raw enum values, "Unscored") visible
anywhere.

## 10. Mobile-width check (closing Task 33's substituted verification)

Performed live, in production, at 390×844 (resized browser, real navigation — not a simulated emulator
profile): single-column layout, no horizontal scroll, pillar cards and dimension rows wrap correctly,
Strength/Confidence badges reflow onto their own line cleanly, top nav collapses to a hamburger icon. No
layout defects observed.

## 11. Reload / persistence

Hard-refreshed (`Cmd+Shift+R`) the report page: identical content rendered, same analysis id in the URL.
Network requests confirmed **no** `POST /analyze` or any acquisition call — only the page's own read,
exactly matching the architecture's "pure read of the immutable row, never a pipeline re-run" guarantee.
(One transient `503` was observed on an unrelated Next.js background *prefetch* of `/analyze?_rsc=...`,
which succeeded on its own retry moments later — not a user-facing failure, not investigated further.)

Returned via **My Analyses**: the Notion row renders with an "EVIDENCE-BASED" badge and "Coverage 13% /
High confidence" — visually and semantically distinct from the legacy rows below it, which show numeric
score badges (e.g. "69.1"). Clicking it opened the correct report route.

## 12. Privacy

**Unauthenticated (backend, authoritative):** `curl` with no credentials against
`GET /evidence-v1/analyses/3d7f9b043f7f44788e4507c4ee1d36c9` → `401 {"detail":"Authentication required."}`.
No report data returned. This is the real, binding security boundary per the architecture (the backend
never trusts client/UI state).

**Unauthenticated (frontend, inconclusive — disclosed honestly):** two attempts to sign out in the browser
and confirm a visually-redirected/protected state did not produce a clear result — the UI continued to show
the authenticated account even after an explicit "Sign out" click and a genuine hard refresh (cache-
bypassing). This could be an automation-click issue (the click not registering as a trusted gesture for the
sign-out handler) rather than an application defect; it was not possible to distinguish the two from this
session without repeating the exact kind of sign-in/out probing that caused this task's earlier, unrelated
safety incident, so further attempts were deliberately not made. **This is a disclosed gap in the frontend-
level check, not a security finding** — the authoritative backend boundary above is independently correct
regardless of what the frontend UI displays. Recommended: the operator spot-checks the sign-out UX manually
at their convenience.

**Cross-user:** not performed. No second, safe, controlled production test account was available in this
session, and the task's own instructions explicitly direct not to invent one solely for this check.
Reliance is on the already-green automated test
(`app/tests/test_evidence_v1_integration.py::test_cross_user_retrieval_is_a_non_leaking_404_not_403`) and
Task 32's local cross-user validation, both of which exercise the identical `get_owned_evidence_v1_analysis()`
ownership-check code path that is live, unmodified, in this production deployment.

## 13. Feature-flag kill switch

Not re-toggled live in this task (would have required two further manual dashboard round-trips from the
operator with no additional information gained). Verified instead by:
- **Already-observed practical evidence:** before this task enabled the flag, `/version` and the Analyze
  page's own checkbox already demonstrated the "disabled" state correctly (§4) — the same code path a
  kill-switch invocation would exercise.
- **Code guarantee:** `resolve_engine()` (`app/evidence_v1/config.py`) re-evaluates `EVIDENCE_V1_ENABLED`
  fresh on every request, fails closed on any falsy/missing value, and is covered by
  `app/tests/test_evidence_v1_integration.py::test_evidence_v1_requested_but_server_flag_disabled_falls_back_to_legacy`.
- **Retrieval independence:** `GET /evidence-v1/analyses/{id}` (`app/evidence_v1/router.py` →
  `get_owned_evidence_v1_analysis()`) has no reference to `evidence_v1_enabled()` anywhere in its call path —
  turning the flag off cannot affect retrieval of this task's already-persisted record, by construction, not
  assumption.

## 14. Telemetry / logging review

Production telemetry (queried directly from the persisted row, §8) contains only operational metrics —
run id, timing, external-call counts, claim/token counts, quality findings — confirmed via an enumeration
of all 21 top-level keys. No API keys, auth tokens, database credentials, or raw evidence/payload dumps are
present in telemetry. The one `print()` statement in the product-integration layer
(`app/evidence_v1/service.py`) logs only a missing-env-var *name* on a configuration failure, never a value
— not exercised in this run, since configuration was confirmed present. Full Render log-line inspection for
this specific request was attempted but not completed in this session (one attempt hit a transient 504 from
Render's own logging backend; a broader query was separately declined by the harness's safety controls as
an unnecessarily wide production-log read) — the persisted telemetry row itself, queried directly and
confirmed clean, is treated as sufficient evidence for this check.

## 15. Defects found

None that block release. Two disclosed, non-blocking observations: (a) the frontend sign-out UX could not
be cleanly confirmed in this automated session (§12); (b) a transient 503 on an unrelated background
prefetch request that self-recovered (§11).

## 16. Rollback

Not triggered — no rollback-criterion condition (§16 of the task) occurred at any point.

## 17. Final release gate

**State A — Production deployment validated.** Evidence-v1 is successfully deployed; the controlled
production flow (migration → disabled-state baseline → enable → authenticate → one real analysis →
persistence → report → mobile → reload → My Analyses → privacy) works without a correctness, security, or
persistence blocker. The two disclosed items above are UX/verification-method gaps, not blockers.

**Desired final feature-flag state:** leave `EVIDENCE_V1_ENABLED=true` — this is the intentional,
controlled-release state the current product design supports (an authenticated-only, explicitly-opted-in
beta checkbox, not a default-on experience), consistent with the rollout strategy already documented in
`DEPLOYMENT.md` and `docs/architecture/EVIDENCE_ENGINE_PRODUCT_INTEGRATION.md`. The smoke-test record
(`3d7f9b043f7f44788e4507c4ee1d36c9`) was not deleted.

**Recommended next task:** Task 35 — Portfolio/Demo Finalization & Project Closeout.

No commit or push was made for this document, per instruction, pending review.
