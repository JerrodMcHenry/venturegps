# Engine Transparency & Report Quality

**Portfolio Release Task 7, Phase 3.** Companion to `docs/portfolio/VENTUREGPS_READINESS_AUDIT.md` §4
(architecture/sequence diagrams, now updated for Phase 2's concurrency) and `docs/portfolio/AI_REQUEST_RELIABILITY.md`
(retry/backoff policy). This doc is the reference for what changed in Phase 3: making the real pipeline
explainable to an end user, making report conclusions honest about what is Observed vs. inferred vs.
simply unavailable, and adding processing-time observability — without changing the six-pillar scoring
methodology itself.

## The problem

Phases 1–2 made the engine faster and more architecturally sound, but three trust/clarity gaps remained
in what a user actually sees:

1. **No public explanation of how the pipeline works.** A user reading a report had no way to learn what
   is AI-generated versus deterministically computed, or that reproducible math does not imply a correct
   AI judgment.
2. **Key Risks conflated three different situations.** The report's "Key Risks" list was built from
   pillar-level free-text `weaknesses`, which is never reliably tagged to a specific evidence status. In
   practice this meant an *unavailable* metric (e.g. no disclosed revenue) could read exactly like an
   *observed* weakness (e.g. a disclosed customer-churn problem) — the report could not tell a reader
   which one it was looking at.
3. **No processing-time visibility.** Neither logs nor the UI conveyed how long an analysis takes or
   where the time goes, beyond the hard-coded loading copy already addressed in Task 6.

## The fix

### 1. A real, public "How It Works" page (`dashboard/app/how-it-works/page.tsx`)

Publicly reachable at `/how-it-works` (no `auth.protect()` — it's explanatory content, not account-gated),
linked from the primary nav, the homepage's own "How VentureGPS Uses AI" section, and the report's
existing "How this analysis was generated" disclosure. It describes the five real pipeline stages, in
order, matching `run_due_diligence()` exactly:

1. **Startup information** (input: pasted text, PDF, or website URL)
2. **AI-assisted research** (Tavily, 4 categories, now run concurrently — see §2 below)
3. **AI-generated assessments** (6 pillar analyses + 5 free-form calls, each a probabilistic LLM call)
4. **Deterministic validation and scoring** (Python — `finalize_pillar_score`, `calculate_weighted_score`,
   `calculate_base_score`, `clamp_score`; no LLM involved)
5. **VentureGPS Report** (the assembled, persisted result)

It states explicitly, in plain English, that stages 2–3 are probabilistic (the same input can in
principle produce different AI wording or judgments) while stage 4 is deterministic (the same validated
subscores always produce the same final score) — and that **"reproducible calculations do not mean the
AI's underlying judgments or claims are correct."** This is the one sentence Phase 3 was most explicit
about requiring verbatim in substance, and it is load-bearing: the deterministic scoring math being
reproducible is not evidence that the AI's read of a company's evidence was accurate.

### 2. Key Risks rebuilt from `Subscore.evidence_status`, not free text

`dashboard/components/startup/StartupHeroV2.tsx`'s Key Risks derivation was rewritten to iterate each
pillar's structured `score_breakdown.subscores` — the one place the backend already tags a per-dimension
`evidence_status: "Observed" | "Inferred" | "Unavailable"` — instead of reading `pillar.weaknesses[0]`.
Three, and only three, classifications are produced:

| Kind | When | Backend signal used |
|---|---|---|
| **Observed weakness** | `evidence_status === "Observed"` and `score < 5.0` | The dimension was actually evaluated against disclosed evidence and scored low |
| **Inferred risk** | `evidence_status === "Inferred"` and `score < 5.0` | The dimension was scored, but from inference rather than direct disclosure |
| **Information gap** | `evidence_status === "Unavailable"` | The dimension could not be scored at all — this is a gap in the input, not a demonstrated weakness |

This was a deliberate architectural choice, not a heuristic: an earlier option (keyword-matching the
free-text `weaknesses` strings to re-classify them) was considered and rejected as fragile and exactly the
kind of invented classification Phase 3's own instructions warned against ("use conservative wording and
explicit uncertainty disclosure ... rather than inventing a classification the backend cannot reliably
support"). `Subscore.evidence_status` is the only field the backend actually validates against evidence
rules (`app/ai/analyze_pillar.py::validate_evidence_requirements`), so it is the only field this feature
is built on. Results are deduplicated by normalized text and capped at 5 entries, sorted by
severity/kind so demonstrated weaknesses surface first, information gaps last. The pillar-level free-text
`summary` now carries an explicit disclaimer that it is an AI-written narrative synthesis, not
individually evidence-tagged — pointing readers to Key Risks and the Evidence section for the tagged
detail.

**No scoring changed.** This is a presentation-layer reclassification of existing, already-computed
`Subscore` data; `finalize_pillar_score`, pillar weights, and the overall VentureGPS Score are untouched.

### 3. Evidence transparency — honest about what's linked and what isn't

`EvidenceList` (`dashboard/components/startup/PillarWorkspace.tsx`) already rendered a clickable link when
an evidence item carries a real `url` — that code path was verified correct and left alone. What Phase 3
added is a disclosure directly above the evidence list, stating that quotes are direct excerpts from the
submitted material and research but are not individually linked to a specific source, and pointing to "How
this analysis was generated" for the public sources the analysis actually consulted
(`AnalysisContext.source_snapshot`, when recorded).

**The underlying gap, documented rather than silently worked around:** the backend `Evidence` Pydantic
model (`app/models/evidence.py`) has `source_type` and `verified` fields, but in practice the pillar
evidence-extraction prompts (`app/ai/analyze_pillar.py`) almost always populate evidence as plain strings
with no per-quote URL, and the frontend `Evidence` TypeScript type mirrors only `{source?, text?, title?,
url?}` with no verification field at all. Per Phase 3's own explicit instruction ("do not build a complex
new evidence database or undertake a large migration"), this was not solved with new infrastructure.
**Smallest proposed next step**, for a future task: have `extract_pillar_evidence()`'s prompt ask the
model to attribute each evidence item to one of the `source_snapshot` URLs already collected during
research enrichment when the quote plausibly came from that source, falling back to no URL rather than
guessing — a prompt/schema change with no new tables, since `source_snapshot` is already persisted per
analysis.

### 4. Processing-time observability (`app/workflows/due_diligence_workflow.py`)

`run_due_diligence()` now computes a hash-only `run_id` (`_new_run_id()` — a truncated SHA-256 of the
company text, never the raw text itself) and prints one duration line per major stage plus a final total,
via the existing `print()`-based logging convention already used throughout this codebase (no new
monitoring service):

```
[due_diligence_workflow] run_id=<12 hex chars> stage=research duration_s=<float>
[due_diligence_workflow] run_id=<12 hex chars> stage=free_form_calls duration_s=<float>
[due_diligence_workflow] run_id=<12 hex chars> stage=pillar_analyses duration_s=<float>
[due_diligence_workflow] run_id=<12 hex chars> stage=readiness_score duration_s=<float>
[due_diligence_workflow] run_id=<12 hex chars> stage=sps_v3_assessment duration_s=<float>   # only when SPS v3 is enabled
[due_diligence_workflow] run_id=<12 hex chars> stage=total duration_s=<float>
```

The `run_id` lets separate stage lines for the same request be correlated in logs without ever printing
company text, prompts, or credentials. `test_run_due_diligence_logs_a_duration_line_per_stage_and_a_total`
(`app/tests/test_pipeline_concurrency.py`) captures stdout and asserts the raw input company text never
appears in any log line, alongside the expected stage names and prefix.

## Concurrency and failure handling (carried over from Phase 2, restated here for completeness)

The three independent call groups this doc's pipeline stages 2–3 describe — 4 Tavily searches, 5 free-form
calls, 6 pillar analyses — run through the shared `app/ai/concurrency.py::run_concurrently()` helper: a
bounded `ThreadPoolExecutor` that reassembles results in deterministic input order regardless of which
task finishes first, and re-raises the first exception it sees rather than silently discarding a failed
task or returning a partial/misleading analysis. Each pillar's own two-call dependency (evidence
extraction before scoring) is preserved — only the six pillars run concurrently *with each other*.
`test_pipeline_concurrency.py`'s `test_full_pipeline_produces_identical_scores_regardless_of_completion_order`
is the regression test that would catch a concurrency-introduced ordering bug in the final assembled
score. See `docs/portfolio/VENTUREGPS_READINESS_AUDIT.md` §4.2 for the updated sequence diagram and §4.3
for the before/after latency framing.

## Testing

- `dashboard/tests/engineTransparency.test.ts` (11 tests) — the How It Works page's content/disclaimer/
  public-access/linking, the Key Risks evidence_status-based rebuild (including the structural check that
  an `Unavailable` dimension can never reach the `observed_weakness` branch), the Evidence section's
  honest disclosure, and the glossary cross-reference between Key Risks labels and raw evidence statuses.
- `app/tests/test_pipeline_concurrency.py` (14 tests, up from 13) — added
  `test_run_due_diligence_logs_a_duration_line_per_stage_and_a_total`.
- Full frontend suite (`npm test`, 34 suites), `npx tsc --noEmit`, `npm run lint`, and `npm run build`
  (including the new static `/how-it-works` route) all verified green after these changes.
- `dashboard/tests/unifiedNav.test.ts` and `dashboard/tests/visualSystem.test.ts` were re-verified,
  since Phase 3 touches nav links and reuses established shared visual primitives (`BaseCard` "glass",
  `PageHeader` "glow", `CollapsibleSection`) rather than introducing new ones.

## What this phase deliberately did not do

- No scoring formula, weight, prompt, or threshold change.
- No new evidence database, migration, or provenance backfill for historical analyses (existing analyses
  with blank `AnalysisContext` fields remain readable, just without those fields populated — unchanged
  from Task 5).
- No new monitoring/observability service — stage timing reuses the existing `print()`-based convention.
- No commit, push, or deploy.
