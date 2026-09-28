"""
VentureGPS Evidence Engine (methodology identifier: evidence_engine.v1).

Isolated by design: this package must never import app.ai, app.database,
app.api, app.models, or app.v2 (see docs/architecture/NEW_ENGINE_ARCHITECTURE.md
Part 1.2). It may import pure infrastructure that contains no scoring logic
(e.g. app.pdf_extractor, app.website_scrapper, app.ai.concurrency) -- none of
that is used yet in this first vertical slice.

See app/evidence_engine/README.md for exactly what is implemented so far vs.
what remains design-only in docs/methodology/NEW_ENGINE_SPEC.md and
docs/architecture/NEW_ENGINE_ARCHITECTURE.md.
"""
