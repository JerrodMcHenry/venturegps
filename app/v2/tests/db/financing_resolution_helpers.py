"""Helpers for the financing-resolution tests: real candidates through the real repositories."""

from sqlalchemy import text

from app.v2.tests.db.financing_fakes import canonical_company, form_d, start_attempt
from app.v2.repositories import financing_event_candidates as repo

HUMAN = "admin:jerrod"
FIN_TABLES = ("financing_event_candidate", "financing_event_candidate_amount", "financing_event_candidate_date")
CANONICAL_TABLES = ("financing_event", "financing_resolution_decision", "financing_event_stage", "financing_event_type",
                    "financing_event_verified_round_amount", "financing_event_date")


def canonical_financing_counts(db) -> dict:
    """Accepts an Engine (own connection) or a Connection (the caller's transaction, so uncommitted work is visible)."""
    if hasattr(db, "connect"):
        with db.connect() as conn:
            return {t: conn.execute(text(f"SELECT count(*) FROM v2.{t}")).scalar() for t in CANONICAL_TABLES}
    return {t: db.execute(text(f"SELECT count(*) FROM v2.{t}")).scalar() for t in CANONICAL_TABLES}


def make_financing_candidate(db, proposal_fn, payload, **kw):
    """Ingest, start an attempt and persist ONE financing candidate built by proposal_fn(payload, company_id, **kw)."""
    company = kw.pop("company", None) or canonical_company(db)
    _, attempt = start_attempt(db, payload)
    proposal = proposal_fn(payload, company, **kw) if proposal_fn is not form_d else form_d(company)
    return repo.persist_financing_event_candidates(db, attempt.id, [proposal]).candidates[0], company
