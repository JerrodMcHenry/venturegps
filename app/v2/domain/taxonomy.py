"""
Minimal canonical Market/taxonomy identity, and the explicit, versioned Company -> Market classification.

    Market                       a canonical taxonomy node (e.g. "Robotics"). An identity anchor, not a profile:
                                  no description, icon, score or summary. display_name is NOT identity.
    TaxonomyVersion               a registered version id (e.g. "venturegps_taxonomy.v1"). Classification always
                                  names the version it was made under, so taxonomy history stays reconstructable
                                  and a methodology change never silently overwrites an old classification -- it
                                  is expressed as a NEW version, with new classification rows.
    CompanyMarketClassification   an explicit, authoritative, append-only fact: "under taxonomy version V, Company
                                  C was classified into Market M with role R, by this authority."

ROLE and Capital attribution: `primary` owns Capital attribution (Financing Activity, Capital Deployed, ...);
`secondary` is discovery/context only and contributes NOTHING to aggregate Capital metrics -- attributing the same
financing to two Markets because a Company has two classifications would double-count real capital. A Company may
hold at most one PRIMARY classification per taxonomy version (there is nothing to disambiguate two primaries), but
any number of secondary ones.

AUTHORITY: reuses app.v2.domain.resolution.Authority/AuthorityKind (rule | human; AI cannot be constructed, and an
actor id that names an AI is refused). CLASSIFICATION_RULE_AUTHORITY is deliberately EMPTY: no deterministic rule
for Company -> Market classification is safe yet (same company/name/sector guess is not sufficient), so today only a
human may classify -- may_classify() encodes that, and the database refuses every 'rule' decision unconditionally.

This module is pure: no persistence, no network, no AI.
"""

import re
from enum import Enum
from uuid import UUID

from pydantic import Field

from app.v2.domain.base import DomainModel
from app.v2.domain.errors import InvalidInputError
from app.v2.domain.resolution import Authority, AuthorityKind
from app.v2.domain.time import UtcDatetime
from app.v2.domain.versions import VersionId

MAX_SLUG_LENGTH = 80
MAX_DISPLAY_NAME_LENGTH = 200

_SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

# No financing/company-market classification rule is registered: a rule can never actually classify (see may_classify).
CLASSIFICATION_RULE_AUTHORITY: frozenset[str] = frozenset()


class ClassificationRole(str, Enum):
    PRIMARY = "primary"      # owns Capital attribution
    SECONDARY = "secondary"  # discovery/context only; never double-counted into aggregate Capital metrics


def validate_market_slug(value: object) -> str:
    """A lowercase, hyphenated routing identity. NOT the Market's identity (that is the UUID) -- a slug may be
    reused for a different taxonomy node only by retiring one Market and registering a new slug; this module does
    not support renaming a slug in place."""
    if not isinstance(value, str) or not (1 <= len(value) <= MAX_SLUG_LENGTH) or _SLUG.fullmatch(value) is None:
        raise InvalidInputError("invalid_market_slug", "market slug must be lowercase, hyphenated ASCII (e.g. 'robotics')")
    return value


def validate_market_display_name(value: object) -> str:
    if (not isinstance(value, str) or not value or len(value) > MAX_DISPLAY_NAME_LENGTH
            or value != value.strip() or _CONTROL.search(value)):
        raise InvalidInputError("invalid_market_display_name", "display name must be 1-200 printable characters without surrounding whitespace")
    return value


def may_classify(authority: Authority) -> bool:
    """A human may always classify. A rule may only if it is a REGISTERED classification rule -- none is, so a
    rule can decide nothing here today."""
    if authority.kind is AuthorityKind.HUMAN:
        return True
    return authority.id in CLASSIFICATION_RULE_AUTHORITY


class StoredMarket(DomainModel):
    """A bare taxonomy-node identity: an opaque id, a routing slug, and a display name. Not a profile."""

    id: UUID
    slug: str
    display_name: str
    created_at: UtcDatetime


class StoredTaxonomyVersion(DomainModel):
    taxonomy_version: VersionId
    created_at: UtcDatetime


class StoredCompanyMarketClassification(DomainModel):
    id: int = Field(gt=0)
    company_id: UUID
    market_id: UUID
    taxonomy_version: VersionId
    role: ClassificationRole
    authority: Authority
    created_at: UtcDatetime
