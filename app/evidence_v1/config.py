"""
Task 31 item 4 -- the one server-side engine-selection boundary.

**Safe default: `legacy`.** `evidence_v1` requires explicit, server-side
enablement (`EVIDENCE_V1_ENABLED=true`) -- a client requesting
`engine=evidence_v1` is never itself the authorization boundary for
rollout; the server independently validates the request against this
configuration and silently falls back to `legacy` when evidence_v1 is
not server-enabled (never a 500, never a surprising hard failure for an
otherwise-ordinary request -- see `resolve_engine()`'s own docstring for
exactly what "silently" means here).

No secret lives in this module -- `EVIDENCE_V1_ENABLED` is a plain
boolean flag, safe to reference (not its value) in logs.
"""

from __future__ import annotations

import os
from enum import Enum


class Engine(str, Enum):
    LEGACY = "legacy"
    EVIDENCE_V1 = "evidence_v1"


# The one, explicit candidate identifier this engine's persisted rows are
# stamped with (Task 30's own `evidence-engine-v1-candidate.1`). A plain
# constant, not derived from `app.evidence_engine.parameters.PARAMETER_
# VERSION` -- the product-integration identifier and the methodology's
# own internal calibration-version string are deliberately two different
# concepts (see docs/architecture/EVIDENCE_ENGINE_PRODUCT_INTEGRATION.md).
EVIDENCE_V1_METHODOLOGY_VERSION = "evidence-engine-v1-candidate.1"


def evidence_v1_enabled() -> bool:
    """Server-side rollout gate. Reads fresh from the environment on
    every call (no caching to go stale), mirroring `app/auth.py`'s own
    `_resolve_admin_user_ids()` pattern -- an unset or non-"true" value
    means disabled, fail closed, never fail open."""
    raw = os.environ.get("EVIDENCE_V1_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def resolve_engine(requested: str | None) -> Engine:
    """The ONE place engine selection is decided (item 2's own "do not
    scatter feature-flag checks throughout the codebase; create one
    clear orchestration boundary"). A request with no `engine` field, an
    unrecognized value, or `engine=evidence_v1` while the server-side
    flag is off, all resolve to `Engine.LEGACY` -- the existing,
    unmodified production path. Only an explicit `engine=evidence_v1`
    request, while `EVIDENCE_V1_ENABLED` is true server-side, resolves to
    `Engine.EVIDENCE_V1`. Never raises -- an invalid/unsupported engine
    value is a safe-default situation, not an error, exactly like every
    other unrecognized-but-optional request field elsewhere in this
    codebase."""
    if requested == Engine.EVIDENCE_V1.value and evidence_v1_enabled():
        return Engine.EVIDENCE_V1
    return Engine.LEGACY
