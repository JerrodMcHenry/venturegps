# Evidence Engine v1 — Product End-to-End Validation 001 (Task 32)

The first validation of the complete, real, authenticated-browser product flow for Evidence Engine v1 —
not the isolated engine (Tasks 22/24/26/28/30), and not a mocked backend integration test (Task 31). This
task is observation and validation only; no code was changed.

## 1. Environment

- **Type:** local development.
- **Commit:** `163dde8` ("feat: integrate evidence engine v1 behind feature flag") — Task 31's own commit,
  confirmed checked out, working tree clean before and throughout this task.
- **Migration state:** `alembic -c alembic_evidence_v1.ini current` → `0001 (head)`.
- **Backend:** `uvicorn app.api:app --port 8000`, restarted at the start of this task so it picked up a
  locally-added `EVIDENCE_V1_ENABLED=true` in `.env` (the only local config change made for this
  validation; restored to its prior, unset/off state at the end — see §13).
- **Frontend:** the dashboard's existing `next dev` process on port 3000, unmodified, pointed at the
  local backend (`NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`).
- **Provider keys:** `OPENAI_API_KEY`/`TAVILY_API_KEY` confirmed present (length-only, never printed).
- **Authentication:** real Clerk (Development mode instance). No existing test account existed in this
  project; one was created for this validation via Clerk's own documented dev-mode test convention
  (a `+clerk_test@` email alias with the fixed test OTP `424242`) — the same category of allowance as a
  payment provider's published test card numbers, used only against this local dev host. Credentials were
  never printed in chat.

## 2. Preflight (§1)

All confirmed before any paid call: commit, clean tree, `EVIDENCE_V1_ENABLED=true` locally, provider keys
present, `DATABASE_URL` configured, migration at head, frontend pointed at the local backend,
authentication functional (confirmed in §4), and — via direct, side-effect-free inspection of
`resolve_engine()` (no HTTP call) — that an ordinary request with no explicit engine selection resolves
to `Engine.LEGACY` even with the flag on.

## 3. Company analyzed

**Notion**, `https://www.notion.com` — the same canonical website used in every prior Evidence Engine
live validation (Tasks 24/28/30).

## 4. Authentication result

Real Clerk sign-up (dev-mode test email + OTP) succeeded on the first attempt; the browser was correctly
redirected to `/analyze?engine=evidence_v1` post-authentication. Confirmed working both for the owning
account and for a second, independently-created account (§10).

## 5. Submission, exactly once

Navigated to `/analyze?engine=evidence_v1` → clicked "Analyze My Startup" → the "Evidence Engine v1
(controlled beta)" panel rendered correctly (confirming the query-param gate works) → entered
Company Name "Notion" and Company Website `https://www.notion.com` → submitted once. No rerun.

**Loading state observed:** "Analyzing startup…", "VentureGPS is running Evidence Engine v1: gathering
and grounding real evidence, then evaluating it against the six Intelligence Pillars. Usually 30-60
seconds", a live elapsed-time counter, and the honest, static Evidence-v1-specific stage list
(Researching public sources / Retrieving and grounding evidence / Structuring claims / Evaluating
methodology / Preparing report) with the explicit disclaimer that this is not live per-stage progress.

