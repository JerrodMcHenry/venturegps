# VentureGPS

VentureGPS is an AI-assisted startup due-diligence application. Given a company name and website, it
researches public evidence about that company and produces a structured, evidence-backed assessment across
six intelligence pillars (market, product, team, traction, execution, financial signals) — showing exactly
what evidence it found, where it came from, and which categories it could not assess from public
information alone. It does not claim to determine whether a company will succeed; it reports what public
evidence supports and is explicit about what it doesn't know.

**Live application:** https://app.venturegps.ai/

> **Status:** Evidence Engine v1 — the system described below — is **deployed and validated in real
> production** (2026-10-01). It runs behind a server-controlled feature flag alongside an earlier, legacy
> scoring engine kept live only for backward compatibility; this document describes the current,
> evidence-first architecture, not the legacy one. See "Current status" below for the detail.

## Why this project is technically interesting

This is a full-stack, production-deployed application built around one central engineering problem: **how
do you let an LLM help research a company without letting it quietly become the authority on whether that
company is good?** The answer implemented here is a hard boundary between what AI is allowed to do
(propose, research, structure) and what only deterministic code is allowed to do (validate, score, decide
what gets published) — enforced in code, not prompt instructions, and demonstrated end to end: structured-
output extraction with grounding validation, semantic-fit checking (catching schema-valid-but-wrong
categorical values), evidence provenance tracked to the exact source excerpt, fail-closed scoring and
publication gates, SSRF-hardened external content retrieval, ownership-scoped authenticated persistence,
an independently-owned database migration boundary, and a real, controlled production deployment with its
own rollback plan.

## Architecture

```
User
  → Next.js frontend (Vercel)
  → Clerk authentication
  → FastAPI backend (Render)
  → Analysis Service (engine selection, input validation, error mapping)
  → Evidence Engine Adapter
       → Search / Retrieval / Extraction   (probabilistic — real AI calls)
       → Canonicalization / Semantic Validation   (deterministic — no AI)
       → Deterministic Methodology (scoring, Coverage/Confidence, publish/withhold)
  → PostgreSQL (ownership-scoped persistence)
  → Evidence-first Report
```

Full diagrams (component architecture, request sequence, trust boundaries, fail-closed behavior):
`docs/portfolio/EVIDENCE_ENGINE_V1_ARCHITECTURE.md`.

## The AI boundary

**Probabilistic components propose, research, and structure evidence. Deterministic software validates
that evidence and owns every scoring and publication decision.** This is the single most important
engineering idea in this project, and it holds at every layer:

- An LLM extraction call can *propose* a claim (a typed fact plus the exact excerpt it came from) — it
  cannot make that claim true. Deterministic code checks the excerpt is actually, verbatim, present in the
  real retrieved page before the claim is allowed to exist at all.
- An LLM's categorical tag on a claim can be *schema-valid* and still *semantically wrong* (e.g. a funding
  amount mislabeled as a hiring metric) — a dedicated semantic-fit check catches this class of error before
  it reaches scoring, not after.
- **No model call ever computes a final score.** Pillar scores, company-level Evidence Coverage,
  Confidence, and the publish/withhold decision are all pure, reproducible Python arithmetic over
  already-validated claims. Two runs over identical validated evidence always produce the identical number.
- When evidence is too thin to support a pillar, the pillar is explicitly **withheld** — shown as
  "Assessment withheld," never silently scored anyway and never presented as equivalent to a demonstrated
  weakness. There is deliberately **no overall company score** — Coverage and Confidence are reported as
  their own, differently-shaped concepts, not folded into one number that implies more certainty than the
  evidence supports.

## Reliability and security

- **Authentication/authorization:** Clerk-issued JWTs verified server-side against Clerk's own JWKS
  (RS256, issuer + authorized-party checks); every analysis-retrieval route is ownership-scoped — a
  non-owner and a nonexistent resource id return the identical 404, never a distinguishing status code.
- **SSRF defense:** website retrieval validates scheme, rejects private/loopback/link-local/cloud-metadata
  addresses, pins DNS resolution against rebinding, bounds redirects, and caps response size — independently
  tested (`app/tests/test_website_url_security.py`) and reused unchanged by the evidence pipeline.
- **Structured-output + semantic validation:** every AI-proposed claim is schema-validated, grounding-
  checked against its source, and semantic-fit-checked against its claimed category before it can influence
  a score.
- **Fail-closed by default:** an unset or misconfigured feature flag, missing provider credentials, a
  provider exception, or a persistence failure all fail to a safe, generic, non-leaking state — never a raw
  exception, traceback, or credential reaching the client.
- **Feature flags, server-authoritative:** the production rollout of Evidence Engine v1 is gated by a
  server-side environment flag that is re-validated on every request; the client UI showing a feature is
  never itself proof the server will allow it.
- **Migration ownership, kept separate on purpose:** the legacy engine's tables, VentureGPS V2's schema, and
  Evidence Engine v1's own table are each migration-managed independently (two separate Alembic
  environments plus the legacy ad-hoc pattern), so none of the three can accidentally depend on or corrupt
  another's schema history.

## Testing

Verified directly, this session (not invented):

