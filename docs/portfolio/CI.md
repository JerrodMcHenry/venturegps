# Continuous Integration

**Workflow:** `.github/workflows/ci.yml`
**Added:** Audit P0-1 (`docs/portfolio/VENTUREGPS_READINESS_AUDIT.md`, §7) — before this, nothing in the repository ran automatically on push or pull request. **Extended:** Portfolio Release Task 1 — added `backend-legacy-core-journey` (below), covering the legacy backend's core user journey (unified analyze, auth, PDF/website ingestion, saved startups, admin authorization), which the original P0-1 workflow explicitly excluded. **Extended again:** the IPv6/IPv4 address-selection fix added 7 tests to `test_website_url_security.py` (12 → 19) without adding a new file or CI step; Portfolio Release Task 2 added a new file and a new step, `test_ai_request_reliability.py` (AI request retry/backoff policy).

**Status:**
- `backend-v2` / `frontend`: **verified on GitHub.** Pushed as commit `55b38f2`; the resulting Actions run (`gh run view 36036368738`) succeeded end-to-end (see below for details, unchanged since).
- `backend-legacy-core-journey`: **verified locally only, not yet pushed.** Per each task's own constraints (no commit/push), this job has not run on GitHub Actions yet at its current, 8-file shape. All eight test files it now runs were verified in this session against a fresh, local, disposable PostgreSQL 16 database using the exact same `DATABASE_URL`/`OPENAI_API_KEY`/`TAVILY_API_KEY`/`CLERK_ISSUER` values the workflow sets — **112/112 individual tests passed** across all eight files. See "Local verification results" below.

## What runs, and when

Three independent jobs, all triggered on every push to `main` and every pull request targeting `main`:

| Job | What it verifies | Runtime (local validation) |
|---|---|---|
| `backend-v2` | The full VentureGPS V2 test suite (`python -m pytest app/v2 -q`) — architecture-boundary tests, pure domain/evidence tests, and every database-backed test, against a fresh, attested, disposable PostgreSQL database created for that run only | ~4m20s, 3,472 tests |
| `backend-legacy-core-journey` | Eight `app/tests/*.py` script-style test files covering the legacy backend's core user journey plus AI request reliability (see table below), against a fresh disposable PostgreSQL 16 service container | ~1–2 min combined (local validation, eight sequential steps) |
| `frontend` | `npm run lint` (ESLint), `npx tsc --noEmit` (TypeScript), `npm test` (25 suites), `npm run build` (Next.js production build) | ~1–2 min combined |

### `backend-legacy-core-journey`: which tests run, and which remain excluded

**Included (8 files, one CI step each, 112 individual tests):**

| File | Covers | Individual tests |
|---|---|---|
| `test_backend_authentication.py` | Clerk JWT verification gate: missing/malformed/expired/wrong-issuer/wrong-party/`alg:none`-attack tokens, valid-token pass-through, `users` row creation/reuse, no internal-error leakage | 14 |
| `test_analyze_unified.py` | `POST /analyze`'s multi-source assembly (website + pitch deck + text, any combination), input validation, size bounds, backward-compatible provenance | 12 |
| `test_analyze_unified_concurrency.py` | Real uvicorn server, real concurrent HTTP requests: `/health` stays responsive during a slow `/analyze` call; the same-user concurrency lock (`analysis_runs` partial unique index) is race-safe under genuine concurrent load, not just correct sequentially | 2 |
| `test_pdf_ingestion.py` | Pitch deck / PDF ingestion hardening: size cap, magic bytes, page cap, encrypted/corrupt/empty PDFs, `analysis_type` provenance threading | 15 |
| `test_website_url_security.py` | Website ingestion SSRF hardening: scheme allow-listing, private/loopback/link-local/cloud-metadata-address rejection, DNS-rebinding-safe IP pinning, bounded redirects, oversized-response rejection, deterministic IPv4-preferred/bounded-fallback address selection | 19 |
| `test_saved_startups.py` | Saved-startups/watchlist DB functions and `/me/saved-startups` endpoints: cross-user isolation, auth gating, idempotent save/unsave, no membership side effects | 19 |
| `test_security_hardening.py` | Admin-only authorization on `GET/PUT/DELETE /analyses/*`, removed unauthenticated `/migrate/*` routes stay gone, migration helpers still run at startup, public routes stay public | 24 |
| `test_ai_request_reliability.py` | `app/ai/pillar_shared.py::call_analysis_model()`'s bounded retry policy: first-attempt success, transient-failure-then-success, retry exhaustion, permanent failures never retried, exact exponential-backoff-with-jitter values, retry count never exceeds the configured bound (see `docs/portfolio/AI_REQUEST_RELIABILITY.md`) | 7 |

