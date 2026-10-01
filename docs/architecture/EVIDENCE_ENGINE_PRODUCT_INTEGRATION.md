# Evidence Engine v1 Product Integration (Task 31)

Integrates the isolated, validated Evidence Engine (`app/evidence_engine/`, candidate identifier
`evidence-engine-v1-candidate.1`, Task 30's own "State A" gate) into the real VentureGPS product,
behind a controlled, server-side feature flag, alongside the existing, unmodified legacy analysis path.

## 1. Old flow (unchanged, still the default)

```
authenticated user
  -> POST /analyze (website/PDF/text, multi-source)
  -> run_due_diligence() (app/workflows/due_diligence_workflow.py)
  -> save_analysis() -> analyses table (legacy schema)
  -> StartupAnalysisResponse (context + startup_scorecard + methodology)
  -> frontend redirects to /startup/{company_name}
  -> GET /startup/{company_name} (ownership/visibility-checked) renders the legacy report
```

Zero lines of this path were removed or rewritten. Every existing legacy test file
(`app/tests/test_analyze_unified.py`, `test_analysis_usage_protection.py`, `test_analysis_visibility.py`,
`test_my_analyses.py`, `test_security_hardening.py`, `test_public_evidence_consistency.py`,
`test_website_url_security.py`, `test_backend_authentication.py`) was re-run after this task's changes
and passes unchanged.

## 2. New flow (Evidence v1, server-flag-gated)

```
authenticated user
  -> POST /analyze (website + company_name, engine=evidence_v1)
  -> resolve_engine() -- THE one server-side boundary (app/evidence_v1/config.py)
       -- client REQUESTS evidence_v1; only runs if EVIDENCE_V1_ENABLED=true server-side
  -> submit_evidence_v1_analysis() (app/evidence_v1/service.py) -- Analysis Service
  -> run_evidence_v1_analysis() (app/evidence_v1/adapter.py) -- Engine Adapter
       -- CompanyAnalysisInput -> run_acquisition_pipeline() (the real, tested, unmodified
          app.evidence_engine pipeline -- production providers, canonicalization, semantic-fit,
          routing, provenance, cross-pillar audit, all untouched)
  -> save_evidence_v1_analysis() -> evidence_v1_analyses table (new, independent)
  -> EvidenceV1AnalysisResponse (analysis_id, engine, methodology_version, Coverage/Confidence/publishable)
  -> frontend redirects to /evidence/{analysis_id}
  -> GET /evidence-v1/analyses/{analysis_id} (ownership-checked by id, never company name)
       renders the evidence-first report
```

```
Route (POST /analyze, one boundary) -> Analysis Service -> Engine Adapter -> Persistence
```

- **Route** (`app/api.py::analyze_unified`): resolves the engine, then either runs the (unchanged)
  legacy body below, or delegates entirely to the service and returns. Thin -- no methodology, no
  provider construction, no persistence logic lives in the route itself.
- **Analysis Service** (`app/evidence_v1/service.py`): validates Evidence-v1's narrower input scope
  (website + company name only, item 7), invokes the adapter, persists the result, maps every failure to
  a typed `EvidenceV1FailureReason` the route turns into the right HTTP status/message.
- **Engine Adapter** (`app/evidence_v1/adapter.py`): the ONLY place application code constructs
  `CompanyAnalysisInput` and the real production providers (`TavilySearchProvider`,
  `HttpSourceRetriever`, `OpenAIEvidenceExtractor`) and calls `run_acquisition_pipeline()`. Serializes the
  real, unmodified `AcquisitionResult` to plain dicts -- no methodology logic is reimplemented, copied, or
  bypassed anywhere in this module.
- **Persistence** (`app/evidence_v1/persistence/repository.py`): plain parameterized SQL against
  `evidence_v1_analyses`, reusing `app.database.db.engine` (same database, same connection pool) for
  runtime reads/writes -- but the TABLE itself is migration-managed by a fully independent Alembic
  environment (§4).

## 3. Engine identity and the feature-flag boundary

`app/evidence_v1/config.py::resolve_engine(requested: str | None) -> Engine` is the one function that
decides. Safe default: `Engine.LEGACY`. `Engine.EVIDENCE_V1` requires BOTH an explicit client request
(`engine=evidence_v1` form field) AND the server-side `EVIDENCE_V1_ENABLED=true` environment flag -- a
client can never authorize evidence_v1 merely by asking for it. An unrecognized engine value, a missing
flag, or no `engine` field at all all resolve to `Engine.LEGACY` silently and safely -- never an error,
never a surprising behavior change for an ordinary request. Every persisted `evidence_v1_analyses` row
carries its own `engine` (`'evidence_v1'`, enforced by a `CHECK` constraint) and `methodology_version`
(`'evidence-engine-v1-candidate.1'`) columns -- which engine produced a given analysis is always
determinable from the row alone, never inferred.

## 4. Persistence: two Alembic environments, deliberately

**The constraint.** CLAUDE.md's Legacy DDL freeze forbids new `add_*_column()`/`create_*_table()`
migrations in `app/database/db.py`/the import-time migration block in `app/api.py`. The existing Alembic
environment (`alembic.ini`, `app/v2/migrations/`) is explicitly V2-only and structurally cannot host an
unrelated table:

- `app/v2/db/metadata.py`'s `MetaData(schema="v2", ...)` namespaces every table registered on it into
  schema `v2`, unconditionally.
- `app/v2/db/scope.py`'s `include_name`/`include_object` are a fail-closed allowlist for schema `v2`
  only -- the default/public schema is explicitly excluded from autogenerate.
- `app/v2/migrations/env.py`'s downgrade-to-base path **drops the entire `v2` schema**
  (`_teardown_if_reverted_to_base`) -- an unrelated table's migration history must never share that
  lifecycle.

Evidence Engine v1 is architecturally separate from `app/v2/` (a different rebuild effort entirely), so
placing its table inside the `v2` schema/Alembic environment would create a misleading dependency for
migration convenience alone.

**The decision.** A second, minimal, fully independent Alembic environment
(`alembic_evidence_v1.ini`, `app/evidence_v1/migrations/`):

- Owns exactly one table, `evidence_v1_analyses`, in the **default/public** schema -- no new Postgres
  schema (there is no technical reason one is needed here, unlike V2's own broader namespacing need).
- Its own version table, `evidence_v1_alembic_version` (also default schema) -- distinct name from
  `v2.alembic_version`, so the two histories can never collide even though both may target the same
  physical database (`DATABASE_URL`).
- No autogenerate (`target_metadata=None`) -- one table does not need reflection/diffing machinery; each
  revision is a small, hand-written, explicit migration.
- Never run at import time or FastAPI startup -- manual only (`alembic -c alembic_evidence_v1.ini
  upgrade head`), the same convention V2 established.
- Never touches `v2.*` or `analyses`/any legacy table -- no foreign key crosses either boundary.

```
legacy persistence (analyses, ...)   -> frozen, ad-hoc add_*_column() migrations (unchanged)
V2 persistence (v2.*)                -> unchanged, Alembic, app/v2/migrations/, schema v2
Evidence Engine v1 persistence       -> new, independent Alembic environment,
                                         app/evidence_v1/migrations/, default/public schema,
                                         table evidence_v1_analyses
```

### Schema

```sql
CREATE TABLE evidence_v1_analyses (
    id                    TEXT        NOT NULL,   -- application-generated UUID4 hex, never sequential
    owner_user_id         TEXT        NOT NULL,   -- Clerk user_id, ownership
    company_name          TEXT        NOT NULL,
    canonical_website     TEXT        NOT NULL,
    engine                TEXT        NOT NULL,   -- CHECK engine = 'evidence_v1'
    methodology_version   TEXT        NOT NULL,   -- 'evidence-engine-v1-candidate.1'
    stage                 TEXT,
    run_status            TEXT        NOT NULL,   -- CHECK IN ('completed', 'failed')
    company_coverage_pct  DOUBLE PRECISION,
    company_confidence    TEXT,                    -- CHECK IN ('Low','Medium','High') or NULL
    company_publishable   BOOLEAN,
    result                JSONB       NOT NULL,    -- the full, immutable FullCompanyAnalysis + accepted claims
    telemetry             JSONB,                    -- kept separate for cheaper operational queries
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_evidence_v1_analyses PRIMARY KEY (id)
);
CREATE INDEX ix_evidence_v1_analyses_owner_created ON evidence_v1_analyses (owner_user_id, created_at DESC);
```

A UUID primary key (application-generated, never a Postgres extension dependency) rather than a
sequential integer -- a sequential id would make cross-user analysis enumeration trivial. Relational
columns exist only for what ownership/listing/filtering/report-selection genuinely need; the full, rich
analysis artifact is not flattened into further columns. No `UPDATE` path exists anywhere -- a row is
written once, by the adapter, after a completed run, and never mutated.

## 5. Privacy boundary (release blocker, item 9 -- verified, not just assumed)

`GET /startup/{company_name}` (legacy) was already re-secured in a prior phase (Portfolio Release Task
3B): `RequireAuth`-gated, and `get_startup_by_name()` applies a submitter/approved-member/admin
visibility rule before returning anything, never leaking existence via a distinguishing status code.
Confirmed still intact by re-running `app/tests/test_analysis_visibility.py` (14/14),
`test_my_analyses.py` (7/7), `test_security_hardening.py` (24/24) after this task's changes -- zero
regressions.

Evidence v1's own retrieval path never uses company name as an identity key anywhere:
`GET /evidence-v1/analyses/{analysis_id}` (`app/evidence_v1/router.py`) looks up strictly by the UUID
`analysis_id`, then compares `row.owner_user_id` against the authenticated caller
(`get_owned_evidence_v1_analysis()`, `app/evidence_v1/service.py`). A non-owner and a nonexistent id
receive the byte-identical 404 response -- verified directly
(`app/tests/test_evidence_v1_integration.py::test_cross_user_retrieval_is_a_non_leaking_404_not_403`).
The two tables (`analyses`, `evidence_v1_analyses`) are never joined or cross-referenced, so a company
name can never bridge a private Evidence-v1 analysis into the legacy public-lookup surface.

## 6. Authentication/authorization

Reuses `app/auth.py` unchanged -- `RequireAuth` on every Evidence-v1 route, `current_user.user_id` (the
verified Clerk JWT subject) is the only identity ever written as `owner_user_id` or compared against it.
No new authentication mechanism, no new token format, no new admin/membership concept.

## 7. Frontend

- `types/evidenceV1.ts`, `lib/api/evidenceV1.ts` -- new, separate from the legacy shapes (no overall
  0-100 score, Coverage/Confidence are a different concept, never rendered as if equivalent).
- `lib/api/analyze.ts::analyzeMultiSource()` -- additive `engine`/`companyName` parameters;
  `isEvidenceV1Response()` discriminates the response shape.
- `app/analyze/AnalyzeStartupForm.tsx` -- evidence_v1 is reachable only via `?engine=evidence_v1` (never
  a default-on toggle in the ordinary UI), redirects to `/evidence/{id}` on an evidence_v1 response.
  Loading state uses its own honest, non-fabricated stage language (`EVIDENCE_V1_STAGES`) -- the backend
  does not report live per-stage progress, so neither list ever pretends otherwise.
- `app/evidence/[analysisId]/page.tsx` + `components/evidence/EvidenceV1Report.tsx` -- the report itself:
  header, company-level Coverage/Confidence/publication state (never an overall score), six pillars with
  progressive disclosure into dimensions and evidence (native `<details>`/`<summary>`, no client-side
  JavaScript required), Unscored explicitly distinguished from a negative result, external source links
  marked `rel="noopener noreferrer nofollow"` and never implied to mean independent verification,
  untrusted retrieved text rendered as plain React text (never `dangerouslySetInnerHTML`).
- `app/my-analyses/MyAnalysesView.tsx` -- fetches both `GET /me/analyses` (legacy) and
  `GET /me/analyses/evidence-v1` independently (one failing never blanks the other), merges by date,
  renders each engine's row with its own distinct badge/link -- Evidence v1's Coverage is never styled
  through the legacy score-tier badge classes.

## 8. Failure behavior

Every Evidence-v1 failure mode maps to a typed `EvidenceV1FailureReason`
(`UNSUPPORTED_INPUT` -> 400, `NOT_CONFIGURED`/`ACQUISITION_FAILED`/`PERSISTENCE_FAILED` -> 502), a clear
user-facing message, and a server-side `traceback.print_exc()` -- never a raw provider exception, secret
value, or traceback reaching the client (verified:
`test_evidence_v1_missing_credentials_maps_to_a_clear_non_leaking_error`,
`test_evidence_v1_pipeline_exception_maps_to_a_clear_error_never_a_raw_traceback`). Evidence v1 reuses
the SAME cost/abuse protection the legacy path already has (`compute_analysis_fingerprint`,
`has_recent_duplicate_completed_run`, `count_recent_analysis_runs`, `begin_analysis_run`,
`finish_analysis_run`) -- these are already engine-agnostic (keyed on `user_id` + a content fingerprint),
so no second protection mechanism was built.

## 9. Rollout strategy

1. `EVIDENCE_V1_ENABLED` unset/false in every environment (default) -- zero behavior change, legacy path
   only, verified by the full existing legacy test suite.
2. Run `alembic -c alembic_evidence_v1.ini upgrade head` once against the target database (additive,
   non-destructive, independently reversible).
3. Enable `EVIDENCE_V1_ENABLED=true` in a controlled environment only, for internal/invited testing via
   `?engine=evidence_v1` (not a public-facing toggle yet).
4. No legacy behavior is ever removed as part of this rollout -- see the ADR (`ADR-evidence-engine-v1-
   candidate.md`) for the explicit decision to keep both paths live behind the flag, not to delete or
   disable legacy.