| Suite | Result |
|---|---|
| `app/evidence_engine/tests/` (the Evidence Engine's own offline test suite) | 604 tests across 28 files, all passing |
| `app/tests/test_evidence_v1_integration.py` (product-integration auth/ownership/engine-selection contract) | 14/14 passing |
| `app/evidence_v1/tests/test_migrations.py` (migration safety — legacy/V2 isolation, constraints, rollback) | 6/6 passing |
| `app/tests/` (legacy backend core journey, security, auth, concurrency, etc. — 66 files, run in isolation) | 65/66 passing; the one exception fails only on two helper routines that require a local-only development database not present in every environment — its actual security-contract tests pass |
| `python -m pytest app/v2` (VentureGPS V2's architecture-boundary and domain tests) | 2,226 passed, 0 failed (1,246 database-backed tests correctly skipped without a disposable test database — by design, never silently run against a real one) |
| Frontend (`npm test`, 35 suites) | 434 tests, all passing |
| `npx tsc --noEmit` / `npm run lint` / `npm run build` | all clean |

CI runs a subset of this automatically on every push to `main` — see `docs/portfolio/CI.md`.

## Current status

**Evidence Engine v1 is deployed and validated in real production** — real authentication, real Tavily/
OpenAI calls, real PostgreSQL persistence, a real analysis (Notion) run end to end through the live
application and independently verified (persistence, report rendering, reload-without-re-acquisition,
unauthenticated-access rejection). Full validation record: `docs/validation/EVIDENCE_V1_PRODUCTION_SMOKE_001.md`.

This is an actively maintainable project, not a claim that the software is permanently "finished" — but
there is no open roadmap of required work blocking its current state. An earlier, legacy scoring engine
(six pillars, structured outputs, its own evidence-awareness work) remains live, unflagged, and unmodified
for backward compatibility; it is documented in `docs/portfolio/ENGINE_TRANSPARENCY.md` and is **not** the
architecture described above. VentureGPS V2 (`app/v2/`) is a separate, in-progress rebuild of the platform's
company/market/financing data model with its own strict AI-candidate/deterministic-authority boundary
(`docs/v2/ADR-0001-truth-model.md`) — real, substantially tested (2,226 passing tests), but not the subject
of this README; see `docs/architecture/NEW_ENGINE_ARCHITECTURE.md` and `docs/v2/` for its own documentation.

## Documentation map

| Document | What it covers |
|---|---|
| `docs/portfolio/EVIDENCE_ENGINE_V1_ARCHITECTURE.md` | The current production architecture — diagrams, request flow, trust boundaries, fail-closed behavior |
| `docs/portfolio/ENGINEERING_CASE_STUDY.md` | The engineering narrative: the problem, the failure that drove the architecture change, the solution, tradeoffs |
| `docs/portfolio/INTERVIEW_GUIDE.md` | Technical interview talking points grounded in this repository |
| `docs/portfolio/DEMO_SCRIPT.md` | A 3–5 minute walkthrough of the live application |
| `docs/architecture/EVIDENCE_ACQUISITION_PIPELINE.md` | The evidence pipeline's own internal stage design |
| `docs/architecture/EVIDENCE_ENGINE_PRODUCT_INTEGRATION.md` | How the engine was wired into the real product (feature flag, persistence, migration ownership) |
| `docs/validation/EVIDENCE_V1_PRODUCTION_SMOKE_001.md` | The production deployment's own validation record |
| `DEPLOYMENT.md` | Full deployment runbook — hosting, environment variables, migrations (all three boundaries), rollback |
| `docs/ENGINEERING_JOURNAL.md` | Dated, chronological index of significant engineering decisions |

Historical/methodology documentation (the legacy engine's full scoring methodology, VentureGPS V2's own
extensive build history, and dozens of dated live-evaluation/calibration reports from building the Evidence
Engine) lives under `docs/methodology/`, `docs/product/`, and `docs/v2/` — kept rather than deleted, since
it records real engineering decisions and the reasoning behind them, but it is not required reading to
understand the current production system.

## Tech stack

**Backend:** Python, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL, OpenAI, Tavily
**Frontend:** TypeScript, Next.js (App Router), React, Clerk
**Infrastructure:** Vercel (frontend), Render (backend + managed PostgreSQL), GitHub Actions (CI)

## Developer setup

### Backend

```bash
pip install -r requirements.txt
```

Required environment variables (see `.env.example` for the full, placeholder-only template — never commit
real values):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (legacy tables, VentureGPS V2's `v2` schema by default, and Evidence Engine v1's own table all share this one database) |
| `OPENAI_API_KEY` / `TAVILY_API_KEY` | Required for any real analysis, either engine |
| `CLERK_ISSUER` | Required for any authenticated route — no safe default, fails closed if unset |
| `EVIDENCE_V1_ENABLED` | `true`/`false` — the production feature flag for Evidence Engine v1; defaults to off |

Run the API (this also applies the legacy engine's own additive, idempotent startup migrations):

```bash
uvicorn app.api:app --reload --port 8000
```

**Evidence Engine v1's own table** is migration-managed separately and is **not** created at startup —
run once, by hand:

```bash
alembic -c alembic_evidence_v1.ini upgrade head
```

**VentureGPS V2's schema** is also migrated separately and manually — see `DEPLOYMENT.md` for the exact
command. (Three migration boundaries exist on purpose — each is independently owned so none can
accidentally depend on or corrupt another's schema history; `DEPLOYMENT.md` explains why.)

### Frontend

```bash
cd dashboard
npm install
npm run dev   # http://localhost:3000, expects the API at http://127.0.0.1:8000
```

### Tests

```bash
# Evidence Engine (offline, no API keys needed)
python -m app.evidence_engine.tests.<test_file_name>

# Evidence-v1 product integration / migration safety
python -m app.tests.test_evidence_v1_integration
python -m app.evidence_v1.tests.test_migrations

# Legacy backend core journey (script-style, run individually)
python -m app.tests.<test_file_name>

# VentureGPS V2 (pytest-based)
python -m pytest app/v2 -q

# Frontend
cd dashboard && npm test && npx tsc --noEmit && npm run lint
```

Full test inventory and CI wiring: `docs/portfolio/CI.md`.
