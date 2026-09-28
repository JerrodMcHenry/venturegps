# VentureGPS Evidence Engine — Architecture

**Status: TASK 10 (Evidence Reliability & Validation) COMPLETE for Product & Technology, still
in isolation, no persistence/API/frontend yet.** Beyond Task 9 (real classification/extraction
interface, stage-aware evaluation): Task 10 closed two engineering gaps ahead of a small
live-evidence evaluation — evidence-independence is now provenance-verified rather than trusting
a self-declared group id (`app/evidence_engine/provenance.py`), and a classification/extraction
failure gets one retry with structured feedback before failing closed (Part 5 below). Open
questions 1-3 (naming, company identity, Confidence shape) remain decided/approved — see the box
in `docs/methodology/NEW_ENGINE_SPEC.md`. Open questions 4-5 remain open and are not needed yet.
Parts 3 (Persistence), 4 (API Contracts), and 6 (Frontend Integration) below remain design only.
See `app/evidence_engine/README.md` for the exact current-state boundary and
`docs/methodology/NEW_ENGINE_CALIBRATION_REPORT.md` Part 10 for what this pass found, including
an explicit readiness assessment for a small live-evidence evaluation.

Companion documents: `docs/methodology/NEW_ENGINE_SPEC.md` (the methodology this architecture
implements) and `docs/methodology/NEW_ENGINE_CALIBRATION.md` (the evaluation plan).

---

## Part 1 — Isolation Boundary (why, and where it sits relative to existing code)

### 1.1 Precedent this follows