**Total observed runtime:** ~30-35 seconds (submitted shortly after 17:37:19 local time; the persisted
row's `created_at` is `17:37:51.786962-07`), consistent with the UI's own "usually 30-60 seconds" copy and
materially faster than the legacy path's "usually 2-4 minutes."

**Backend log** (`POST /analyze` access-log line only — no bodies, no secrets):
```
INFO: 127.0.0.1:xxxxx - "OPTIONS /analyze HTTP/1.1" 200 OK
INFO: 127.0.0.1:xxxxx - "POST /analyze HTTP/1.1" 200 OK
```
One `POST /analyze`, `200 OK`. No raw internal exception ever appeared in the browser.

## 6. Engine-selection / provider / acquisition result (§4)

- Frontend sent `engine=evidence_v1` (confirmed by the Evidence-v1-specific panel rendering and loading
  copy, which only render when the query param is present — Task 31's own regression test
  (`test_form_only_requests_evidence_v1_via_an_explicit_query_param`) already proves this is the only way
  the field gets sent).
- Server resolved `Engine.EVIDENCE_V1` (confirmed: the response carried `engine: "evidence_v1"` and
  `methodology_version: "evidence-engine-v1-candidate.1"`, and the redirect went to `/evidence/{id}`, not
  `/startup/{name}` — only the evidence_v1 branch ever produces that response shape).
- The legacy workflow (`run_due_diligence()`) was not invoked for this request — confirmed structurally
  (the evidence_v1 branch `return`s before any legacy code runs, per Task 31's own code) and
  observationally (a legacy run takes minutes and produces a `/startup/{name}` redirect; this one did
  neither).
- Real production provider adapters were used — confirmed by the real, varied, dated, source-attributed
  evidence that appears in the persisted result (§7) — content no mock/fixture in this codebase produces.
- Acquisition completed, persistence succeeded, the API returned a stable `analysis_id`
  (`a9b5d1fa37e7461fb70b9a7758f0d761`), and no raw internal exception appeared anywhere in the browser.

## 7. Persistence result (§5)

Queried directly against the real database (values shown; `owner_user_id` is a Clerk subject identifier,
not sensitive user content, and is not reproduced in this report's own narrative elsewhere):

| Field | Value |
|---|---|
| `id` | `a9b5d1fa37e7461fb70b9a7758f0d761` (UUID hex, stable) |
| `owner_user_id` | present, a real Clerk user id |
| `company_name` | `Notion` |
| `canonical_website` | `https://www.notion.com` |
| `engine` | `evidence_v1` |
| `methodology_version` | `evidence-engine-v1-candidate.1` |
| `stage` | `Undetermined` |
| `run_status` | `completed` |
| `company_coverage_pct` | `9.0` |
| `company_confidence` | `High` |
| `company_publishable` | `false` |
| `created_at` | present (timestamptz) |
| `result` (JSONB) | present |
| `telemetry` (JSONB) | present |

**Legacy `analyses` table isolation:** confirmed untouched by this run — zero new rows matching `Notion`
in the time window around this submission; the most recent row in the entire table predates this
submission by several hours (unrelated residue from earlier Task 31 test-suite verification work, not
from this run).

## 8. Navigation result (§6)

Browser redirected to `/evidence/a9b5d1fa37e7461fb70b9a7758f0d761` immediately on completion. The route
loaded successfully and rendered the persisted report. Confirmed via backend access log that the report
is read-only: every subsequent load of this URL produced exactly one
`GET /evidence-v1/analyses/{id} 200 OK` and never another `POST /analyze` — the report never reruns
acquisition.

## 9. Report UX result (§7)

**Header:** Notion, `https://www.notion.com` (linked), "Analyzed 2026-09-30", "Evidence Engine
evidence-engine-v1-candidate.1" — all correct.

**Company state:** Coverage 9.0%, Confidence High, Status "Not yet publishable", with explicit,
itemized withholding reasons ("company-level weighted coverage 9.0% < floor 40.0%", "only 1 published
pillar(s) < floor 2"). **No overall company score anywhere on the page** — confirmed by direct text
extraction of the full rendered page.

**Six pillars**, all present:

| Pillar | Status | Strength | Coverage | Confidence |
|---|---|--:|--:|---|
| Market Opportunity | Withheld | — | 0.0% | Low |
| Product & Technology | **Published** | **8.0** | 50.0% | High |
| Team & Leadership | Withheld | — | 0.0% | Low |
| Commercial Traction | Withheld | — | 0.0% | Low |
| Execution & Momentum | Withheld | — | 0.0% | Low |
| Financial & Funding Signals | Withheld | — | 0.0% | Low |

Exactly matches the pattern every prior Notion live evaluation (Tasks 24/28/30) found — a strong,
reassuring integration-correctness signal (the real engine behaves identically whether invoked from a
scratchpad script or from the real product). Each withheld pillar shows its own specific reason and the
explicit line "This reflects missing or insufficient evidence, not a negative assessment." Within
Product & Technology, 2 of 4 dimensions scored (differentiation_claim_corroboration 8.0/10, defensibility
_signal 8.0/10) and 2 correctly show "Unscored" (product_existence_maturity, technical_depth_signal) —
confirming Unscored is visually and textually distinguished from a negative result, never styled as a
low score.

**Evidence:** expanding a scored dimension and the "All evidence and technical detail" section both
render real, individually-sourced excerpts — e.g. *"Among Notion's many strengths is its ability to
integrate seamlessly..."* (www.jotform.com, Independent Reporting, "View source ↗"), *"Notion generated
$400 million in annual revenue in 2024..."* (taptwicedigital.com), *"$600 million in annual recurring
revenue... by early 2026"* (valueaddvc.com), among 19 total claims from a genuinely varied set of
independent sources (jotform.com, spinach.ai, eesel.ai, leadiq.com, lennysnewsletter.com, unifygtm.com,
taptwicedigital.com, sqmagazine.co.uk, valueaddvc.com, competitiveintelligencealliance.io,
cofounderbase.com). Each item shows the claim, publisher, source type ("Independent Reporting"), and an
outbound link — never implying the URL alone means independent verification.

**Information gaps:** unknown does not visually read as poor performance — every withheld pillar and
Unscored dimension is paired with its own specific, honest reason text, never a bare "0" or a red/negative
styling.

**Security:** evidence text (claim quotes, excerpts) rendered as plain text throughout — no broken markup,
no executable content, confirmed both visually (screenshots) and via `get_page_text` extraction (which
would surface raw HTML artifacts if present; none were found). Task 31's own regression test already
proves the component never uses `dangerouslySetInnerHTML`; this run is consistent with that.

## 10. Refresh / My Analyses result (§8/§9)

- **Hard navigation to the same URL:** reloaded successfully, identical analysis_id, identical Coverage/
  Confidence/Status/pillar data. Backend log shows only a new `GET /evidence-v1/analyses/{id}` — no new
  `POST /analyze`, no new provider calls.
- **My Analyses:** the Notion entry appears correctly — company name, "Sep 30, 2026" date, an "EVIDENCE
  V1" badge, "Coverage 9%" (styled distinctly from the legacy score badge — confirmed by direct
  inspection, never a 0-100-tiered color), and "High confidence" text. Clicking it navigated to the exact
  same, correct `/evidence/{id}` report.

## 11. Privacy/ownership result (§10) — release-blocker check

- **Owner access:** works correctly (§8-9 above).
- **Unauthenticated access:** verified at BOTH layers. Backend: `curl` with no Authorization header
  against `GET /evidence-v1/analyses/{id}` → `401 {"detail":"Authentication required."}` — no report data,
  no leak. Frontend: a genuinely signed-out browser tab navigating directly to `/evidence/{id}` was
  cleanly redirected to `/sign-in?redirect_url=...`, no report content ever rendered.
- **Cross-user access:** a second, independently-created real account (`ventgps.task32.crossuser+clerk_
  test@example.com`) was navigated to the EXACT SAME analysis URL. Result: a generic "Analysis not
  found — This analysis doesn't exist, or isn't one you have access to." page — never the report content,
  never a distinguishing message. Backend log confirms `404 Not Found` (never `403`) for this request.
  This second account's own "My Analyses" page correctly shows the honest empty state (zero entries) —
  confirming no cross-contamination in either direction.

**No privacy failure of any kind was found.** This release-blocker check passed cleanly.

## 12. Feature-flag behavior (§11)

Verified by direct, side-effect-free inspection of `resolve_engine()` (no HTTP call, no analysis
triggered):

- **Flag enabled, no explicit engine selection:** `resolve_engine(None)` → `Engine.LEGACY`. An ordinary
  `/analyze` submission would still run the unmodified legacy pipeline even with `EVIDENCE_V1_ENABLED=
  true` server-side.
- **Flag disabled, `evidence_v1` explicitly requested:** `resolve_engine("evidence_v1")` → `Engine.LEGACY`
  (simulated via a one-off subprocess environment override, never touching the running server or `.env`).
  Matches the implemented contract exactly: the client's request alone is never authorization.

## 13. Local configuration restored

`EVIDENCE_V1_ENABLED` removed from `.env` (restored to unset/off, its state before this task); the backend
was restarted once more so its live state matches. Confirmed post-restart: `evidence_v1_enabled()` →
`False`.

## 14. Defects (§12)

### Blocker
None found.

### Important
None found.

### Polish
- The initial click on the "Analyze My Startup" chooser card did not register on the first attempt during
  this session's own browser automation (a second click, via an explicit element reference, succeeded) —
  observed only through automated clicking, not identified as a real user-facing interaction issue; worth
  a quick manual-mouse check in a future UX pass, not treated as a defect here since it could equally be
  an automation-tooling artifact.
- No other cosmetic issues observed in this pass.

## 15. Legacy test-debt note (§13)

The six pre-existing `/rankings`-related legacy test failures (`test_founder_actions.py`,
`test_founder_evidence.py`, `test_fundraising_readiness.py`, `test_pitch_deck_coach.py`,
`test_startup_membership.py`, `test_v2_review_api.py`, documented in Task 31's own completion report) were
**not** re-examined or touched in this task, per its own explicit instruction. They remain known test debt
requiring triage before final deployment-readiness signoff. Nothing observed in this live validation
suggests they are related to the Evidence-v1 flow.

## 16. Decision gate

### **A — Integrated flow validated.**

The complete real flow — authenticated browser, explicit engine selection, real acquisition providers,
real persistence, a stable analysis id, a correct redirect, authenticated ownership-scoped retrieval, a
correctly-rendered evidence-first report, persistence through a hard refresh, correct My Analyses
integration, and a verified privacy boundary (unauthenticated AND cross-user, both at the frontend and
backend layer) — all worked exactly as designed, with zero correctness, privacy, or persistence blockers
found.

## 17. Recommended next task

**Evidence-v1 Product UX & Deployment Readiness** — per this task's own instruction: fix the (zero found,
but watch for) important/polish issues, make Evidence-v1 appropriately discoverable (today it is reachable
only via the `?engine=evidence_v1` query parameter, by design), triage the six stale legacy `/rankings`
tests, verify deployment migration/configuration steps, and prepare a controlled, wider deployment.
