# SIE Core Platform — Staging Deployment Runbook

Target architecture: **Vercel** (frontend) + **Render** (backend + managed Postgres).
Render was chosen over Railway because it offers a genuinely free-tier Postgres
option suited to a staging environment, and its `render.yaml` Blueprint format
(see `render.yaml` at the repo root) lets one file define both the web service
and the database together.

This document describes how to deploy staging. It originally read "No
deployment has been performed — this is preparation only," written when V2
was new (see the `alembic upgrade head` example further down, which used to
say "expect: 0010 (head)"). **That is no longer accurate and this note
exists so the two don't silently disagree again:** the frontend is live at
`https://app.venturegps.ai/` (confirmed reachable, with its own custom Clerk
auth domain), which by itself means *some* deployment of *something* has
happened. What exactly is deployed — which commit, whether it matches
`main`, and whether its database has ever had V2 migrations applied — is
**not verifiable from this repository or this runbook alone**; see
`docs/portfolio/VENTUREGPS_READINESS_AUDIT.md` §2/§6 for the full, dated
investigation and its explicit UNKNOWNs. The steps below remain the
documented *procedure* for standing up the `render.yaml` staging Blueprint
from scratch; they are not a claim about what is currently running.

## Hosts

- **Frontend**: Vercel (Next.js 16, App Router — zero custom build config needed)
- **Backend**: Render Web Service (Python/FastAPI, `render.yaml` at repo root)
- **Database**: Render managed PostgreSQL (same provider as the backend, defined
  in the same `render.yaml`)

## Required environment variables

### Backend (Render)

