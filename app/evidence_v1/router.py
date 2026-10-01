"""
Task 31 item 10 -- authenticated Evidence Engine v1 retrieval. Mounted
into app/api.py the same way app/v2/api.py and app/v2_review_api.py
already are (app.include_router()) -- no V1 route is touched by this
file's existence.

Both routes below are RequireAuth-gated and ownership-scoped to
`current_user.user_id` -- never by company name (item 9's own privacy
boundary). A submission the caller does not own is a 404, never a
distinguishing 403 -- same discipline `app/auth.py::require_startup_
member()` already established for the legacy app, so probing an
analysis id can never be used to learn whether it exists.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.auth import AuthenticatedUser, RequireAuth
from app.evidence_v1.service import get_owned_evidence_v1_analysis, list_my_evidence_v1_analyses

router = APIRouter()


@router.get("/me/analyses/evidence-v1")
def list_my_evidence_v1_analyses_route(current_user: AuthenticatedUser = RequireAuth):
    """A separate list endpoint from legacy's GET /me/analyses, by
    design -- the two engines' rows live in two different tables with
    two different shapes (item 3/17); the frontend combines both lists
    for one unified "My Analyses" view rather than this backend
    pretending they are the same kind of row."""
    return list_my_evidence_v1_analyses(current_user.user_id)


@router.get("/evidence-v1/analyses/{analysis_id}")
def get_evidence_v1_analysis_route(analysis_id: str, current_user: AuthenticatedUser = RequireAuth):
    """Returns the persisted result WITHOUT rerunning acquisition (item
    10's own explicit requirement) -- a pure read of the immutable row
    `app/evidence_v1/persistence/repository.py::save_evidence_v1_
    analysis()` wrote once, at submission time."""
    row = get_owned_evidence_v1_analysis(analysis_id, current_user.user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    return {
        "analysis_id": row.id,
        "engine": row.engine,
        "methodology_version": row.methodology_version,
        "company_name": row.company_name,
        "canonical_website": row.canonical_website,
        "stage": row.stage,
        "run_status": row.run_status,
        "company_coverage_pct": row.company_coverage_pct,
        "company_confidence": row.company_confidence,
        "company_publishable": row.company_publishable,
        "created_at": row.created_at,
        "result": row.result,
        "telemetry": row.telemetry,
    }