This codebase already has one proven precedent for isolating a new system beside a legacy one:
`app/v2/` (documented in `docs/v2/ADR-0001-truth-model.md`, enforced by
`app/v2/tests/architecture/boundary_rules.py`) — a strangler-pattern package that imports no
legacy modules, owns its own Postgres schema (`v2`, migrated by its own Alembic instance
scoped away from legacy's ad-hoc `create_*`/`add_*` migration functions), and draws a hard line
between AI-proposed candidates and deterministically-or-human-resolved canonical truth.

**The new engine adopts the same isolation discipline, but is deliberately not built inside
`app/v2/`.** Two reasons: first, `app/v2`'s own architectural rule is that everything except
`app/v2/ai` must work with zero AI SDK/credentials/network access — this engine is
fundamentally an AI-assisted evidence-and-assessment system end to end, which does not fit that
boundary without distorting it. Second, `app/v2`'s domain is company *identity* resolution
(Company, FinancingEvent, Market classification) — a different kind of system, with its own
candidate/canonical authority rules, that this engine should not need to depend on or extend
just to exist. **Proposed package: `app/evidence_engine/`, a new top-level package, sibling to
`app/ai/`, `app/v2/`, and `app/database/`, not nested inside any of them.**

### 1.2 What the new engine may and may not import

| May import (reused as infrastructure, per the spec's Part 8.3) | May not import |
|---|---|
| `app/pdf_extractor.py`, `app/website_scrapper.py` (pure text-extraction utilities, no scoring logic) | `app.ai.*` (all legacy scoring/prompt modules — the entire point of this task) |
| `app/ai/concurrency.py::run_concurrently` (a general bounded-concurrency utility, no scoring logic) | `app.database.db` (legacy's ad-hoc migration/query functions) |
| `app/auth.py` (`RequireAuth`, `AuthenticatedUser` — the existing Clerk JWT verification gate, already used unmodified by every other authenticated route in `app/api.py`) | `app.v2.*` (a different system with its own identity-resolution authority rules this engine does not need) |
| The existing `DATABASE_URL`-configured Postgres instance (new schema, Part 3) | `app.models.startup`, `app.models.scoring` (legacy's Pydantic contracts — the new engine defines its own, Part 4) |

A dedicated architecture test (mirroring `app/v2/tests/architecture/boundary_rules.py`'s own
pattern — reusable *test infrastructure*, not scoring logic) should assert this import boundary
mechanically once implementation begins, not rely on convention alone.

### 1.3 Company identity — a deliberate, explicit non-decision

`app/v2` already has a governed, human-authority-gated canonical Company identity system
(`app/v2/resolution`). Whether the new engine should assess *against* V2's canonical companies
(reuse, avoids duplicate identity data, but couples this engine to V2's own candidate/canonical
authority rules) or maintain its own lightweight, fully-decoupled company reference (simpler,
faster to ship, but means "Acme Inc" can exist as two unrelated records across the two systems)
is presented here as an **open question (Part 8)**, not decided unilaterally. This document's
default design (Part 4) assumes the simpler, fully-decoupled option for a first version, with
the integration path to V2 identity explicitly left for a later, separately-scoped phase if
approved.

---

## Part 2 — Request Flow

```
Research → Evidence Ledger → Assessment → Deterministic Scoring → Report
```

### 2.1 Research

Reuses existing ingestion utilities unmodified: `app/pdf_extractor.py` for an uploaded pitch
deck, `app/website_scrapper.py` for a submitted URL, and a new Tavily-based research step
modeled on (not importing) `app/ai/research_enrichment.py`'s existing category-search pattern —
modeled on it because the *pattern* (a fixed set of named research categories, dispatched
concurrently via `run_concurrently`, assembled in a deterministic fixed order) is sound general
infrastructure; the actual category list and prompts are new, since the new engine's evidence
needs (named customers, disclosed figures, named executives) differ from the legacy pipeline's
narrative-research needs.

### 2.2 Evidence Ledger construction

One or more schema-constrained LLM calls (dispatched concurrently, one per research category or
per pillar — an implementation-time choice, not fixed here) turn raw research text plus any
submitted document/website text into typed `Claim` records (spec Part 2.1), each validated
against a Pydantic model before being written to the ledger. **No claim is written without a
`source.type`, `source.publisher`, and `retrieved_at`** (spec Part 2.2) — a call that cannot
produce a valid claim for a given piece of text simply produces no claim, never a
partially-filled one.

### 2.3 Assessment

For each dimension (spec Part 3.3): a **Computed** dimension's typed-fact extraction call reads
only the ledger claims already tagged with that dimension in `assessment_criteria`; a
**Classified** dimension's classification call does the same, with the company-name-redaction
step (spec Part 5.3) applied to the claim text before the call is made. Both call types are
schema-enforced to their respective output shapes (spec Part 5.1) and dispatched concurrently
across dimensions/pillars via `run_concurrently`, since dimensions have no cross-dependency on
each other's Assessment output (only Scoring, Part 2.4, depends on Assessment's already-complete
output).

**Implemented for Product & Technology (Task 9):** the interface itself
(`app/evidence_engine/classification.py`) and its default `WellBehaved*` mocks are real and
tested. **Task 10** added evidence-independence verification (a deterministic pass over cited
claims' content/provenance, `app/evidence_engine/provenance.py`, run as part of dimension
evaluation before a Classified response is accepted — not itself an AI call) and one retry with
validation feedback before failing closed (Part 5 below). Concurrent dispatch across
dimensions/pillars via `run_concurrently` is not yet wired in (only four dimensions exist so far,
run sequentially in the current code — revisit once more
pillars exist and concurrency is actually worth the complexity).

### 2.4 Deterministic Scoring

Pure Python, no I/O, over the completed Assessment output for all dimensions of one company's
analysis: dimension scoring → pillar aggregation/gates → coverage → confidence → overall-score
gates (spec Part 6, in that order, each a separately testable pure function).

### 2.5 Report

Assembles the persisted result (Part 3) into the API response contract (Part 4) and, on
request, into the frontend's rendering (Part 6).

---

## Part 3 — Persistence

### 3.1 A new, isolated Postgres schema

Proposed: a new schema, `evidence_engine`, migrated by its own Alembic instance
(`app/evidence_engine/migrations/`), following the exact precedent `app/v2/migrations/` already
establishes in this codebase — never an ad-hoc `create_*`/`add_*` function run at FastAPI
import time (the legacy pattern this codebase's own `CLAUDE.md` explicitly freezes and forbids
extending). Migrations run manually (`alembic upgrade head`), never automatically at API
startup, exactly matching `app/v2`'s own already-approved operating model.

### 3.2 Proposed tables (design only — no migration is created in this phase)

- **`evidence_engine.claims`** — one row per `Claim` (spec Part 2.1), including its full
  provenance. A real relational table, not an embedded JSON blob, specifically because the
  ledger is meant to be independently queryable (find every claim backing a given dimension
  across companies, for calibration and audit) in a way a JSON column inside a legacy-style
  `analyses` row does not support well.
- **`evidence_engine.assessments`** — one row per dimension-assessment-attempt (the AI's typed
  fact or classified label, with its supporting `claim_ids`), linked to the analysis run that
  produced it.
- **`evidence_engine.analyses`** — one row per completed analysis run: the company reference
  (3.3), the methodology identifier and every parameter-table version used (spec Part 7), and
  the final computed Strength/Coverage/Confidence result at every level (dimension, pillar,
  overall) — the *output* of Scoring, kept separately from the `claims`/`assessments` tables
  that record the *inputs*, so a future recalibration can recompute Scoring from the same stored
  Assessment output without re-running Research/Assessment (and therefore without a new paid AI
  call) — an explicit design goal, since recalibration (spec Part 7) should be cheap to test
  against already-gathered evidence.
- **`evidence_engine.parameter_versions`** — a small, versioned table recording exactly which
  weight/threshold/band-table values were live for a given `methodology identifier +
  calibration sub-version` combination (the "reusable `ParameterRegistry` pattern," spec Part
  8.3), so a stored analysis's scores can be recomputed byte-for-byte from its own recorded
  parameter version even after live values are recalibrated.

### 3.3 Company reference (per the open question in 1.3)

Proposed default: a lightweight `evidence_engine.companies` table (name, primary domain,
optional external ids) with no foreign-key dependency on V2's canonical `Company` table —
fully decoupled, per 1.3's stated default. If approved, a future integration phase could add an
optional `v2_company_id` foreign key without breaking this design, since nothing in Parts 2, 4,
or 6 depends on where the company reference resolves from.

### 3.4 Zero impact on legacy or V2 persistence

No legacy table (`analyses`, `score_history`, or any other `public`-schema table) is touched.
No V2 table or schema is touched. The new engine's tables are entirely additive, in their own
schema, with no foreign key into either existing system's tables (aside from the optional,
future, explicitly-flagged V2 Company link above) — satisfying "without modifying the legacy
scoring systems or corrupting historical analyses" by construction, not by convention.

---

## Part 4 — API Contracts

### 4.1 New, additive endpoints — never a change to an existing route's response shape

Proposed new router, mounted on the existing FastAPI app (`app/api.py`) alongside existing
routers, reusing the existing Clerk authentication dependency unmodified:

```python
from app.auth import AuthenticatedUser, RequireAuth
# new router, e.g. app/evidence_engine/api.py, included via app.include_router(...)

@router.post("/evidence-engine/analyze")
def analyze(payload: EvidenceEngineAnalyzeRequest, current_user: AuthenticatedUser = RequireAuth) -> EvidenceEngineAnalysisResponse: ...

@router.get("/evidence-engine/analyses/{analysis_id}")
def get_analysis(analysis_id: str, current_user: AuthenticatedUser = RequireAuth) -> EvidenceEngineAnalysisResponse: ...
```

No existing route (`/analyze`, `/startup/{id}`, `/rankings`, etc.) changes its request or
response shape. The new engine is reached only through its own, separately-versioned endpoints
— a company wanting both assessments today would call both `/analyze` (legacy) and
`/evidence-engine/analyze` (new) as two independent requests, not a combined one, in this first
version.

### 4.2 Response contract shape (Pydantic, new module, no legacy import)

```python
class EvidenceEngineDimensionResult(BaseModel):
    dimension: str
    pillar: str
    category: Literal["computed", "classified"]
    score: float | None          # None = Unscored, never 0
    supporting_claim_ids: list[str]
    evidence_support_quality: ...  # feeds Confidence, spec 6.4

class EvidenceEnginePillarResult(BaseModel):
    pillar: str
    strength: float | None       # None = withheld, never 0
    coverage_pct: float
    confidence: Literal["Low", "Medium", "High"]
    publishable: bool
    withhold_reason: str | None
    dimensions: list[EvidenceEngineDimensionResult]

class EvidenceEngineAssessment(BaseModel):
    methodology_version: str            # e.g. "evidence_engine.v1"
    parameter_version: str
    stage: Literal["Idea","Pre-Seed","Seed","Series A","Series B+","Growth","Undetermined"]
    overall_score: float | None
    overall_coverage_pct: float
    overall_confidence: Literal["Low", "Medium", "High"]
    publishable: bool
    withhold_reason: str | None
    pillars: list[EvidenceEnginePillarResult]
    computed_at: str
```

Every nullable field above is nullable **because the methodology requires it to be**, not as an
implementation convenience — matching the spec's own explicit rule that `Unscored`/withheld is a
distinct state from zero, never collapsed.

### 4.3 Evidence Ledger read endpoint

```python
@router.get("/evidence-engine/analyses/{analysis_id}/claims")
def get_claims(analysis_id: str, dimension: str | None = None, current_user: AuthenticatedUser = RequireAuth) -> list[Claim]: ...
```

Lets a reviewer (or the frontend's own "why this score" detail view, Part 6) fetch the exact
ledger entries backing any dimension — the mechanism that makes "every material scored claim is
traceable to admissible evidence" (spec Design Principle 2) a checkable product feature, not
just an internal guarantee.

---

## Part 5 — Failure Handling

**Implemented and tested for Product & Technology** (Task 9:
`app/evidence_engine/tests/test_adversarial_robustness.py`; Task 10:
`test_classification_recovery.py`): a classification/extraction call that raises is caught
immediately (no retry on a raised exception — see below) and resolved to `Unscored
(extraction_failed)`; a call that returns an invalid label or cites unsupported/inadmissible
evidence is retried exactly once with the violations fed back as structured
`validation_feedback` (`classify_with_recovery`/`extract_with_recovery`), and only fails closed
to `Unscored (extraction_failed)` if the second attempt is also invalid. Verified directly,
including the case of every one of a pillar's four model calls raising simultaneously, which
still returns a normal, non-exception `PillarResult` (withheld, never a crash). **Deliberate
scope boundary:** retry applies only to a validation failure, not to a raised exception — a
model/provider crash is assumed non-transient-within-this-request and fails closed immediately,
matching the legacy pattern's own distinction between a retriable transient failure and a
permanent one; revisit if a real model call's actual crash modes turn out to include
worth-retrying transient ones.

- **A failed research/Assessment call for one dimension never fails the whole analysis.**
  Mirrors the existing legacy pipeline's own already-sound "fail loud within a bounded group,
  never silently return a partial-but-unlabeled result" discipline (`app/ai/concurrency.py`),
  reused as a pattern: a dimension whose extraction call errors is marked `Unscored` with an
  internal `extraction_failed` reason distinct from a genuine `no_evidence_found` reason (surfaced
  to observability, Part 7, never to the end user as if it were the same thing as "the company
  has no evidence here").
- **A malformed AI output** (fails schema validation) is retried once with the validation error
  fed back to the model (the existing legacy pattern for this, in `app/ai/analyze_pillar.py`, is
  sound and worth reusing as a pattern) and, on a second failure, the dimension is marked
  `Unscored` with reason `extraction_failed` — never a best-effort partial parse.
- **A conflicting-claims tie that cannot be resolved** (spec Part 2.3) is not a failure at all —
  it is a correct, expected `disputed`/excluded-from-scoring outcome, logged as such for
  observability but never surfaced as an error.
- **Persistence failure** (the database write fails after a real, expensive research/Assessment
  pass) does not silently discard the computed result — the API returns a 5xx and the caller can
  retry against the same already-gathered evidence rather than re-running paid AI calls, exactly
  the reasoning behind keeping `assessments` (raw Assessment output) separate from `analyses`
  (Scoring output) in Part 3.2.

---

## Part 6 — Frontend Integration

**No existing dashboard component is modified in this phase.** A future, separately-scoped
implementation phase would add new components under `dashboard/components/evidence-engine/`,
reading the new API contract (Part 4) through a new typed client module
(`dashboard/lib/api/evidenceEngine.ts`), following the existing `lib/api/*.ts` thin-wrapper
convention already established for every other API surface. Proposed (design-only) product
surfaces:

- A Startup Profile section showing the new engine's Strength/Coverage/Confidence per pillar,
  visually distinct from the legacy score ring rather than blended with it (this session's own
  prior work on the `sps_v3` "Limited"/"Insufficient" badge pattern, in
  `ComparisonHeader.tsx`, is a proven, reusable *pattern* for showing a withheld/partial state
  honestly rather than a numeric ring — reused as a pattern, not its specific code).
- A "why this score" expandable detail view per dimension, listing its `supporting_claim_ids`
  resolved to their full `Claim` records via the Part 4.3 endpoint — the concrete product
  feature that makes evidence traceability (spec Design Principle 2) visible, not just
  internally true.
- Clear, separate visual treatment for `source.url` (locatable) vs. corroboration status
  (independently verified) — never one badge implying both (spec Part 2.5).

---

## Part 7 — Observability

- **Per-stage timing**, reusing this session's own already-proven pattern from
  `due_diligence_workflow.py::_log_stage()` (a hash-only run identifier, never raw company text
  or evidence content in a log line) — applied to this engine's own stages (Research, Ledger
  construction, Assessment, Scoring).
- **Per-analysis structural counters**, never containing evidence content: dimensions scored vs.
  `Unscored` (and, for `Unscored`, which reason — `no_evidence`, `stale`, `extraction_failed`,
  `stage_inapplicable`), pillars withheld and why, overall publishability outcome. These are the
  metrics a future calibration/monitoring pass would use to detect, e.g., a silent adapter
  regression (the exact failure mode that made the prior V3 engine's Financial Health pillar
  permanently empty without an obvious signal, per the spec's Part 8.2 finding) — this design
  makes that class of regression visible via a per-dimension "was this ever populated" counter
  rather than requiring a manual live-run check to discover it, as happened previously.
- **No new external monitoring service.** Reuses the existing `print()`-based logging
  convention this codebase already documents as its own observability approach.

---

## Part 8 — Open Questions Requiring Approval

**Decided (approved):**

1. **Package/methodology naming:** `app/evidence_engine/` / `evidence_engine.v1`. Confirmed.
2. **Company identity** (1.3, 3.3): fully decoupled lightweight reference, no dependency on
   V2's canonical Company resolution. Integration deferred indefinitely, revisit only if a
   later phase is separately scoped for it.
3. **Confidence's exact output shape** (spec Part 6.4): categorical Low/Medium/High.

**Still open (not needed by the current vertical slice):**

4. **Whether this engine's result is ever surfaced alongside the legacy/V3 result on the same
   Startup Profile page, or only reachable as its own separate view initially.** This document
   assumes "own separate view" as the lowest-risk first step (Part 6); combining them is a
   product decision for a later phase.
5. **Whether `Retention/Renewal Signal` and `Capital Efficiency`, both expected to be
   `Unscored` for the large majority of companies (spec Part 3.3), should be dropped from the
   dimension count entirely rather than kept as near-always-empty** — this document keeps them
   (an honestly-labeled `Unscored` dimension is still useful information, per Design Principle
   9) but flags that a reviewer may reasonably prefer a leaner framework; kept here for approval
   rather than decided.