**Deliberately still excluded (54 remaining files under `app/tests/`):** everything covering Idea Lab/Build, Investor Workspace, Founder Workspace (actions/evidence/missions/reanalysis), Venture financials/hiring/scenarios/graduation/history/share, Fundraising Readiness, Pitch Deck Coach, SIE v2/SPS v3 methodology and calibration, Discovery/Compare, Product Analytics, Observability, Startup Claims/Membership/Entity-Migration, and the legacy `test_v2_review_api.py`. These are real, working test files — this task's scope was specifically the core user journey the read-only audit named (unified analysis, auth, PDF/website ingestion, saved startups, security hardening), not the full `app/tests/` directory. Wiring the rest in is the same mechanical pattern (verify DB/env assumptions, add a step) and can be done incrementally; not attempted here per the task's own scope. Run any of them locally, individually, exactly as before: `python -m app.tests.<name>`.

Not `pytest`-collected either way (the repo-root `conftest.py` refuses to collect anything outside `app/v2`) — both the included and excluded files here are run as plain Python scripts (`python -m app.tests.<name>`), each with its own hand-rolled `PASS`/`FAIL`/exit-code runner.

## Test database isolation and attestation

The `backend-v2` job provisions its own throwaway PostgreSQL 16 server as a [GitHub Actions service container](https://docs.github.com/actions/using-containerized-services/about-service-containers) — it exists only for that one job run and is discarded with the runner afterward. Nothing about this is new infrastructure; it's the same disposable-database contract `app/v2/tests/db/guard.py` has always enforced locally, just provisioned fresh per run instead of created once by hand.

Before any test runs, the workflow:

1. `CREATE DATABASE venturegps_v2_test;` — a name matching `app/v2/tests/db/guard.py`'s required pattern, `^venturegps_v2_test(_[a-z0-9]+)?$`.
2. `COMMENT ON DATABASE venturegps_v2_test IS 'VENTUREGPS_V2_DISPOSABLE_TEST_DB';` — the **server-side attestation** `guard.py`'s `verify_server_attests_disposable()` checks before any destructive step. A connection string alone is never trusted; the server itself has to carry this marker.

Then `V2_TEST_DATABASE_URL` (and *only* that variable — `DATABASE_URL`/`V2_DATABASE_URL`/`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`TAVILY_API_KEY` are all left unset in the job) points pytest at it. `app/v2/tests/conftest.py`'s own `_isolated_environment` autouse fixture additionally strips `DATABASE_URL`/`V2_DATABASE_URL` from the process environment for the whole test session regardless — CI leaving them unset in the first place just means that fixture's own "does the test DB collide with a production one" check is trivially satisfied. This mirrors the suite's own documented instruction (`app/v2/tests/conftest.py`'s docstring): *"CI should additionally run the suite with `env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u TAVILY_API_KEY pytest`."*

Migrations are **not** a separate CI step. Each database-backed test applies migrations up to head itself, through the `migrated_db` fixture (`command.upgrade(alembic_cfg(), "head")`), against a schema that fixture-level `clean_db`/`reset_database` machinery tears down and recreates per test — an explicit `alembic upgrade head` step before pytest would just be undone by the first test that runs.

CI never touches, and never has credentials for, `venturegps_v2_dev_1801` (local dev) or any preview/production database.

`backend-legacy-core-journey` provisions its own separate, similarly throwaway PostgreSQL 16 service container — a different container from `backend-v2`'s, each job gets its own, neither can see the other's. There is no V2-style fail-closed guard for legacy tests (`app/v2/tests/db/guard.py` is V2-only), because there's nothing to guard against here in CI: `DATABASE_URL` is set to exactly one value for the whole job — `postgresql://postgres:postgres@localhost:5432/venturegps_legacy_ci_test`, the service container's own database — and nothing else is ever a candidate. Seven of the eight test files import `app.api` at module load, which runs legacy's full additive migration sequence (`create_tables`/`add_*_columns`, `app/api.py`) against that URL before any test function runs; this is the same thing that already happens the first time any of these files is run against a real local `DATABASE_URL`, just against a database that exists for one job run and nothing else. (`test_ai_request_reliability.py` is the one exception — it only imports `app.ai.pillar_shared`, never `app.api`/`app.database.db`, and needs no database at all; `DATABASE_URL` is simply unused for that one step, harmlessly.) The container (and every row in it) is discarded with the runner when the job ends.

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

**Legacy core-journey tests (from the repo root, with the project's virtualenv active):**

```bash
pip install -r requirements.txt

# Once, to create the disposable database:
createdb venturegps_legacy_ci_test

export DATABASE_URL='postgresql://localhost/venturegps_legacy_ci_test'
export OPENAI_API_KEY='sk-test-ci-placeholder-not-a-real-credential'
export TAVILY_API_KEY='tvly-test-ci-placeholder-not-a-real-credential'
export CLERK_ISSUER='https://test-instance.clerk.accounts.dev'

python -m app.tests.test_backend_authentication
python -m app.tests.test_analyze_unified
python -m app.tests.test_analyze_unified_concurrency
python -m app.tests.test_pdf_ingestion
python -m app.tests.test_website_url_security
python -m app.tests.test_saved_startups
python -m app.tests.test_security_hardening
python -m app.tests.test_ai_request_reliability
```

This is exactly the sequence used for this task's own local verification (see "Local verification results" below) — substitute your local Postgres role for a bare `createdb`/connection string if your setup needs one (e.g. `createdb -U postgres venturegps_legacy_ci_test`).

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
| `backend-legacy-core-journey` | `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/venturegps_legacy_ci_test` | Points only at this job's own separate throwaway service-container database; same locally-scoped, newly-created-per-run credential pattern as `backend-v2` above |
| `backend-legacy-core-journey` | `OPENAI_API_KEY` | `sk-test-ci-placeholder-not-a-real-credential` | Never sent in a real request — every test monkeypatches the actual call sites; exists only so `OpenAI(api_key=...)` constructs without error at import time |
| `backend-legacy-core-journey` | `TAVILY_API_KEY` | `tvly-test-ci-placeholder-not-a-real-credential` | Same reasoning as `OPENAI_API_KEY` above, for `TavilyClient(api_key=...)` |
| `backend-legacy-core-journey` | `CLERK_ISSUER` | `https://test-instance.clerk.accounts.dev` | Never the issuer any token is actually checked against — every authenticated test monkeypatches `app.auth.CLERK_ISSUER` (and the JWKS client, and authorized-parties resolution) for its own duration; exists only so the module-level `os.getenv("CLERK_ISSUER", "")` has a non-empty starting value |
| `frontend` | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_test_Y2ktZmFrZS10ZXN0LmNsZXJrLmFjY291bnRzLmRldiQ` | Decodes (base64) to the made-up hostname `ci-fake-test.clerk.accounts.dev$` — syntactically valid per Clerk's own shape check, corresponds to no real Clerk instance |
| `frontend` | `CLERK_SECRET_KEY` | `sk_test_ci_placeholder_not_a_real_credential` | Never sent anywhere during a build; only referenced server-side at *request* time, which `next build` doesn't reach |
| `frontend` | `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | Build-time only; pages that fetch from it (e.g. `/markets`) already fail closed to an empty/"unavailable" state on a fetch error, which is exactly what an unreachable placeholder produces |

`ADMIN_USER_IDS` is never set in `backend-legacy-core-journey`: `test_security_hardening.py` monkeypatches `app.auth._resolve_admin_user_ids()` directly, so there's nothing for the env var to do. No `ANTHROPIC_API_KEY`, real `DATABASE_URL`, real `CLERK_ISSUER`, or `CLERK_AUTHORIZED_PARTIES` is ever set, read, or needed by any job.

## Local verification results (cumulative, most recent run)

All eight files were run against a fresh local disposable PostgreSQL 16 database (`createdb venturegps_legacy_ci_test`, dropped afterward), with `DATABASE_URL`/`OPENAI_API_KEY`/`TAVILY_API_KEY`/`CLERK_ISSUER` set to the exact values the workflow now sets (see the "Reproducing the checks locally" command block above) — the same commands and environment `backend-legacy-core-journey` runs, just outside GitHub Actions:

| File | Result |
|---|---|
| `test_backend_authentication.py` | 14/14 passed |
| `test_analyze_unified.py` | 12/12 passed |
| `test_analyze_unified_concurrency.py` | 2/2 passed |
| `test_pdf_ingestion.py` | 15/15 passed |
| `test_website_url_security.py` | 19/19 passed |
| `test_saved_startups.py` | 19/19 passed |
| `test_security_hardening.py` | 24/24 passed |
| `test_ai_request_reliability.py` | 7/7 passed |
| **Total** | **112/112 passed** |

`test_ai_request_reliability.py` is fully offline like every other step in this job: `client.chat.completions.create()` is monkeypatched to canned `openai` SDK exceptions/responses, and `time.sleep()`/`random.random()` are also monkeypatched, so no real OpenAI request is ever made and no step actually waits out a backoff delay — the whole file completes in well under a second despite exercising backoff delays of up to several seconds on paper. See `docs/portfolio/AI_REQUEST_RELIABILITY.md` for the retry policy itself.

The first run of each file prints its own migration output (`... table created successfully`, idempotent `ALTER TABLE ... ADD COLUMN` calls) as `app.api` builds the schema fresh against the empty disposable database — expected, not a failure, and the same output you'd see the first time any of these files runs against any brand-new `DATABASE_URL`. `test_analyze_unified_concurrency.py` also prints two Python tracebacks mid-run — these are the test's own intentional fake pipeline failures (`RuntimeError("intentional fake failure -- only call count/status matter here")`), asserted on by the test itself, not errors.

**Unresolved / worth knowing before relying on this job:**

- **Not yet run on GitHub Actions.** Per this task's constraints, nothing was pushed — the workflow file's correctness is verified (valid YAML, exact env/command reproduction of the passing local run), but the actual hosted-runner execution is unverified until it runs there. First push to a branch/PR should be watched once, the same way `55b38f2`'s `backend-v2`/`frontend` run was confirmed via `gh run view`.
- **`test_analyze_unified_concurrency.py` has pre-existing timing sensitivity**, not introduced by this change: it asserts `GET /health` responds in under 1.5 seconds while a slow fake `/analyze` call is in flight, using fixed `time.sleep()` calls to synchronize threads and a real uvicorn server on hardcoded ports 8099/8100. A sufficiently slow or contended GitHub-hosted runner could in principle make this flake; per this task's "minimum justified changes" scope, its timing/synchronization logic was not modified. If it ever fails in CI, re-run before assuming a real regression, and check whether the failure is the `<1.5s` latency assertion specifically (timing-related) versus a status-code/call-count assertion (a real bug).
- **`test_website_url_security.py` makes two real outbound HTTPS requests** to `https://example.com/`, by the file's own design (see its docstring). This depends on GitHub-hosted runners' default outbound internet access, which is standard but is an external dependency this job did not have when it ran zero tests before this task.
  **Resolved (GitHub Actions run #5):** these two cases failed on the first real CI run — `example.com` resolves to both an IPv4 and an IPv6 address, `app/website_scrapper.py`'s address selection picked the IPv6 one via a hash-randomized Python `set`, and GitHub-hosted runners have no outbound IPv6 route (`OSError: [Errno 101] Network is unreachable`). This was **not** a transient/availability issue — it was deterministic given that DNS answer. Fixed in production code (`_resolve_validated_ips()`, deterministic IPv4-first ordering + bounded fallback to the next validated candidate on a connection-level failure only), not in CI — see the function's own docstring and `app/tests/test_website_url_security.py`'s new fallback-specific tests for the full record. The two real-fetch cases now reliably succeed via IPv4 on any runner with IPv4-only egress.

## Investigating a CI failure

- **`backend-v2` fails at "Create and attest the disposable V2 test database"** — the Postgres service container didn't come up healthy in time, or (extremely unlikely, since the database name is freshly created every run) a name collision. Re-run the job; if it persists, check the service container's health-check logs in the run's own log output.
- **`backend-v2` fails inside `pytest`** — read the failing test's name and file directly from the log; this is the same suite you can run locally (see above) against your own disposable database to reproduce.
- **`backend-v2` fails with `UnsafeTestDatabaseError` / "REFUSING to run V2 database tests"** — `app/v2/tests/db/guard.py` refused the database for a specific, printed reason (wrong name shape, wrong host, missing attestation, or a collision with a "production" URL env var). This is the guard working as designed, not a flake; the fix is in the workflow's database-setup step, never in loosening `guard.py` itself.
- **`backend-legacy-core-journey` fails at any of the seven named steps** — the step name says which file failed; reproduce with the exact `python -m app.tests.<name>` command from "Reproducing the checks locally" above, against your own disposable database.
- **`backend-legacy-core-journey` fails only in "Unified analyze -- concurrency"**, and specifically on the health-latency assertion (not a status-code/call-count one) — likely runner contention, not a regression; see "Unresolved / worth knowing" above.
- **`backend-legacy-core-journey` fails only in "Website URL ingestion -- SSRF hardening"**, on one of the two real-fetch tests (`test_valid_public_https_url_is_fetched`/`test_valid_public_http_url_is_fetched`) — the IPv4-first fix above means this should no longer happen from IPv6 unreachability specifically; if it recurs, it's more likely a genuine transient outbound-network or `example.com` availability issue than a code regression (every other case in that file, including the new fallback-logic tests, is fully offline and deterministic).
- **`backend-legacy-core-journey` fails only in "AI request reliability -- retry/backoff policy"** — this step is fully offline and deterministic (no real OpenAI request, no real sleep), so a failure here means a real behavior change, not flakiness: reproduce with `python -m app.tests.test_ai_request_reliability` locally (no database needed for this one file — it never imports `app.api`/`app.database.db`) and read which of the 7 scenarios failed (first-attempt success, transient-then-success, retry exhaustion, permanent-not-retried, exact backoff values, bounded-attempt-count, or the classification table). See `docs/portfolio/AI_REQUEST_RELIABILITY.md`.
- **`frontend` fails at lint/typecheck/test** — reproduce with the exact same command locally (see above); no CI-specific environment is involved in these three steps.
- **`frontend` fails at `npm run build`** — if the failure mentions Clerk/publishable key, confirm the workflow's placeholder env vars are still set correctly (see table above) — this is a build-time compatibility check, never a real-account issue. Any other build failure reproduces identically with `npm ci && npm run build` locally using the same placeholder values.
