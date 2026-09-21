# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

AI Due Diligence Copilot analyzes a startup (from pasted text, a PDF, or a website URL) and produces a
structured, evidence-based investment analysis using the "Startup Intelligence Engine" (SIE) methodology.
It has two halves that run as separate processes:

- **`app/`** — Python/FastAPI backend. Runs the AI analysis pipeline (OpenAI + Tavily) and persists results
  to Postgres.
- **`dashboard/`** — Next.js 16 (App Router) frontend that reads from the backend API and renders rankings,
  search, and per-startup score breakdowns.

The full SIE methodology (pillars, scoring weights, evidence rules) is documented in
`app/docs/SIE_Methodology_v1.md` and `dashboard/docs/sie-intelligence-framework.md` — read these before
changing any scoring logic.

## Commands

Run backend commands from this directory (`ai-due-diligence-copilot/`) so the `app` package resolves.

```bash
# Backend setup
pip install -r requirements.txt
# requires OPENAI_API_KEY, TAVILY_API_KEY, DATABASE_URL (postgresql://...) in .env

# Run the API server
uvicorn app.api:app --reload --port 8000

# Run the CLI pipeline (prompts for a file path, e.g. app/data/sample_company.txt)
python -m app.main

# Run the scoring calibration suite against benchmark companies
python -m app.calibration.run_calibration
```

```bash
# Dashboard (from dashboard/)
npm run dev      # http://localhost:3000, expects the API at http://127.0.0.1:8000
npm run build
npm run lint
npm start
```

There is no automated unit/integration test suite in this repo. The closest equivalent is the calibration
suite (`app/calibration/`), which checks that pillar scores for known benchmark companies fall within
expected ranges (`app/calibration/expected_scores.py`) — treat it as the regression check when touching
scoring, prompts, or evidence rules.

## Architecture

### Backend request flow

`app/api.py` is the FastAPI entrypoint. On import it runs a series of additive, idempotent migration
functions (`create_tables`, `add_scoring_columns`, etc. from `app/database/db.py`) against `DATABASE_URL` —
there is no Alembic/migration framework; new columns are added by writing a new `add_*_columns()` function
and calling it at startup, wrapped in try/except so re-running is safe.

For a given company input, the pipeline (`app/workflows/due_diligence_workflow.py::run_due_diligence`) is:

1. **Enrichment** — `app/ai/research_enrichment.py` (Tavily) adds public research context to the raw
   company text. PDFs and URLs are converted to text first via `app/pdf_extractor.py` /
   `app/website_scrapper.py`.
2. **Pillar analysis** — six independent analyses run over the enriched text: market, team (founders),
   product, execution, traction, financial health (`app/ai/market_analysis.py`,
   `founder_analysis.py`, `product_analysis.py`, `execution_analysis.py`, `traction_analysis.py`,
   `financial_analysis.py`), plus free-form summary/risk/memo/competitor/structured-analysis calls.
3. **Assembly** — `app/workflows/sie_assembler.py::assemble_sie_analysis` combines the six pillar results
   plus a readiness score into one `SIEMethodologyAnalysis` (`app/models/startup.py`), computes the overall
   `startup_intelligence_score` (`app/ai/investment_score.py`) and the `startup_scorecard`
   (`app/ai/scorecard.py`).
4. Note `run_due_diligence` calls `build_sie_methodology_analysis` **twice**: once with `readiness=None` to
   get pillar scores, then again after computing the readiness score from those scores
   (`app/ai/readiness_score.py`), so the final object includes readiness. Keep this two-pass shape in mind
   when changing what feeds the readiness calculation.
5. `app/api.py` persists the result via `save_analysis`/`save_score_history` and returns a
   `StartupAnalysisResponse`.

### The pillar-analysis engine (`app/ai/analyze_pillar.py`)

All six pillar modules are thin wrappers that call the single generic `analyze_pillar()` — they only supply
a pillar name, a Pydantic `result_model`, and pillar-specific extra fields/rules. Don't reimplement this
per-pillar; add new pillars by following the same wrapper pattern (see `market_analysis.py` as the
reference example).

`analyze_pillar()`'s contract, driven by `app/ai/scoring_methodology.py` (per-pillar dimensions, weights,
score-band guidance) and `app/ai/scoring.py` (weighted-average finalization):

- Every scoring dimension is tagged **Public**, **Inferred**, or **Private**, which controls what evidence
  is required and whether `Unavailable` (null score) is a legal outcome for that dimension.
- The model is called once (`gpt-4.1-mini`, temperature 0), the JSON response is validated against the
  evidence/score rules (`validate_evidence_requirements`), and if validation fails a single correction pass
  is sent back to the model with the specific errors before giving up and logging a warning.
- `finalize_pillar_score` (in `scoring.py`) computes the weighted pillar score from validated subscores —
  this is the only place pillar scores are calculated; don't hand-roll weighted averages elsewhere.

When editing prompts or evidence rules, changes belong in `scoring_methodology.py` /
`analyze_pillar.py`, not in the individual pillar files, since all six pillars share this machinery.

### Data models

