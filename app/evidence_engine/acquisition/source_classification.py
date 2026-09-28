"""
Deterministic source-type classification (Task 21 item 13).

**Source type must NOT be LLM-authoritative.** A page that itself says
"this is independent, verified reporting" does not thereby become
`INDEPENDENT_REPORTING` -- and a company's own domain does not become
independent merely because a compromised or credulous extractor asserts
it. This module is the ONE place `source_type` is assigned, and it looks
at exactly two things: the retrieved URL's registered domain, and the
company's own declared website URL's registered domain -- never the
page's own content, never anything an `EvidenceExtractor` proposed.
`RetrievedSource.source_type` (models.py) is always populated from THIS
function's return value, before any extraction call ever happens
(`providers_live.py::HttpSourceRetriever.retrieve` calls this directly);
`extraction.py::validate_candidate` structurally cannot override it,
because `ExtractedClaimCandidate` (Task 20) has no `source_type` field at
all -- a candidate cannot even ASSERT one, let alone have it accepted.

**Deliberately simple, deliberately conservative.** This is not a
general-purpose domain-reputation service. It answers exactly one
narrow question -- "is this URL the company's own domain, a known
public-filing/regulator domain, a known aggregator/directory, a known
open-community platform, or (the honest default) ordinary third-party
reporting" -- using a small, explicit, reviewable table rather than any
heuristic that could be gamed by a URL crafted to look official. A
domain not recognized by any specific rule below falls through to
`INDEPENDENT_REPORTING`, the same conservative default `SourceType`
already had before acquisition existed (a human pasting a news URL into
the legacy pipeline made exactly this same judgment call by hand).

**Known limitation, documented rather than silently assumed away:** this
uses a simple "last two DNS labels" heuristic for the registered domain,
not a full Public Suffix List. This is wrong for domains like
`company.co.uk` (whose registrable domain is `company.co.uk`, three
labels) -- a real production deployment should use a PSL-aware library
(e.g. `tldextract`, not currently a project dependency). Documented in
`PROVIDER_ADAPTERS_AND_CALL_BUDGET.md` as an assumption awaiting a real
run against non-`.com` company domains, not fixed here since it is not
exercised by any real or fictional fixture in this engine today.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from app.evidence_engine.models import SourceType

# Known public-filing / regulator domains. Deliberately a short, explicit
# list -- a domain NOT on this list is never assumed to be a filing
# source just because it looks official (e.g. contains "gov" as a
# substring); only an exact registered-domain match qualifies.
_PUBLIC_FILING_DOMAINS: frozenset[str] = frozenset({
    "sec.gov",
    "edgar.sec.gov",
    "companieshouse.gov.uk",
    "find-and-update.company-information.service.gov.uk",
    "europa.eu",
})

# Known aggregator/directory platforms -- third-party sites that compile
# structured company data, distinct from bylined independent reporting
# (spec's own SourceType taxonomy, models.py).
_AGGREGATOR_DOMAINS: frozenset[str] = frozenset({
    "crunchbase.com",
    "pitchbook.com",
    "g2.com",
    "capterra.com",
    "producthunt.com",
    "similarweb.com",
    "builtwith.com",
    "owler.com",
    "trustradius.com",
})

# Known open-community platforms with no identified author/editorial
# process for any given post (models.py's own COMMUNITY_COMMENTARY
# definition) -- independent of the company, but not attributable,
# bylined reporting.
_COMMUNITY_DOMAINS: frozenset[str] = frozenset({
    "reddit.com",
    "news.ycombinator.com",
    "quora.com",
    "stackoverflow.com",
    "stackexchange.com",
})

# Subdomain prefixes that, on the COMPANY'S OWN domain specifically,
# indicate product documentation rather than general company disclosure
# (models.py: PRODUCT_DOCUMENTATION is still the company's own words,
# just a different SourceType than COMPANY_DISCLOSURE for rubrics that
# distinguish "marketing claim" from "documented product surface").
_DOCUMENTATION_SUBDOMAIN_PREFIXES: tuple[str, ...] = ("docs.", "developer.", "developers.", "help.", "support.", "api.")


def _registered_domain(url: str) -> str:
    """Last two DNS labels of the URL's hostname, lowercased. See the
    module docstring's own "known limitation" note for what this gets
    wrong (multi-label public suffixes like .co.uk)."""
    host = (urlsplit(url).hostname or "").lower()
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    return ".".join(labels[-2:])


def _full_host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def classify_source_type(url: str, company_website_url: str) -> SourceType:
    """The one deterministic rule set. Order matters: company-domain
    checks run first, so a company that happens to also be listed as an
    "aggregator" domain (unlikely, but never assumed impossible) is still
    correctly classified as its own disclosure, not independent of
    itself."""
    company_domain = _registered_domain(company_website_url)
    url_domain = _registered_domain(url)
    full_host = _full_host(url)

    if company_domain and url_domain == company_domain:
        if any(full_host.startswith(prefix) for prefix in _DOCUMENTATION_SUBDOMAIN_PREFIXES):
            return SourceType.PRODUCT_DOCUMENTATION
        return SourceType.COMPANY_DISCLOSURE

    if url_domain in _PUBLIC_FILING_DOMAINS or full_host in _PUBLIC_FILING_DOMAINS:
        return SourceType.PUBLIC_FILING

    if url_domain in _AGGREGATOR_DOMAINS or full_host in _AGGREGATOR_DOMAINS:
        return SourceType.AGGREGATOR_OR_DIRECTORY

    if url_domain in _COMMUNITY_DOMAINS or full_host in _COMMUNITY_DOMAINS:
        return SourceType.COMMUNITY_COMMENTARY

    return SourceType.INDEPENDENT_REPORTING
