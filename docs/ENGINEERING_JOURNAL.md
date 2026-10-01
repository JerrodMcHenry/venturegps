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
