"""
Task 31 item 8/10 -- Evidence Engine v1 persistence (runtime reads/
writes, distinct from the DDL in app/evidence_v1/migrations/, which
creates the table this module reads and writes).

Reuses `app.database.db.engine` directly -- the SAME SQLAlchemy engine/
connection pool the legacy app already uses (same physical database,
same `DATABASE_URL`), rather than constructing a second pool in the same
process. This is a RUNTIME dependency only; the table this module
operates on was created by an entirely independent Alembic environment
(see alembic_evidence_v1.ini), and this module never issues DDL.

Every function here is a plain, parameterized SQL query -- no ORM, no
ownership/authorization logic (that stays the caller's job, matching
app/database/db.py's own established convention: "DB functions implement
queries/writes, not access control").
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import text

from app.database.db import engine
from app.evidence_v1.adapter import EvidenceV1RunResult
from app.evidence_v1.config import EVIDENCE_V1_METHODOLOGY_VERSION, Engine


def new_analysis_id() -> str:
    """A UUID4 hex string -- never a sequential integer (Task 31 item 20's
    own explicit 'cross-user enumeration' check: a sequential id would
    make guessing another user's analysis id trivial)."""
    return uuid.uuid4().hex


@dataclass(frozen=True)
class EvidenceV1AnalysisRow:
    id: str
    owner_user_id: str
    company_name: str
    canonical_website: str
    engine: str
    methodology_version: str
    stage: str | None
    run_status: str
    company_coverage_pct: float | None
    company_confidence: str | None
    company_publishable: bool | None
    result: dict
    telemetry: dict | None
    created_at: str


def save_evidence_v1_analysis(
    owner_user_id: str,
    company_name: str,
    canonical_website: str,
    run_result: EvidenceV1RunResult,
) -> str:
    """Writes exactly one row, once, after a completed run -- this table
    has no UPDATE path anywhere in this codebase; a row is immutable
    from the moment it is written (the migration's own docstring). The
    full, rich `EvidenceV1RunResult` (everything except the raw
    telemetry, split into its own column for cheaper operational
    queries) goes into `result` as JSONB. Returns the new, stable
    analysis id."""
    analysis_id = new_analysis_id()
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO evidence_v1_analyses (
                id, owner_user_id, company_name, canonical_website, engine,
                methodology_version, stage, run_status, company_coverage_pct,
                company_confidence, company_publishable, result, telemetry
            ) VALUES (
                :id, :owner_user_id, :company_name, :canonical_website, :engine,
                :methodology_version, :stage, :run_status, :company_coverage_pct,
                :company_confidence, :company_publishable, CAST(:result AS JSONB), CAST(:telemetry AS JSONB)
            )
        """), {
            "id": analysis_id,
            "owner_user_id": owner_user_id,
            "company_name": company_name,
            "canonical_website": canonical_website,
            "engine": Engine.EVIDENCE_V1.value,
            "methodology_version": EVIDENCE_V1_METHODOLOGY_VERSION,
            "stage": run_result.stage,
            "run_status": "completed",
            "company_coverage_pct": run_result.company_coverage_pct,
            "company_confidence": run_result.company_confidence,
            "company_publishable": run_result.company_publishable,
            "result": json.dumps({
                "company_ref": run_result.company_ref,
                "as_of": run_result.as_of,
                "generated_at": run_result.generated_at,
                "total_claims_in_ledger": run_result.total_claims_in_ledger,
                "rejected_count": run_result.rejected_count,
                "accepted_claims": run_result.accepted_claims,
                "pillar_results": run_result.pillar_results,
                "company_withhold_reasons": run_result.company_withhold_reasons,
                "cross_pillar_audit": run_result.cross_pillar_audit,
                "wall_clock_seconds": run_result.wall_clock_seconds,
            }),
            "telemetry": json.dumps(run_result.telemetry),
        })
    return analysis_id


def get_evidence_v1_analysis(analysis_id: str) -> EvidenceV1AnalysisRow | None:
    """Looked up by id ALONE -- ownership is enforced by the caller
    (`app/evidence_v1/service.py`), comparing `.owner_user_id` against
    the verified, authenticated caller, exactly the pattern
    `app/auth.py::require_startup_member()` already established. This
    function itself never takes a viewer identity -- it is a pure
    lookup, same convention as `app/database/db.py::get_analysis_by_id()`."""
    with engine.begin() as connection:
        row = connection.execute(text("""
            SELECT id, owner_user_id, company_name, canonical_website, engine,
                   methodology_version, stage, run_status, company_coverage_pct,
                   company_confidence, company_publishable, result, telemetry,
                   created_at
            FROM evidence_v1_analyses WHERE id = :id
        """), {"id": analysis_id}).mappings().first()
    if row is None:
        return None
    return EvidenceV1AnalysisRow(
        id=row["id"], owner_user_id=row["owner_user_id"], company_name=row["company_name"],
        canonical_website=row["canonical_website"], engine=row["engine"],
        methodology_version=row["methodology_version"], stage=row["stage"], run_status=row["run_status"],
        company_coverage_pct=row["company_coverage_pct"], company_confidence=row["company_confidence"],
        company_publishable=row["company_publishable"], result=row["result"], telemetry=row["telemetry"],
        created_at=row["created_at"].isoformat(),
    )


def list_evidence_v1_analyses_for_user(owner_user_id: str) -> list[dict]:
    """A deliberately flat, list-row shape -- mirrors `app/database/db.py
    ::get_my_analyses()`'s own 'this is a list view, not a second report
    experience' convention -- newest first, scoped STRICTLY to
    `owner_user_id = :owner_user_id` (never company name, never a
    membership/admin bypass, matching item 9's own privacy-boundary
    requirement)."""
    with engine.begin() as connection:
        rows = connection.execute(text("""
            SELECT id, company_name, canonical_website, company_coverage_pct,
                   company_confidence, company_publishable, created_at
            FROM evidence_v1_analyses
            WHERE owner_user_id = :owner_user_id
            ORDER BY created_at DESC
        """), {"owner_user_id": owner_user_id}).mappings().all()
    return [
        {
            "analysis_id": r["id"],
            "company_name": r["company_name"],
            "canonical_website": r["canonical_website"],
            "company_coverage_pct": r["company_coverage_pct"],
            "company_confidence": r["company_confidence"],
            "company_publishable": r["company_publishable"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]
