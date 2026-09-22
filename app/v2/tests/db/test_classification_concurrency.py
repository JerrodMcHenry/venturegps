"""Concurrent classification: the database (partial unique index) is the final authority."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.v2.classification import service
from app.v2.classification.errors import AlreadyClassifiedError, PrimaryAlreadyAssignedError
from app.v2.domain.taxonomy import ClassificationRole
from app.v2.repositories.errors import ConflictError
from app.v2.tests.db.financing_fakes import canonical_company
from app.v2.tests.db.taxonomy_fakes import ME, TV1, setup_taxonomy

pytestmark = pytest.mark.db


def run_all(fn, n=12):
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(fn, range(n)))


def outcome(fn):
    try:
        return fn()
    except ConflictError as exc:
        return type(exc)


def test_concurrent_primary_classification_attempts_admit_exactly_one_winner(migrated_db):
    db = migrated_db
    taxonomy = setup_taxonomy(db, ("robotics", "Robotics"), ("ai-infrastructure", "AI Infrastructure"))
    company = canonical_company(db)
    def act(i):
        market = taxonomy["robotics"] if i % 2 == 0 else taxonomy["ai-infrastructure"]
        return outcome(lambda: service.classify_company(db, company, market.id, TV1, ClassificationRole.PRIMARY, ME))
    results = run_all(act)
    with db.connect() as conn:
        from sqlalchemy import text
        count = conn.execute(text("SELECT count(*) FROM v2.company_market_classification WHERE company_id = :c AND role = 'primary'"), {"c": company}).scalar()
    assert count == 1
    assert sum(1 for r in results if not isinstance(r, type)) == 1
    assert all(r in (PrimaryAlreadyAssignedError, AlreadyClassifiedError) for r in results if isinstance(r, type))
