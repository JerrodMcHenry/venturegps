"""
VentureGPS V2 -- deterministic truth foundation.

Everything under app/v2 EXCEPT app/v2/ai and app/v2/tests is the
"deterministic core". It must stay importable and correct with no AI
provider SDK, no AI credentials, and no model network access. That rule
is enforced by app/v2/tests/architecture/, not by convention.

V2 does not import legacy code (app.ai, app.database, app.api, ...). See
docs/v2/ADR-0001-truth-model.md.
"""
