"""
Evidence Acquisition Pipeline (Task 20) -- the bridge from a raw company
identity/website to the canonical `EvidenceLedger` every pillar already
consumes. See `docs/architecture/EVIDENCE_ACQUISITION_PIPELINE.md` for
the full design and `docs/methodology/NEW_ENGINE_E2E_EVALUATION.md` for
the offline end-to-end test results.

This subpackage is part of the isolated evidence engine -- it imports
nothing from `app.ai`, `app.database`, `app.api`, `app.models`, `app.v2`,
or `app.auth`, and nothing outside `app.evidence_engine` at all (Task 20
item 1's own "reuse infrastructure where appropriate... do not couple
the new evidence engine back to legacy scoring models" is satisfied here
by reusing the established PATTERN the architecture document already
approved for the Tavily research step -- modeled on, never importing,
`app/ai/research_enrichment.py` -- rather than importing any existing
app-level ingestion utility directly, keeping this subpackage inside the
exact same zero-import boundary the rest of `app/evidence_engine/`
already guarantees).

**The one rule this entire subpackage exists to enforce structurally:
AI helps discover and structure evidence; deterministic software decides
what that evidence means under the methodology.** No function in this
subpackage ever asks a model for a score, a label the methodology
doesn't define, or a subjective judgment -- extraction produces typed
claim candidates; everything downstream of that (grounding validation,
canonical identity, contradiction detection, ledger construction) is
pure, deterministic Python, identical in spirit to every pillar's own
`classify_with_recovery()`/`extract_with_recovery()` boundary.
"""
