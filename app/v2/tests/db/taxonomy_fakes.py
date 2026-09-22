"""Shared fixtures for classification / Capital metrics tests."""

from app.v2.domain.resolution import human_authority
from app.v2.repositories import markets

HUMAN = "admin:jerrod"
ME = human_authority(HUMAN)
TV1 = "venturegps_taxonomy.v1"
TV2 = "venturegps_taxonomy.v2"


def setup_taxonomy(db, *slugs_and_names, taxonomy_version=TV1):
    """Registers `taxonomy_version` and each (slug, display_name) market; returns {slug: StoredMarket}."""
    markets.register_taxonomy_version(db, taxonomy_version)
    return {slug: markets.register_market(db, slug, name) for slug, name in slugs_and_names}
