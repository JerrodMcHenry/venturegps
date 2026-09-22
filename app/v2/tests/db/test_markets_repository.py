"""Market/TaxonomyVersion registration: reference data, directly registered (like v2.source)."""

import pytest

from app.v2.domain.errors import InvalidInputError
from app.v2.repositories import markets
from app.v2.repositories.errors import ConflictError

pytestmark = pytest.mark.db


def test_registering_a_market_returns_a_generated_persistent_identity(migrated_db):
    stored = markets.register_market(migrated_db, "robotics", "Robotics")
    assert stored.id is not None and stored.slug == "robotics" and stored.display_name == "Robotics"
    assert stored.created_at.tzinfo is not None
    assert markets.get_market(migrated_db, stored.id) == stored


def test_display_name_is_not_identity_and_duplicate_display_names_are_allowed(migrated_db):
    a = markets.register_market(migrated_db, "robotics", "Robotics")
    b = markets.register_market(migrated_db, "industrial-robotics", "Robotics")     # same display name, different slug
    assert a.id != b.id and a.display_name == b.display_name == "Robotics"
    assert {m.id for m in markets.list_markets(migrated_db)} == {a.id, b.id}


def test_slug_is_unique_routing_identity_not_the_uuid(migrated_db):
    markets.register_market(migrated_db, "robotics", "Robotics")
    with pytest.raises(ConflictError) as info:
        markets.register_market(migrated_db, "robotics", "Industrial Robotics")     # same slug, different name: still a conflict
    assert info.value.code == "market_slug_already_registered"
    assert markets.get_market_by_slug(migrated_db, "robotics").display_name == "Robotics"   # unchanged


def test_slug_and_uuid_are_independently_useful_for_lookup(migrated_db):
    stored = markets.register_market(migrated_db, "climate-tech", "Climate Tech")
    assert markets.get_market_by_slug(migrated_db, "climate-tech") == stored
    assert markets.get_market(migrated_db, stored.id) == stored
    assert markets.get_market_by_slug(migrated_db, "no-such-slug") is None


def test_a_market_has_no_bloated_profile_fields(migrated_db):
    from sqlalchemy import text
    with migrated_db.connect() as conn:
        columns = {r[0] for r in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name='market'"))}
    assert columns == {"id", "slug", "display_name", "created_at"}


def test_invalid_slug_or_display_name_is_refused_before_any_write(migrated_db):
    from app.v2.tests.db.evidence_helpers import count
    with pytest.raises(InvalidInputError):
        markets.register_market(migrated_db, "Not A Slug", "Robotics")
    with pytest.raises(InvalidInputError):
        markets.register_market(migrated_db, "robotics", "")
    assert count(migrated_db, "market") == 0


# ---------------- taxonomy version

def test_registering_a_taxonomy_version(migrated_db):
    stored = markets.register_taxonomy_version(migrated_db, "venturegps_taxonomy.v1")
    assert stored.taxonomy_version == "venturegps_taxonomy.v1" and stored.created_at.tzinfo is not None
    assert markets.get_taxonomy_version(migrated_db, "venturegps_taxonomy.v1") == stored


def test_taxonomy_version_history_is_reconstructable_and_never_silently_overwritten(migrated_db):
    v1 = markets.register_taxonomy_version(migrated_db, "venturegps_taxonomy.v1")
    v2 = markets.register_taxonomy_version(migrated_db, "venturegps_taxonomy.v2")
    assert [v.taxonomy_version for v in markets.list_taxonomy_versions(migrated_db)] == ["venturegps_taxonomy.v1", "venturegps_taxonomy.v2"]
    with pytest.raises(ConflictError) as info:
        markets.register_taxonomy_version(migrated_db, "venturegps_taxonomy.v1")
    assert info.value.code == "taxonomy_version_already_registered"
    assert markets.get_taxonomy_version(migrated_db, "venturegps_taxonomy.v1") == v1    # untouched


def test_taxonomy_version_shape_is_validated(migrated_db):
    for bad in ("v1", "latest", "1.0", "", None):
        with pytest.raises(InvalidInputError):
            markets.register_taxonomy_version(migrated_db, bad)
