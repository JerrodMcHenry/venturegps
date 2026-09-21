"""Helpers for the resolution/promotion tests: real candidates through the real repositories. No AI, no network."""

import itertools

from sqlalchemy import text

from app.v2.repositories import company_candidates as candidates
from app.v2.repositories import processing_attempts as attempts
from app.v2.tests.db.candidate_fakes import make_proposal
from app.v2.tests.db.evidence_helpers import ingest_one

HUMAN = "admin:jerrod"
_counter = itertools.count(1)


def page_for(name: str, *identifiers: str) -> bytes:
    return ("<html><h1>" + name + "</h1><p>" + " ".join(identifiers) + "</p></html>").encode("utf-8")


def make_candidate(db, name="Acme Robotics, Inc.", *, domain=None, url=None, domain_needle=None):
    """One untrusted candidate (own observation and attempt). Returns the StoredCompanyCandidate."""
    n = next(_counter)
    payload = page_for(name, *(x for x in (domain_needle.decode() if domain_needle else domain, url) if x), f"n{n}")
    observation = ingest_one(db, record_id=f"rec-{n}", payload=payload, key=f"run-{n}").observation
    attempt = attempts.start_processing(db, observation.id, f"finder_{n}", f"finder_{n}.v1")
    proposal = make_proposal(payload, name, domain=domain, url=url, domain_needle=domain_needle)
    return candidates.store_company_candidates(db, attempt.id, [proposal]).candidates[0]


def canonical_counts(db) -> dict:
    with db.connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM v2.{t}")).scalar()
                for t in ("company", "resolution_decision", "company_name", "company_identifier")}


def untouched_snapshot(db) -> dict:
    """Every row of the layers a resolution must never modify."""
    out = {}
    with db.connect() as conn:
        for table, order in (("source", "id"), ("raw_payload", "content_hash"), ("observation", "id"),
                             ("observation_sighting", "id"), ("processing_attempt", "id"),
                             ("company_candidate", "id"), ("company_candidate_identifier", "id")):
            out[table] = [tuple(r) for r in conn.execute(text(f"SELECT * FROM v2.{table} ORDER BY {order}"))]
    return out
