# ADR: Adopt `evidence-engine-v1-candidate.1` as the production candidate, behind a feature flag

- **Status:** Accepted (Task 31)
- **Scope:** `app/evidence_v1/` (new product-integration layer), `app/api.py::analyze_unified` (the one
  engine-selection boundary added), `evidence_v1_analyses` (new, independently-migrated table). Does not
  touch `app/evidence_engine/` (the isolated methodology engine itself, unchanged since Task 30) or
  `app/v2/`.
- **Enforced by:** `app/evidence_v1/config.py::resolve_engine()` (the one server-side authorization
  check), `EVIDENCE_V1_ENABLED` (default unset/false), `app/tests/test_evidence_v1_integration.py`.

## Context

Task 30 reached State A: "Evidence Engine v1 Candidate," identifier `evidence-engine-v1-candidate.1`.
The live validation demonstrated the critical production property this whole body of work (Tasks 20-30)
was built toward: *legitimate evidence survives; unsupported interpretations do not.* No production
blocker was identified; known beta limitations (metric period-date completeness, funding/market-recall
variance, a `team_identity.role` exact-match gap) all fail conservatively (withholding evidence, never
fabricating it).

The engine had never been connected to the real VentureGPS product -- every prior task ran it through
scratchpad scripts against real live companies, never through an authenticated user-facing flow, never
persisted anywhere a user could revisit it.

## Decision

Integrate Evidence Engine v1 into VentureGPS as a second, explicitly-identified analysis engine
(`evidence_v1`, alongside `legacy`), reachable only when both:

1. the client explicitly requests it (`engine=evidence_v1` on `POST /analyze`), and
2. the server independently has it enabled (`EVIDENCE_V1_ENABLED=true`).

The legacy analysis path (`run_due_diligence()`, the `analyses` table, `/startup/{company_name}`) is
**not modified, not deprecated, and not removed** by this decision. Both engines run side by side
indefinitely, until a SEPARATE, future decision (not this one) chooses to change that. This ADR commits
only to: Evidence Engine v1 is now reachable in the real product, behind a flag that defaults to off.

## Why behind a flag, not a full cutover

- Coverage remains genuinely low on real companies (Task 30's own Notion 003 run: 9.0%, not
  publishable) -- the methodology is honest about what it doesn't yet know, but that honesty means most
  real analyses today will be sparse. A full cutover would present users with a materially less complete
  report than the legacy product currently gives them, without warning.
- Known beta limitations (§ Context) are real, even though none are dangerous. A controlled rollout lets
  them be observed against real product traffic before wider exposure.
- The integration surface itself (this task) is new and unproven in production, independent of the
  methodology's own Task-30 validation -- a new adapter, a new persistence layer, a new report UI all
  deserve their own burn-in period.

## Why a second, independent persistence environment (not reusing `analyses` or `v2.*`)

See `docs/architecture/EVIDENCE_ENGINE_PRODUCT_INTEGRATION.md` §4 for the full technical account. In
short: the legacy `analyses` table's own shape (an overall 0-100 score, six legacy pillar score columns)
cannot represent this methodology's output without either dropping information or fabricating fields
that don't exist (no overall score, Coverage/Confidence instead of a score). The existing V2 Alembic
environment is structurally hard-wired to schema `v2` and cannot host an unrelated table without either
coupling it to V2's own domain metadata or modifying V2's own migration-safety scope -- and Evidence
Engine v1 is not part of the V2 rebuild, so doing either would create a misleading architectural
dependency. A small, independent, additive migration environment was the smallest change that avoided
both problems.

## Consequences

- A user can now complete the full loop this task's own success criterion names: authenticated
  submission -> Evidence Engine v1 runs -> a persisted, private, ownership-scoped analysis ->
  a reloadable, evidence-first report -- without touching or risking the existing legacy product.
- Every persisted Evidence-v1 row is permanently attributable to the exact engine and methodology
  version that produced it (`engine`, `methodology_version` columns) -- a future methodology change
  (Increment, calibration pass, or a genuine `evidence-engine-v2-candidate`) never has to guess which
  historical rows used which rules.
- Two Alembic environments now exist in this repository. This is a deliberate, documented exception, not
  an invitation to add a third for convenience -- any future genuinely new, architecturally-separate
  subsystem should make the same "does the existing environment structurally support this?" check this
  ADR made, not default to spinning up another one.

## Recommended next task

Controlled VentureGPS Product Integration is this task's own deliverable; what follows it is operational,
not architectural: enable `EVIDENCE_V1_ENABLED=true` in a staging/internal environment, run a handful of
real, authenticated, end-to-end submissions (not mocked) to confirm the full live path end-to-end
(including real OpenAI/Tavily calls, real persistence, real report rendering), then decide -- as its own,
separate, explicit decision -- whether and how to broaden access beyond internal testing.
