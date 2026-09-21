# SIE Core Platform — Staging Deployment Runbook

Target architecture: **Vercel** (frontend) + **Render** (backend + managed Postgres).
Render was chosen over Railway because it offers a genuinely free-tier Postgres
option suited to a staging environment, and its `render.yaml` Blueprint format
(see `render.yaml` at the repo root) lets one file define both the web service
and the database together.

This document describes how to deploy staging. **No deployment has been
performed** — this is preparation only.

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
  drops or destructively alters existing data.
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
alembic current                              # expect: 0007 (head)
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
  `v2.company_identifier`.
- A second `upgrade` running at the same time waits on a PostgreSQL advisory lock
  (default 30s, `V2_MIGRATION_LOCK_TIMEOUT_SECONDS`) and then finds nothing to do.
- Preview without a database: `alembic upgrade head --sql`.
- Run `upgrade` **before** deploying code that needs a newer V2 schema.
  (Nothing deployed uses V2 tables yet.)

**Rollback.** `alembic downgrade` exists for disposable, dev and test databases
and is tested there. Once V2 holds real evidence, a destructive downgrade is
**not** the recovery strategy: take a backup/snapshot first, then fix forward
with a new migration (expand/contract). `downgrade base` also refuses to drop
schema `v2` if it still contains anything other than Alembic's own bookkeeping, and
**`downgrade` past 0007 refuses to run while any company or resolution history exists, past 0006 while any candidate exists, past 0005 while `v2.processing_attempt` holds rows, past 0004 while
`v2.observation_sighting` does, and past 0003 while `v2.raw_payload` or `v2.observation` do**: evidence is never discarded by a migration.

Whether to automate this (for example a Render pre-deploy command, which I
believe requires a paid plan - verify) is a separate, later decision.
