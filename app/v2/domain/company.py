"""
Canonical Company identity: the first TRUSTED entity in V2, and only ever created
through an explicit ResolutionDecision (app.v2.domain.resolution).

A Company is an identity anchor: an opaque UUID and a database-owned creation
time, nothing else. Its identity is NOT its name, a domain, a URL, a candidate
id or anything a model produced, and it survives renames, domain changes and
new evidence. Names and identifiers are separate, append-only accepted facts,
each carrying the ResolutionDecision that accepted it (and through it the
candidate, attempt, observation, payload and source).

NORMALIZATION (deterministic; no DNS, no network, no AI, no public-suffix list):

  Domain           lowercase; one trailing dot removed; ONE leading "www." label removed
                   when at least two labels remain ("www.Example.com." -> "example.com",
                   "www.com" is left alone). Every other subdomain is kept ("app.example.com"
                   and "example.com" are different identifiers). Must then be a valid hostname.
  Website URL      scheme and host lowercased; the default port (http 80, https 443) removed;
                   the fragment removed; an empty path becomes "/". Deliberately NOT collapsed:
                   http vs https, www vs no-www, trailing slashes on non-root paths, query
                   strings, path case: those can be genuinely different resources. IPv6/other
                   non-hostname hosts are unsupported.
  Company name     NEVER normalized into identity. normalize_name_for_blocking() exists only as
                   a search/blocking aid ("Acme", "Acme Inc." and "ACME" all block together);
                   equal blocking keys are NOT a match and never authorize anything.
"""

import re
import unicodedata
from enum import Enum
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field

from app.v2.domain.base import DomainModel
from app.v2.domain.candidate import IdentifierType, validate_candidate_name, validate_domain_name
from app.v2.domain.errors import InvalidInputError, UnsupportedInputError
from app.v2.domain.source import validate_source_url
from app.v2.domain.time import UtcDatetime

_HOST = re.compile(r"[a-z0-9.-]+")
_LEGAL_SUFFIXES = frozenset({"inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co", "company",
                             "gmbh", "ag", "sa", "plc", "lp", "llp"})


class CompanyNameRole(str, Enum):
    CANONICAL = "canonical"   # the name accepted when the company was created
    ALIAS = "alias"           # an additional name accepted when a candidate was attached


def normalize_domain(value: str) -> str:
    if not isinstance(value, str):
        raise InvalidInputError("invalid_domain", "domain must be a string")
    lowered = value.lower()
    if lowered.endswith("."):
        lowered = lowered[:-1]
    validate_domain_name(lowered)
    labels = lowered.split(".")
    if len(labels) > 2 and labels[0] == "www":
        lowered = ".".join(labels[1:])
    return lowered


def normalize_website_url(value: str) -> str:
    validate_source_url(value)
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if _HOST.fullmatch(host) is None or host.startswith(("-", ".")) or host.endswith(("-", ".")) or ".." in host:
        raise UnsupportedInputError("unsupported_url_host", "only ordinary hostnames are supported in website URLs")
    port = parts.port
    default = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default else f"{host}:{port}"
    query = f"?{parts.query}" if parts.query else ""
    return f"{scheme}://{netloc}{parts.path or '/'}{query}"


def normalize_identifier(identifier_type: IdentifierType, value: str) -> str:
    if identifier_type is IdentifierType.DOMAIN:
        return normalize_domain(value)
    return normalize_website_url(value)


def normalize_name_for_blocking(name: str) -> str:
    """A SEARCH AID ONLY. Two names with the same key are not the same company."""
    folded = unicodedata.normalize("NFKC", validate_candidate_name(name)).casefold()
    tokens = [t for t in re.sub(r"[^\w]+", " ", folded).split() if t not in _LEGAL_SUFFIXES]
    return " ".join(tokens)


class StoredCompany(DomainModel):
    """The whole canonical identity row: an opaque id and when it was created."""

    id: UUID
    created_at: UtcDatetime


class StoredCompanyName(DomainModel):
    id: int = Field(gt=0)
    company_id: UUID
    name: str
    name_role: CompanyNameRole
    resolution_decision_id: int = Field(gt=0)   # provenance: the decision that accepted this name
    created_at: UtcDatetime


class StoredCompanyIdentifier(DomainModel):
    id: int = Field(gt=0)
    company_id: UUID
    identifier_type: IdentifierType
    identifier_value: str                        # the canonical (normalized) value
    resolution_decision_id: int = Field(gt=0)   # provenance: the decision that accepted it
    candidate_identifier_id: int = Field(gt=0)  # provenance: the proposed identifier (and its evidence)
    created_at: UtcDatetime


class LineageLink(DomainModel):
    """One accepted canonical fact traced back to the evidence it came from:
    fact -> ResolutionDecision -> CompanyCandidate -> ProcessingAttempt -> Observation -> RawPayload -> Source."""

    fact_kind: str   # "name" | "identifier"
    fact_id: int = Field(gt=0)
    company_id: UUID
    resolution_decision_id: int = Field(gt=0)
    candidate_id: int = Field(gt=0)
    processing_attempt_id: int = Field(gt=0)
    observation_id: int = Field(gt=0)
    content_hash: str
    source_id: int = Field(gt=0)
    source_key: str
