"""Company -> Market classification: human authority, primary/secondary roles, one-primary-per-version, immutability."""

import uuid

import pytest
from sqlalchemy import text

from app.v2.classification import service
from app.v2.classification.errors import AlreadyClassifiedError, PrimaryAlreadyAssignedError
from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.resolution import rule_authority
from app.v2.domain.taxonomy import ClassificationRole
from app.v2.repositories import markets
from app.v2.repositories.errors import NotFoundError
from app.v2.tests.db.financing_fakes import canonical_company
from app.v2.tests.db.resolution_helpers import canonical_counts, untouched_snapshot
from app.v2.tests.db.taxonomy_fakes import ME, TV1, TV2, setup_taxonomy

pytestmark = pytest.mark.db

PRIMARY, SECONDARY = ClassificationRole.PRIMARY, ClassificationRole.SECONDARY


@pytest.fixture
def world(migrated_db):
    db = migrated_db
    taxonomy = setup_taxonomy(db, ("robotics", "Robotics"), ("ai-infrastructure", "AI Infrastructure"))
    company = canonical_company(db)
    return db, company, taxonomy


def test_a_human_creates_a_primary_classification(world):
    db, company, taxonomy = world
    before = untouched_snapshot(db)
    result = service.classify_company(db, company, taxonomy["robotics"].id, TV1, PRIMARY, ME)
    c = result.classification
    assert c.company_id == company and c.market_id == taxonomy["robotics"].id and c.taxonomy_version == TV1
    assert c.role is PRIMARY and c.authority == ME and c.created_at.tzinfo is not None
    assert canonical_counts(db)["company"] == 1 and untouched_snapshot(db) == before   # Company unchanged


def test_a_human_creates_a_secondary_classification(world):
    db, company, taxonomy = world
    result = service.classify_company(db, company, taxonomy["ai-infrastructure"].id, TV1, SECONDARY, ME)
    assert result.classification.role is SECONDARY


def test_a_company_may_hold_one_primary_and_multiple_secondary_markets(world):
    db, company, taxonomy = world
    service.classify_company(db, company, taxonomy["robotics"].id, TV1, PRIMARY, ME)
    service.classify_company(db, company, taxonomy["ai-infrastructure"].id, TV1, SECONDARY, ME)
    other = markets.register_market(db, "defense-tech", "Defense Tech")
    service.classify_company(db, company, other.id, TV1, SECONDARY, ME)
    with db.connect() as conn:
        rows = conn.execute(text("SELECT market_id, role FROM v2.company_market_classification WHERE company_id = :c ORDER BY id"), {"c": company}).all()
    assert [r.role for r in rows] == ["primary", "secondary", "secondary"]


def test_only_one_primary_market_per_company_per_taxonomy_version(world):
    db, company, taxonomy = world
    service.classify_company(db, company, taxonomy["robotics"].id, TV1, PRIMARY, ME)
    with pytest.raises(PrimaryAlreadyAssignedError):
        service.classify_company(db, company, taxonomy["ai-infrastructure"].id, TV1, PRIMARY, ME)   # a DIFFERENT market, still refused
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.company_market_classification WHERE company_id = :c AND role = 'primary'"), {"c": company}).scalar() == 1


def test_the_same_company_market_taxonomy_version_cannot_be_classified_twice(world):
    db, company, taxonomy = world
    service.classify_company(db, company, taxonomy["robotics"].id, TV1, SECONDARY, ME)
    with pytest.raises(AlreadyClassifiedError):
        service.classify_company(db, company, taxonomy["robotics"].id, TV1, SECONDARY, ME)
    with pytest.raises(AlreadyClassifiedError):
        service.classify_company(db, company, taxonomy["robotics"].id, TV1, PRIMARY, ME)   # even a different role: same triple


def test_a_new_taxonomy_version_allows_a_different_primary_without_touching_the_old_one(world):
    db, company, taxonomy = world
    markets.register_taxonomy_version(db, TV2)
    first = service.classify_company(db, company, taxonomy["robotics"].id, TV1, PRIMARY, ME).classification
    second = service.classify_company(db, company, taxonomy["ai-infrastructure"].id, TV2, PRIMARY, ME).classification
    assert first.market_id != second.market_id
    with db.connect() as conn:
        v1 = conn.execute(text("SELECT market_id FROM v2.company_market_classification WHERE company_id=:c AND taxonomy_version=:t"), {"c": company, "t": TV1}).scalar()
    assert v1 == taxonomy["robotics"].id                     # the v1 classification is untouched by the v2 one


# ---------------- authority

def test_ai_authority_is_impossible_and_no_rule_can_classify(world):
    db, company, taxonomy = world
    with pytest.raises(InvalidInputError):
        service.classify_company(db, company, taxonomy["robotics"].id, TV1, PRIMARY, "ai")
    with pytest.raises(InvariantViolationError):
        service.classify_company(db, company, taxonomy["robotics"].id, TV1, PRIMARY, rule_authority("exact_identifier_match.v1"))
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.company_market_classification")).scalar() == 0


def test_a_forged_authority_that_skips_validation_is_still_refused(world):
    db, company, taxonomy = world
    from app.v2.domain.resolution import Authority
    forged = Authority.model_construct(kind="ai", id="admin:jerrod")
    with pytest.raises(InvalidInputError):
        service.classify_company(db, company, taxonomy["robotics"].id, TV1, PRIMARY, forged)


# ---------------- existence checks

def test_unknown_company_market_or_taxonomy_version_are_not_found(world):
    db, company, taxonomy = world
    with pytest.raises(NotFoundError) as info:
        service.classify_company(db, uuid.uuid4(), taxonomy["robotics"].id, TV1, PRIMARY, ME)
    assert info.value.code == "company_not_found"
    with pytest.raises(NotFoundError) as info:
        service.classify_company(db, company, uuid.uuid4(), TV1, PRIMARY, ME)
    assert info.value.code == "market_not_found"
    with pytest.raises(NotFoundError) as info:
        service.classify_company(db, company, taxonomy["robotics"].id, "venturegps_taxonomy.v9", PRIMARY, ME)
    assert info.value.code == "taxonomy_version_not_found"


def test_invalid_role_is_refused(world):
    db, company, taxonomy = world
    with pytest.raises(InvalidInputError):
        service.classify_company(db, company, taxonomy["robotics"].id, TV1, "primary", ME)


# ---------------- immutability

def test_classification_history_is_append_only(world):
    db, company, taxonomy = world
    service.classify_company(db, company, taxonomy["robotics"].id, TV1, PRIMARY, ME)
    from app.v2.tests.db.evidence_helpers import refused
    from sqlalchemy.exc import DBAPIError, IntegrityError
    ANY = (IntegrityError, DBAPIError)
    for sql in ("UPDATE v2.company_market_classification SET role = 'secondary'", "DELETE FROM v2.company_market_classification",
               "TRUNCATE v2.company_market_classification CASCADE"):
        _, message = refused(db, sql, exc=ANY)
        assert "append-only" in message