| Variable | Source | Notes |
|---|---|---|
| `DATABASE_URL` | Auto-populated by Render from the linked Postgres resource | Do not set manually |
| `OPENAI_API_KEY` | Set manually in the Render dashboard | Secret — never commit |
| `TAVILY_API_KEY` | Set manually in the Render dashboard | Secret — never commit |
| `CORS_ALLOWED_ORIGINS` | Set manually in the Render dashboard | Comma-separated list of allowed frontend origins, e.g. `https://sie-staging.vercel.app`. Unset = local-dev-only origins (see `app/api.py`) |
| `CLERK_ISSUER` | The Clerk instance's Frontend API URL, e.g. `https://your-app.clerk.accounts.dev` (dev) or `https://clerk.yourdomain.com` (production custom domain) — decode it from the `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` set on the frontend, or copy it from the Clerk Dashboard | Required for all four paid analyze endpoints to accept requests — see `app/auth.py`. **No safe default**: unlike `CORS_ALLOWED_ORIGINS`, an unset `CLERK_ISSUER` fails every authenticated request closed (401), it does not fall back to a guessed value |
| `CLERK_AUTHORIZED_PARTIES` | Set manually in the Render dashboard | Comma-separated list of allowed frontend origins that may present a token, e.g. `https://sie-staging.vercel.app`. Unset = the same two local-dev origins `CORS_ALLOWED_ORIGINS` falls back to. Mirrors `CORS_ALLOWED_ORIGINS`'s own pattern; set both together |
| `ADMIN_USER_IDS` | Set manually in the Render dashboard | Comma-separated list of Clerk user IDs (e.g. `user_2abc...,user_2def...`) allowed to call the admin startup-claim review endpoints (`app/auth.py`'s `RequireAdmin`). Backend-only — **never** prefix with `NEXT_PUBLIC_`. Unset or empty = no admins; every admin endpoint fails closed (403), same fail-closed default as an unset `CLERK_ISSUER` |
| `EVIDENCE_V1_ENABLED` | Set manually in the Render dashboard, when ready | `true`/`false` (case-insensitive); unset or anything else = `false`. Server-side-only switch for the Evidence Engine v1 beta path (`app/evidence_v1/config.py::evidence_v1_enabled()`) — see "Evidence Engine v1 database migrations" below. A client can never turn this on by itself; `resolve_engine()` re-checks it on every request regardless of what the client sends. Leave unset until the table has been migrated (next section) |
| `PYTHON_VERSION` | Set in `render.yaml` | Pinned to `3.12.5` to match the version this app has been tested against locally |

### Frontend (Vercel)

| Variable | Value | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | The deployed Render backend's public URL, e.g. `https://sie-backend-staging.onrender.com` | Must be set before the first Vercel build that needs to talk to staging data — it's baked in at build time as a `NEXT_PUBLIC_` var |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | From the Clerk Dashboard → API keys | Safe to expose to the browser by design — it identifies the Clerk instance, it does not authenticate anything on its own |
| `CLERK_SECRET_KEY` | From the Clerk Dashboard → API keys | Server-only — **never** prefix with `NEXT_PUBLIC_`. Used server-side by `@clerk/nextjs` (`ClerkProvider`, `proxy.ts`, `auth()`); never sent to the browser |

Both are required at build time — `ClerkProvider` (rendered in the root
layout, present on every page) throws if `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
is missing/invalid, so `npm run build` will fail without a real key pair. See
"Local development (Clerk)" below for the no-account-needed dev option.

## Local development (Clerk)

Two ways to run `npm run dev` locally, in order of preference:

1. **Keyless mode (no Clerk account needed)** — `@clerk/nextjs` 7.x ships a
   "keyless" onboarding mode: with `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`/
   `CLERK_SECRET_KEY` both unset, running `next dev` auto-provisions a
   temporary, accountless Clerk application scoped to that dev server and
   works immediately — no signup, no dashboard, no keys to copy. This does
   **not** work for `next build` (a production build has no long-running dev
   server to hold the temporary instance), so it's a `dev`-only convenience.
2. **A real (free) Clerk application** — create one at
   [clerk.com](https://clerk.com), copy its publishable/secret key pair into
   `dashboard/.env.local` (not committed — see `dashboard/.gitignore`'s
   existing `.env*` rule), required for `npm run build`/`npm start` and for
   staging/production.

## Backend build/start commands

```
Build:  pip install -r requirements.txt
Start:  uvicorn app.api:app --host 0.0.0.0 --port $PORT
```

No `--reload` in production. `$PORT` is injected by Render at runtime — do not
hardcode a port. Both commands are already encoded in `render.yaml`.

## Frontend environment settings

Vercel auto-detects Next.js — no custom build/output settings are required.
The only setting to configure is the `NEXT_PUBLIC_API_URL` environment variable
above, set per-environment (Preview/Production) in the Vercel project settings.

## CORS setup

`app/api.py` now resolves allowed origins from `CORS_ALLOWED_ORIGINS`
(comma-separated), falling back to the two local-dev origins
(`http://localhost:3000`, `http://127.0.0.1:3000`) when unset — local
development behavior is unchanged. **Never set this to `*`.** Once the Vercel
staging URL is known, set it as `CORS_ALLOWED_ORIGINS` on the Render service
and redeploy (or Render will pick it up on the next deploy/restart).

## Clerk backend auth setup

`app/auth.py` verifies every request to the four paid analyze endpoints
(`/analyze`, `/analyze-startup`, `/analyze-website`, `/analyze-pdf`) against
Clerk's own public JWKS for `CLERK_ISSUER`, and (when present) checks the
token's `azp` claim against `CLERK_AUTHORIZED_PARTIES`. All other endpoints —
Dashboard/analytics, Rankings, Search, Startup Profile, `/health`, `/version`
— stay public and need no Clerk configuration. Set `CLERK_ISSUER` and
`CLERK_AUTHORIZED_PARTIES` on the Render backend once the Clerk application
and Vercel staging URL are both known, alongside `CORS_ALLOWED_ORIGINS` in
step 6 below — they're independent settings but change at the same point in
the deploy sequence.

## Expected deployment order

1. **Create the Render Blueprint** from `render.yaml` (Render dashboard → New →
   Blueprint → point at this repo). This provisions the Postgres database and
   the (not-yet-working) web service.
2. **Set `OPENAI_API_KEY` and `TAVILY_API_KEY`** on the web service in the
   Render dashboard (Blueprint intentionally leaves these blank).
3. **Deploy the backend.** Confirm it starts and the startup migrations run
   cleanly against the fresh, empty staging database (see "Database
   readiness" below).
4. **Note the backend's public URL** (e.g. `https://sie-backend-staging.onrender.com`).
5. **Deploy the frontend to Vercel**, setting `NEXT_PUBLIC_API_URL` to that URL
   before the build.
6. **Set `CORS_ALLOWED_ORIGINS`, `CLERK_ISSUER`, and `CLERK_AUTHORIZED_PARTIES`**
   on the Render backend (the latter two per "Clerk backend auth setup" above)
   to the Vercel URL from step 5, then redeploy the backend so it picks up the
   new origin/issuer.
7. Run the health verification steps below.

## Health verification steps

1. `GET {backend_url}/health` → `{"status": "healthy"}`
2. `GET {backend_url}/version` → confirms `methodology_version` is stamped
   and matches the current constant.
3. Open the deployed frontend → Dashboard loads with an empty/zero state
   (fresh staging DB has no analyses yet — this is expected, not a bug).
4. Sign in via Clerk, then Analyze Startup → submit a real company → confirm
   the analysis completes, redirects to its Startup Profile, and the profile
   renders (six pillars, SPS, evidence). Signed out, the same submission
   should fail with a 401 surfaced as a "session expired, sign in" message,
   not a silent failure or a 500.
5. Confirm that company now appears in Rankings and Search on the deployed
   frontend.
6. Check the browser console for CORS errors specifically — a misconfigured
   `CORS_ALLOWED_ORIGINS` shows up immediately here as blocked requests. A
   misconfigured `CLERK_ISSUER`/`CLERK_AUTHORIZED_PARTIES` instead shows up as
   every authenticated submission returning 401 regardless of sign-in state.

## Rollback basics

- **Frontend**: Vercel keeps every previous deployment; "Promote to Production"
  (or "Redeploy") any prior working deployment from the Vercel dashboard —
  effectively instant, no data implications.
- **Backend**: Render keeps a deploy history per service; roll back to a
  previous deploy from the Render dashboard. Because startup migrations are
  additive-only (`CREATE TABLE IF NOT EXISTS` / `ADD COLUMN`, each wrapped in
  its own try/except), rolling the backend back to an older commit is safe —
  older code simply won't reference newer columns, and no migration ever
  drops or destructively alters existing data. V2's and Evidence v1's own
  tables (`v2.*`, `evidence_v1_analyses`) are migrated manually, not at
  startup, so a backend rollback never touches either — rolling back older
  code simply stops calling the newer routes/tables, same as above.
- **Database**: this is a staging database with no production data to protect;
  if it ever needs to be reset, delete and recreate the Render Postgres
  resource rather than attempting to hand-edit it. Do not do this to the
  production database once one exists.

## VentureGPS V2 database migrations (manual)

V2 owns its own PostgreSQL schema, `v2`, managed by Alembic. It does **not**
touch the legacy `public` tables, and the legacy startup migrations described
above are unchanged. Full design: `docs/v2/DATABASE_MIGRATIONS.md`.

**V2 migrations are run by hand, on purpose.** They do not run at application
import, when FastAPI starts, in the Render build/start commands, or in a
pre-deploy command. Nothing in `render.yaml` or the start command changed.

```bash
# from the repo root, with the venv active
export V2_DATABASE_URL='postgresql://...'   # the intended database (Render: the External Database URL)
alembic current                              # prints "V2 migration target: host:port/database" first - check it
alembic upgrade head
alembic current                              # expect: 0012 (head), as of Increment 18.7
```

- Target resolution: `V2_DATABASE_URL`, else `DATABASE_URL`. **No `.env` file is
  loaded.** The command logs `V2 migration target: <host>:<port>/<database>`
  (never the password) before doing anything - read it before proceeding.
- `alembic current`, `heads` and `history` create nothing. `alembic upgrade head`
  creates schema `v2` (if missing), its version table `v2.alembic_version`, and
  (revision 0002) the `v2.source` table with its guard trigger, (revision 0003) the append-only
  evidence tables `v2.raw_payload` and `v2.observation`, (revision 0004) the append-only
  `v2.observation_sighting` acquisition-history table, (revision 0005) `v2.processing_attempt`
  (processing history, mutable only through its lifecycle), and (revision 0006) the append-only, UNTRUSTED
  candidate tables `v2.company_candidate` and `v2.company_candidate_identifier`, and (revision 0007) the resolution
  boundary: append-only `v2.resolution_decision` plus canonical identity `v2.company`, `v2.company_name` and
  `v2.company_identifier`, and (revision 0008) the append-only, UNTRUSTED `v2.financing_event_candidate` (+ `_amount`, `_date`) tables, and (revision 0009) the financing resolution boundary: append-only `v2.financing_resolution_decision` plus canonical `v2.financing_event` (+ `_stage`, `_type`, `_verified_round_amount`, `_date`).
- A second `upgrade` running at the same time waits on a PostgreSQL advisory lock
  (default 30s, `V2_MIGRATION_LOCK_TIMEOUT_SECONDS`) and then finds nothing to do.
- Preview without a database: `alembic upgrade head --sql`.
- Run `upgrade` **before** deploying code that needs a newer V2 schema.
  Whether anything currently deployed reads V2 tables, and whether preview/
  production have ever had these migrations applied, is **not verifiable
  from this repository** — see `docs/portfolio/VENTUREGPS_READINESS_AUDIT.md`
  §6 (the earlier claim here that nothing deployed uses V2 tables predates
  the live site that now exists and should not be relied on).

**Local isolated dev database, verified 2026-09-24.** `venturegps_v2_dev_1801`
(127.0.0.1:54331 — never preview or production) was confirmed at revision
`0011` by direct read-only query, then upgraded to `0012` (Company Lifecycle,
Increment 18.7) via the exact procedure above. Verified before and after:
Gecko Robotics' canonical company row, name, website identifier, financing
event (verified $125,000,000.00 USD round amount, filing/first-sale dates),
and Robotics market classification are byte-for-byte unchanged (same row
IDs, same timestamps to the microsecond); all pre-existing canonical table
row counts are unchanged; all 10 new lifecycle tables exist and are empty
(no lifecycle candidates were created). `alembic check` against this
database separately flagged a **pre-existing, unrelated** index-direction
drift on `v2.collection_run` (its indexes still carry `DESC`, fixed in the
migration 0011 file before this database's own 0011 was applied — cosmetic/
performance-only, never touches row data) — not introduced by, or connected
to, migration 0012. Preview and production were not touched.

**Rollback.** `alembic downgrade` exists for disposable, dev and test databases
and is tested there. Once V2 holds real evidence, a destructive downgrade is
**not** the recovery strategy: take a backup/snapshot first, then fix forward
with a new migration (expand/contract). `downgrade base` also refuses to drop
schema `v2` if it still contains anything other than Alembic's own bookkeeping, and
**`downgrade` past 0010 refuses to run while any taxonomy version, market or classification exists, past 0009 refuses to run while any canonical financing or resolution history exists, past 0008 refuses to run while any financing candidate exists, past 0007 refuses to run while any company or resolution history exists, past 0006 while any candidate exists, past 0005 while `v2.processing_attempt` holds rows, past 0004 while
`v2.observation_sighting` does, and past 0003 while `v2.raw_payload` or `v2.observation` do**: evidence is never discarded by a migration.

Whether to automate this (for example a Render pre-deploy command, which I
believe requires a paid plan - verify) is a separate, later decision.

## Evidence Engine v1 database migrations (manual)

Evidence Engine v1 owns exactly one additive table, `evidence_v1_analyses`, in the
**default/public** schema — not `v2`, not a new schema of its own. It is a third,
fully independent Alembic environment, distinct from both the legacy ad-hoc
`add_*_column()` migrations above and V2's own `alembic.ini`/`app/v2/migrations/`.
Full architectural rationale (why a third environment, not a reuse of either
existing one): `docs/architecture/EVIDENCE_ENGINE_PRODUCT_INTEGRATION.md` §4.

**Also run by hand, on purpose — same convention as V2.** It does not run at
application import, when FastAPI starts, in the Render build/start commands, or in
a pre-deploy command. Nothing in `render.yaml` or the start command references it.

```bash
# from the repo root, with the venv active
export DATABASE_URL='postgresql://...'   # the SAME target as the app's own runtime database
alembic -c alembic_evidence_v1.ini current   # prints its own version table state - check it
alembic -c alembic_evidence_v1.ini upgrade head
alembic -c alembic_evidence_v1.ini current   # expect: 0001 (head)
```

- Target resolution: `DATABASE_URL` directly (there is no separate
  `EVIDENCE_V1_DATABASE_URL` — this table lives in the same physical database as
  everything else, just a different, independently-tracked migration history). No
  `.env` file is loaded by the Alembic CLI itself; export the variable in the shell
  first.
- Version table: `evidence_v1_alembic_version` (default schema) — a different name
  from both the legacy app's implicit table state and `v2.alembic_version`, so the
  three histories can never collide even though two of them may target the same
  database.
- `alembic -c alembic_evidence_v1.ini current`/`heads`/`history` create nothing.
  `upgrade head` creates `evidence_v1_analyses` (revision 0001) — one `CREATE TABLE`,
  one index (`ix_evidence_v1_analyses_owner_created`), no autogenerate (this
  environment has no reflection/diffing machinery by design — each revision is
  small and hand-written).
- **Ordering relative to the feature flag:** run `upgrade head` **before** setting
  `EVIDENCE_V1_ENABLED=true` anywhere. With the flag off (the default), the table
  is simply unused — `resolve_engine()` never routes a request to the evidence_v1
  path, so a missing table is harmless until the flag flips. With the flag on and
  the table missing, every evidence_v1 request fails closed with a mapped,
  non-leaking `PERSISTENCE_FAILED` → 502 (verified:
  `app/tests/test_evidence_v1_integration.py`) — not a crash, not data loss, but
  not a usable beta either, so there is no reason to flip the flag before this
  step.
- **Ordering relative to the legacy and V2 migrations:** independent of both — it
  shares nothing with either (no foreign key crosses into `v2.*` or the legacy
  `analyses` table), so it can be run before, after, or interleaved with either
  without a correctness concern. There is also no ordering requirement between this
  migration and a deploy of the Evidence-v1 application code itself in either
  direction: with the flag off, neither the route branch nor the table is reachable
  regardless of deploy order.
- Preview without a database: `alembic -c alembic_evidence_v1.ini upgrade head --sql`.
- **Verified locally** against the same `venturegps_v2_dev_1801` instance
  (127.0.0.1:54331) used for V2's own local verification (Task 31): upgrade and
  downgrade both run cleanly; `v2.*` and the legacy `analyses` table are provably
  untouched by either direction (`app/evidence_v1/tests/test_migrations.py`, run as
  `python -m app.evidence_v1.tests.test_migrations` — a script, like the legacy
  tests, not `pytest`, since it lives outside `app/v2` and the root `conftest.py`
  scopes pytest to `app/v2` only). Whether staging/production have ever had this
  migration applied is **not verifiable from this repository** — the same caveat
  that applies to the V2 migrations above applies here.

**Rollback.** `alembic -c alembic_evidence_v1.ini downgrade base` drops
`evidence_v1_analyses` and leaves `evidence_v1_alembic_version` in place, empty (no
custom teardown, unlike V2's schema-drop — there is no schema to drop here). Safe
on a database with no evidence_v1 rows (e.g. before the flag has ever been turned
on anywhere). Once real rows exist, treat this the same as the V2 guidance above:
take a backup first, prefer fixing forward with a new revision over a destructive
downgrade, and never downgrade a database the flag is currently pointed at in any
environment.

**Manual controlled release (no automated gate exists yet).** There is currently no
staged-rollout infrastructure (no canary, no percentage-based flag, no per-user
allowlist) beyond the single global `EVIDENCE_V1_ENABLED` boolean and the client's
own `?engine=evidence_v1` opt-in. The controlled release procedure is therefore
entirely manual: (1) run the migration above against the target database with the
flag still off; (2) set `EVIDENCE_V1_ENABLED=true` only in a controlled
environment (e.g. staging, or a Render environment not linked to the public
production URL); (3) exercise it manually via `?engine=evidence_v1` from a known
test account; (4) only once satisfied, consider enabling it where the public
frontend's "Evidence-based" discoverability checkbox (driven by `GET /version`'s
`evidence_v1_enabled` field — see `docs/architecture/EVIDENCE_ENGINE_PRODUCT_INTEGRATION.md`)
would actually surface it to ordinary users. There is no mechanism to show it to a
subset of production users short of this — building one is future work, not
something to improvise ad hoc here.
