# Continuous Integration

**Workflow:** `.github/workflows/ci.yml`
**Added:** Audit P0-1 (`docs/portfolio/VENTUREGPS_READINESS_AUDIT.md`, §7) — before this, nothing in the repository ran automatically on push or pull request.

**Status: verified.** Pushed as commit `55b38f2`; the resulting GitHub Actions run (`gh run view 36036368738`) **succeeded end-to-end**: `Backend — VentureGPS V2 (pytest)` in 10m42s, `Frontend — lint, typecheck, tests, build` in 1m24s, both ✓. Confirmed directly via the GitHub CLI (`gh run list`, `gh run view`), not just by reading the commit history. Two informational-only annotations appeared (GitHub's own Node 20→24 runner-forcing notice on `actions/checkout@v4`/`actions/setup-python@v5`/`actions/setup-node@v4`, and a future `ubuntu-latest`→Ubuntu 26 migration notice for October 2026) — neither is a failure and neither requires any change to this workflow today.

## What runs, and when

Two independent jobs, both triggered on every push to `main` and every pull request targeting `main`:

| Job | What it verifies | Runtime (local validation) |
|---|---|---|
| `backend-v2` | The full VentureGPS V2 test suite (`python -m pytest app/v2 -q`) — architecture-boundary tests, pure domain/evidence tests, and every database-backed test, against a fresh, attested, disposable PostgreSQL database created for that run only | ~4m20s, 3,472 tests |
| `frontend` | `npm run lint` (ESLint), `npx tsc --noEmit` (TypeScript), `npm test` (25 suites), `npm run build` (Next.js production build) | ~1–2 min combined |

**Deliberately not run in CI:** the 61 script-style tests under `app/tests/` (legacy SIE). They are not `pytest`-collected (the repo-root `conftest.py` refuses to collect anything outside `app/v2`) and, per their own docstrings, some of them write to the real local `DATABASE_URL` rather than a disposable/isolated database. Wiring them into CI safely would first need the same kind of database-isolation guard `app/v2/tests/db/guard.py` already gives V2 (tracked as Audit P1-d — out of scope for this milestone). Run them locally, individually, exactly as before: `python -m app.tests.<name>`.

## Test database isolation and attestation

The `backend-v2` job provisions its own throwaway PostgreSQL 16 server as a [GitHub Actions service container](https://docs.github.com/actions/using-containerized-services/about-service-containers) — it exists only for that one job run and is discarded with the runner afterward. Nothing about this is new infrastructure; it's the same disposable-database contract `app/v2/tests/db/guard.py` has always enforced locally, just provisioned fresh per run instead of created once by hand.

Before any test runs, the workflow:

1. `CREATE DATABASE venturegps_v2_test;` — a name matching `app/v2/tests/db/guard.py`'s required pattern, `^venturegps_v2_test(_[a-z0-9]+)?$`.
2. `COMMENT ON DATABASE venturegps_v2_test IS 'VENTUREGPS_V2_DISPOSABLE_TEST_DB';` — the **server-side attestation** `guard.py`'s `verify_server_attests_disposable()` checks before any destructive step. A connection string alone is never trusted; the server itself has to carry this marker.

Then `V2_TEST_DATABASE_URL` (and *only* that variable — `DATABASE_URL`/`V2_DATABASE_URL`/`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`TAVILY_API_KEY` are all left unset in the job) points pytest at it. `app/v2/tests/conftest.py`'s own `_isolated_environment` autouse fixture additionally strips `DATABASE_URL`/`V2_DATABASE_URL` from the process environment for the whole test session regardless — CI leaving them unset in the first place just means that fixture's own "does the test DB collide with a production one" check is trivially satisfied. This mirrors the suite's own documented instruction (`app/v2/tests/conftest.py`'s docstring): *"CI should additionally run the suite with `env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u TAVILY_API_KEY pytest`."*

Migrations are **not** a separate CI step. Each database-backed test applies migrations up to head itself, through the `migrated_db` fixture (`command.upgrade(alembic_cfg(), "head")`), against a schema that fixture-level `clean_db`/`reset_database` machinery tears down and recreates per test — an explicit `alembic upgrade head` step before pytest would just be undone by the first test that runs.

CI never touches, and never has credentials for, `venturegps_v2_dev_1801` (local dev) or any preview/production database.

## Reproducing the checks locally

**Backend (from the repo root, with the project's virtualenv active):**

```bash
pip install -r requirements.txt

# Once, to create the disposable database (see docs/v2/DATABASE_MIGRATIONS.md
# for the full local-development version of this):
createdb venturegps_v2_test
psql -d venturegps_v2_test -c "COMMENT ON DATABASE venturegps_v2_test IS 'VENTUREGPS_V2_DISPOSABLE_TEST_DB'"

export V2_TEST_DATABASE_URL='postgresql://localhost/venturegps_v2_test'
python -m pytest app/v2 -q
```

To scope to just the architecture-boundary tests: `python -m pytest app/v2/tests/architecture -q` (no database needed — these are static/AST/import-probe checks, not DB-backed).

**Frontend (from `dashboard/`):**

```bash
npm ci
npm run lint
npx tsc --noEmit
npm test
npm run build
```

`npm run build` needs `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` set to *something* syntactically valid (Clerk's `ClerkProvider`, present in the root layout, validates key **shape** at build time — no network call to Clerk happens during a build). For local development, use a real (free) Clerk dev key pair in `dashboard/.env.local` (see `DEPLOYMENT.md`) or Next's own no-account "keyless" dev mode. CI instead uses fixed, non-secret placeholder values — see "Required non-secret configuration" below.

## Required non-secret configuration

CI sets exactly these environment variables; none are real credentials and none need to be configured as GitHub repository secrets:

| Job | Variable | Value | Why it's safe to hardcode in the workflow |
|---|---|---|---|
| `backend-v2` | `V2_TEST_DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/venturegps_v2_test` | Points only at the job's own throwaway service-container database; `postgres`/`postgres` is that container's own locally-scoped, newly-created-per-run credential, not a shared secret |
| `frontend` | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_test_Y2ktZmFrZS10ZXN0LmNsZXJrLmFjY291bnRzLmRldiQ` | Decodes (base64) to the made-up hostname `ci-fake-test.clerk.accounts.dev$` — syntactically valid per Clerk's own shape check, corresponds to no real Clerk instance |
| `frontend` | `CLERK_SECRET_KEY` | `sk_test_ci_placeholder_not_a_real_credential` | Never sent anywhere during a build; only referenced server-side at *request* time, which `next build` doesn't reach |
| `frontend` | `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | Build-time only; pages that fetch from it (e.g. `/markets`) already fail closed to an empty/"unavailable" state on a fetch error, which is exactly what an unreachable placeholder produces |

No `OPENAI_API_KEY`, `TAVILY_API_KEY`, `ANTHROPIC_API_KEY`, real `DATABASE_URL`, real `CLERK_ISSUER`, `CLERK_AUTHORIZED_PARTIES`, or `ADMIN_USER_IDS` is ever set, read, or needed by either job.

## Investigating a CI failure

- **`backend-v2` fails at "Create and attest the disposable V2 test database"** — the Postgres service container didn't come up healthy in time, or (extremely unlikely, since the database name is freshly created every run) a name collision. Re-run the job; if it persists, check the service container's health-check logs in the run's own log output.
- **`backend-v2` fails inside `pytest`** — read the failing test's name and file directly from the log; this is the same suite you can run locally (see above) against your own disposable database to reproduce.
- **`backend-v2` fails with `UnsafeTestDatabaseError` / "REFUSING to run V2 database tests"** — `app/v2/tests/db/guard.py` refused the database for a specific, printed reason (wrong name shape, wrong host, missing attestation, or a collision with a "production" URL env var). This is the guard working as designed, not a flake; the fix is in the workflow's database-setup step, never in loosening `guard.py` itself.
- **`frontend` fails at lint/typecheck/test** — reproduce with the exact same command locally (see above); no CI-specific environment is involved in these three steps.
- **`frontend` fails at `npm run build`** — if the failure mentions Clerk/publishable key, confirm the workflow's placeholder env vars are still set correctly (see table above) — this is a build-time compatibility check, never a real-account issue. Any other build failure reproduces identically with `npm ci && npm run build` locally using the same placeholder values.
