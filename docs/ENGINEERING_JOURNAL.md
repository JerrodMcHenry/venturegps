# Engineering Journal

A short, dated log of significant engineering decisions and milestones. Not a duplicate of git history or
of the detailed per-task methodology/architecture docs (`docs/methodology/`, `docs/architecture/`) --
those remain the source of truth for what was built and why; this file is a chronological index pointing
into them.

---

## 2026-09-30 -- Evidence Engine v1 enters the real product, behind a flag

**What changed.** `app/evidence_engine/` (the isolated, methodology-validated Evidence Engine,
`evidence-engine-v1-candidate.1`, Task 30's own "State A" gate) is now reachable through the real
VentureGPS product for the first time -- `POST /analyze` gained a server-side-gated `engine` parameter;
a new, independent product-integration layer (`app/evidence_v1/`) adapts, orchestrates, and persists its
output; a new, independently-migrated table (`evidence_v1_analyses`) stores results; a new report route
(`/evidence/{analysisId}`) renders them. The legacy analysis path is completely unmodified and remains
the default for every request.

**Why now.** Tasks 20-30 built and live-validated the Evidence Engine in isolation, culminating in Task
30's explicit production-readiness gate. This task (31) is the first time it was connected to anything a
real, authenticated user could reach.

**Key decisions** (full detail in `docs/architecture/EVIDENCE_ENGINE_PRODUCT_INTEGRATION.md` and
`docs/architecture/ADR-evidence-engine-v1-candidate.md`):

- One server-side engine-selection boundary (`app/evidence_v1/config.py::resolve_engine()`), safe
  default `legacy`. A client requesting `evidence_v1` never authorizes it by itself.
- A second, independent Alembic migration environment (`alembic_evidence_v1.ini`), rather than either
  extending the frozen legacy `add_*_column()` pattern (CLAUDE.md's explicit DDL freeze) or coupling
  Evidence v1's persistence to the unrelated V2 rebuild's own schema-`v2`-only Alembic setup.
- Evidence-v1's own report is genuinely new UI, not a retrofit of the legacy scorecard -- no overall
  0-100 score anywhere; Coverage/Confidence/publication status are presented as their own concept.
- Privacy boundary re-verified (not merely assumed) before exposing anything: the legacy
  `/startup/{company_name}` visibility fix from a prior phase (Portfolio Release Task 3B) is confirmed
  still intact; Evidence v1's own retrieval is ownership-scoped strictly by analysis id, never company
  name, with a byte-identical 404 for "not yours" and "doesn't exist."

**State:** `EVIDENCE_V1_ENABLED` unset (off) in every environment by default. Not yet deployed or enabled
anywhere. Full completion report: this task's own final message (Task 31).

---

## 2026-10-01 -- Evidence Engine v1 deployed to real production

**What changed.** Tasks 32-34, in sequence: (32) validated the full integrated product flow against a real
authenticated local browser session; (33) polished the integrated UX (discoverability, terminology,
accessibility), triaged and fixed five stale legacy test files (all failing on the same already-intentional
`/rankings` auth change, not a regression), and wrote the deployment/production-config documentation this
task relied on; (34) ran the actual controlled production deployment -- migrated `evidence_v1_analyses`
against the real production database (Render one-off jobs, so the real `DATABASE_URL` was never seen by the
operator), deployed with the flag off, verified baseline health, then set `EVIDENCE_V1_ENABLED=true` and ran
one real, paid, authenticated production analysis (Notion) end to end: engine selection, live provider
calls, persistence, report rendering, reload-without-re-acquisition, and an independently-verified
unauthenticated-401 privacy boundary.

**Why now.** Task 33's own decision gate (State A) found the integration ready; Task 34 executed the
deployment itself rather than leaving it as an unvalidated "should work" claim.

**Key decisions and findings:** full detail in `docs/validation/EVIDENCE_V1_PRODUCTION_SMOKE_001.md`.
Notably: Render's `autoDeploy` had already shipped the code before the migration ran (flag still off, so
harmless); the operator's own Render API key was deliberately never extracted or used directly by the
operator-automation session (declined by its own safety controls) -- the flag flip was done by hand in the
Render dashboard instead, and the migration itself ran via Render's one-off-job mechanism specifically so no
credential needed to be read by the automation at all.

**State:** `EVIDENCE_V1_ENABLED=true` in production. Evidence Engine v1 is live, deployed, and validated --
see the README's "Current status" section.

---

## 2026-10-01 -- Portfolio closeout

**What changed.** Documentation-only pass (Task 35): rewrote the root README around the now-current,
production-deployed Evidence-v1 architecture (it previously described only the legacy six-pillar engine,
with no mention of Evidence Engine v1 at all -- a real contradiction between the docs and the deployed
system, now fixed); extended `docs/portfolio/EVIDENCE_ENGINE_V1_ARCHITECTURE.md` with explicit trust-
boundary and fail-closed-behavior sections; added the engineering case study, interview guide, resume
bullets, demo script, and screenshot checklist under `docs/portfolio/`. Two genuine repository-hygiene
defects were found and fixed (no application/methodology code touched): `dashboard/package.json`'s `test`
aggregate never actually ran `test:evidenceV1` (18 tests, existing since Task 31, silently never exercised
by CI), and `.github/workflows/ci.yml` never had a step for `test_evidence_v1_integration.py` (14 tests) at
all -- both added, mirroring the exact existing pattern for every other suite/step in their respective jobs.

**State:** documented, closed. See this task's own completion report for the full list of what changed and
why.
