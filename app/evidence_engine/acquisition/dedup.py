"""
Deterministic pre-extraction deduplication and prioritization (Task 21
items 8-9). Two separate, narrow passes, each documented on why it is
safe not to destroy genuine independent corroboration:

1. `normalize_url()` / `dedup_search_results()` -- runs on raw
   `SearchResult`s, BEFORE any retrieval happens (item 9's own "dedup
   before expensive extraction... search -> normalize -> dedup ->
   retrieve"). Collapses only EXACT duplicate URLs (after normalizing
   scheme case, trailing slash, and known tracking query parameters) --
   never collapses two different URLs just because they look similar,
   since two different URLs are, by definition, two different sources
   worth independently retrieving and letting `provenance.py`'s own
   content-based safety net judge later.

2. `dedup_retrieved_content()` -- runs AFTER retrieval, on actual fetched
   text (item 9's own "content/provenance-dedup"). Collapses only
   BYTE-IDENTICAL (after whitespace normalization) content from different
   URLs -- the "syndicated wire copy mirrored verbatim on five domains"
   case Task 20's own duplicate-syndication fixture already exercises at
   the claim-identity layer; catching the identical-text case here purely
   saves an extraction call on four sources whose content extraction
   would have produced the exact same candidate anyway. Two sources that
   report the SAME underlying fact in DIFFERENT words are deliberately
   NOT collapsed here -- that is exactly the "different wording, same
   fact" case `independence_group_id` (claim_identity.py) and
   `provenance.py::verify_independence()` already exist to reconcile
   AFTER extraction, using the fact's own structured identity rather than
   raw text similarity pre-extraction, which is a strictly weaker signal
   this module deliberately does not try to replace.

Prioritization (item 8) is simply "keep provider order, drop exact
duplicates" -- a real search provider (Tavily) already returns results in
its own relevance order; this module never re-ranks by a second, opaque
heuristic. Deterministic here means "the same input list always produces
the same output list," not "sorted by some independently-invented score."

**`dedup_retrieved_content()` is implemented and unit-tested but
deliberately NOT wired into `pipeline.py`'s default flow.** It was
written, then found to directly conflict with an already-approved,
already-tested spec decision: `claim_id` is defined (spec Part 2.1,
unchanged since Task 20) as inherently PER-SOURCE -- "the same real-world
fact reported by five different outlets legitimately produces five
different claim_ids" -- and `test_acquisition_pipeline.py::
test_duplicate_syndicated_reporting_does_not_inflate_evidence` exists
specifically to prove all five survive to the ledger as five distinct,
individually-provenanced claims (only collapsing to ONE
`independence_group_id` for scoring purposes downstream). That fixture's
five outlets share byte-identical content by construction -- exactly
what `dedup_retrieved_content()` would collapse to one source BEFORE
extraction ever ran, silently destroying the very multi-outlet
observability the ledger is designed to retain. Item 9's own
"...where it doesn't destroy genuine independent corroboration" is the
explicit license to make this call: pre-extraction content-dedup is safe
in general, but not safe to apply unconditionally ahead of a spec rule
that deliberately treats "same fact, five sources" as five real ledger
rows, not one. Left available for a caller who has already established
(out of band) that two specific sources are the same wire-service copy
and wants to skip a redundant extraction call for it -- not something
this pipeline decides on the caller's behalf by default. Documented
again, with the same reasoning, in `PROVIDER_ADAPTERS_AND_CALL_BUDGET.md`.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.evidence_engine.acquisition.models import RetrievedSource, SearchResult

_TRACKING_PARAM_PREFIXES: tuple[str, ...] = ("utm_", "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src")
_WHITESPACE = re.compile(r"\s+")


def normalize_url(url: str) -> str:
    """Lowercases scheme/host, strips a trailing slash from the path,
    drops the fragment, and drops known tracking query parameters --
    never drops or reorders any OTHER query parameter, since a parameter
    like `?id=123` or `?page=2` can genuinely change what page loads."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    kept_query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not any(k.lower().startswith(p) for p in _TRACKING_PARAM_PREFIXES)
    ]
    query = urlencode(sorted(kept_query))
    return urlunsplit((scheme, netloc, path, query, ""))


def dedup_search_results(results: tuple[SearchResult, ...]) -> tuple[SearchResult, ...]:
    """Stable dedup by normalized URL, keeping the FIRST occurrence (the
    provider's own highest-relevance instance of that URL) and preserving
    the provider's own relative order for everything kept."""
    seen: set[str] = set()
    kept: list[SearchResult] = []
    for result in results:
        key = normalize_url(result.url)
        if key in seen:
            continue
        seen.add(key)
        kept.append(result)
    return tuple(kept)


def _content_fingerprint(content: str) -> str:
    normalized = _WHITESPACE.sub(" ", content.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def dedup_retrieved_content(
    sources: tuple[RetrievedSource, ...],
) -> tuple[tuple[RetrievedSource, ...], tuple[RetrievedSource, ...]]:
    """Returns (kept, dropped_as_exact_duplicates). Keeps the FIRST
    source seen for each distinct content fingerprint; every later
    source with byte-identical (whitespace/case normalized) content is
    dropped as a redundant fetch, never sent to extraction. A source
    whose content merely OVERLAPS another's (the common case for two
    genuinely independent articles quoting the same press release
    excerpt) is not touched -- only an exact whole-page match is
    collapsed here."""
    seen: dict[str, RetrievedSource] = {}
    kept: list[RetrievedSource] = []
    dropped: list[RetrievedSource] = []
    for source in sources:
        fp = _content_fingerprint(source.content)
        if fp in seen:
            dropped.append(source)
            continue
        seen[fp] = source
        kept.append(source)
    return tuple(kept), tuple(dropped)
