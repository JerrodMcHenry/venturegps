"""Pure tests: Market/TaxonomyVersion identity shape, classification role vocabulary, authority. No database."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.v2.domain.errors import DomainError, InvalidInputError
from app.v2.domain.resolution import human_authority, rule_authority
from app.v2.domain.taxonomy import (
    CLASSIFICATION_RULE_AUTHORITY,
    ClassificationRole,
    StoredCompanyMarketClassification,
    StoredMarket,
    StoredTaxonomyVersion,
    may_classify,
    validate_market_display_name,
    validate_market_slug,
)

NOW = datetime(2026, 9, 22, tzinfo=timezone.utc)


def test_market_identity_is_a_uuid_not_the_slug_or_display_name():
    market = StoredMarket(id=uuid.uuid4(), slug="robotics", display_name="Robotics", created_at=NOW)
    assert isinstance(market.id, uuid.UUID)
    other = StoredMarket(id=uuid.uuid4(), slug="robotics-2", display_name="Robotics", created_at=NOW)   # same display name
    assert market.id != other.id                                                                          # never equated by name


@pytest.mark.parametrize("slug", ["robotics", "ai-infrastructure", "a", "a1-b2", "x" * 80])
def test_valid_slugs(slug):
    assert validate_market_slug(slug) == slug


@pytest.mark.parametrize("slug", ["", "Robotics", "ai_infra", "-robotics", "robotics-", "ai--infra", "robotics ", " robotics",
                                  "x" * 81, "robótics", None, 5])
def test_invalid_slugs_are_refused(slug):
    with pytest.raises(InvalidInputError):
        validate_market_slug(slug)


@pytest.mark.parametrize("name", ["Robotics", "AI Infrastructure", "Climate Tech", "A" * 200])
def test_valid_display_names(name):
    assert validate_market_display_name(name) == name


@pytest.mark.parametrize("name", ["", " Robotics", "Robotics ", "A" * 201, "Ro\x01botics", None, 5])
def test_invalid_display_names_are_refused(name):
    with pytest.raises(InvalidInputError):
        validate_market_display_name(name)


def test_no_bloated_market_profile_fields():
    assert set(StoredMarket.model_fields) == {"id", "slug", "display_name", "created_at"}
    for banned in ("description", "icon", "summary", "score", "seo", "logo", "color", "category"):
        assert banned not in StoredMarket.model_fields


# ---------------- taxonomy version

def test_taxonomy_version_is_an_explicit_versioned_string():
    tv = StoredTaxonomyVersion(taxonomy_version="venturegps_taxonomy.v1", created_at=NOW)
    assert tv.taxonomy_version == "venturegps_taxonomy.v1"
    with pytest.raises(DomainError):
        StoredTaxonomyVersion(taxonomy_version="v1", created_at=NOW)
    with pytest.raises(DomainError):
        StoredTaxonomyVersion(taxonomy_version="latest", created_at=NOW)


# ---------------- classification role / authority

def test_role_vocabulary_is_exactly_primary_and_secondary():
    assert {r.value for r in ClassificationRole} == {"primary", "secondary"}


def test_no_classification_rule_is_registered_only_a_human_may_classify():
    assert CLASSIFICATION_RULE_AUTHORITY == frozenset()
    assert may_classify(human_authority("admin:jerrod"))
    assert not may_classify(rule_authority("exact_identifier_match.v1"))   # a valid Company rule id, reused only as a shape example


def test_ai_authority_cannot_be_constructed():
    with pytest.raises(Exception):
        human_authority("ai:gpt4")


def test_classification_shape():
    c = StoredCompanyMarketClassification(id=1, company_id=uuid.uuid4(), market_id=uuid.uuid4(),
                                          taxonomy_version="venturegps_taxonomy.v1", role=ClassificationRole.PRIMARY,
                                          authority=human_authority("admin:jerrod"), created_at=NOW)
    assert c.role is ClassificationRole.PRIMARY and c.authority.kind.value == "human"
    for extra in ("evidence", "confidence", "score", "reason_code"):
        with pytest.raises(ValidationError):
            StoredCompanyMarketClassification(id=1, company_id=uuid.uuid4(), market_id=uuid.uuid4(),
                                              taxonomy_version="venturegps_taxonomy.v1", role=ClassificationRole.PRIMARY,
                                              authority=human_authority("admin:jerrod"), created_at=NOW, **{extra: 1})