`app/models/` holds the Pydantic contracts shared across the backend: `startup.py` (`SIEMethodologyAnalysis`,
`PillarAnalysis`, API request/response models), `scoring.py` (`PillarScoreBreakdown`,
`StartupIntelligenceScore`), `evidence.py`, `analysis_context.py`. The dashboard's `types/` directory mirrors
these shapes by hand — when a Pydantic model changes, update the matching TypeScript type.

### Dashboard

Next.js App Router app. Pages live in `dashboard/app/` (`rankings`, `search`, `startup/[id]`); UI is split
into `components/dashboard`, `components/layout`, `components/rankings`, `components/startup`, and
`components/sps` (the circular score-ring visualization). All backend calls go through
`dashboard/lib/api/*.ts`, thin typed wrappers around `apiFetch` (`lib/api/client.ts`), which reads
`NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8000`). The backend's CORS policy
(`app/api.py`) only allows `localhost:3000`/`127.0.0.1:3000`, so keep the dev port in sync if you change it.
Path alias `@/*` maps to the `dashboard/` root (`tsconfig.json`).

`dashboard/AGENTS.md` (pulled in via `dashboard/CLAUDE.md`) flags that this Next.js version has
breaking API/convention changes from training-data knowledge — check `node_modules/next/dist/docs/` before
writing Next.js code in `dashboard/`.

### Calibration suite

`app/calibration/` is a standalone regression harness, not unit tests — see `app/calibration/README.md`
for its full rules. Key points: benchmark inputs live in `app/calibration/data/<company>_<stage>.txt`, the
filename stem must match a key in `EXPECTED_SCORES` (`expected_scores.py`), expected values are *ranges*
not exact scores, and the harness must never be used to justify changing the production scoring formula
based on a single benchmark result — look for patterns across multiple benchmarks first.

## VentureGPS V2 (`app/v2/`) — read before touching it

VentureGPS is being rebuilt as a public startup-market intelligence platform. The V2 truth model and AI
boundary are recorded in `docs/v2/ADR-0001-truth-model.md`; the rules below are enforced by tests, not just
convention.

- **Strangler migration.** V2 is built beside legacy in `app/v2/` (and, from Increment 2, its own Postgres schema
  `v2`). V2 code imports **no** legacy modules (`app.ai`, `app.database`, `app.api`, `app.models`, `app.auth`, ...).
  Do not rework legacy to serve V2, and do not migrate old analyses into V2 truth — legacy AI output is not evidence.
- **Legacy DDL freeze.** Do not add new `create_*`/`add_*` migration functions to `app/database/db.py` or the
  import-time migration block in `app/api.py`. New V2 schema comes through Alembic (`alembic.ini`,
  `app/v2/migrations/`), scoped to Postgres schema `v2` with its own `v2.alembic_version`; it never manages legacy
  `public` tables. V2 migrations are run manually (`alembic upgrade head`) — never at import, never at FastAPI
  startup. See `docs/v2/DATABASE_MIGRATIONS.md` and the manual-migration section of `DEPLOYMENT.md`.
- **AI candidate / canonical boundary.** AI may *propose* typed candidates. AI is never the authority that promotes a
  candidate to canonical truth; in Phase 1 an AI-derived candidate needs a human decision. Later, a deterministic,
  versioned rule may accept an AI-produced candidate after independent evidence validation — the rule, not the model,
  is then the authority. Never let AI confidence become canonical truth. Prompts are not a security or integrity
  control.
- **Deterministic core.** Everything in `app/v2` except `app/v2/ai` must work with no AI SDK, no AI credentials and no
  model network access, and may not import `app.v2.ai`, provider SDKs, or reference `OPENAI_API_KEY` /
  `ANTHROPIC_API_KEY` / `TAVILY_API_KEY`. `app/v2/ai` may not import V2 repositories/db/workers, SQL drivers, or legacy
  code. New `app/v2/*` packages are deterministic by default. Rules live in
  `app/v2/tests/architecture/boundary_rules.py`.
- **Resolution boundary.** AI may propose candidates; only a deterministic rule or a human may resolve one into a
  canonical `Company` (`app/v2/resolution`, revision 0007). Canonical tables are written only by the private
  `app.v2.resolution._writes` via `promotion.py`; `app.v2.ai` and the candidate layer cannot import the package, and
  `decided_by_kind` is `rule | human` in the domain and the database. Name-only matches never resolve; there is no merge.
- **Tests.** Pytest is scoped to V2 only: `python -m pytest` (from this directory). It refuses any path outside
  `app/v2` (root `conftest.py`), because legacy tests are scripts that hit the real `DATABASE_URL`; run those as
  `python -m app.tests.<name>`, unchanged.
  V2 DB tests (`-m db`) need a disposable database via `V2_TEST_DATABASE_URL` and **never** fall back to
  `DATABASE_URL`; the fail-closed safety rule is in `docs/v2/DATABASE_MIGRATIONS.md`. Do not point them at a real
  database.
- **No commit / push.** Claude Code must not commit or push in this repo. The user runs all git write operations;
  hand over status, diff, test results, a suggested commit message and the commands.
