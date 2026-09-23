"""
A dedicated SEC Form D collector -- Increment 18.3. Deliberately NOT a general-purpose web scraper: it knows
exactly two things (fetch one Form D filing's primary_doc.xml by CIK+accession; search EDGAR's own full-text
search API, bounded, for candidate Form D filings to review), against a hard-coded allowlist of SEC hostnames,
and nothing else. This is the only module in app/v2/tools that performs network I/O; every downstream step
(ingest_evidence, the Form D proposers, candidate persistence, human resolution) is exactly the same
network-free, already-tested code from Increment 18.2, unmodified.

Architecture: app.v2.ingestion, app.v2.repositories, app.v2.candidates, app.v2.resolution,
app.v2.financing_resolution and app.v2.classification are all no_network_packages (see
app/v2/tests/architecture/boundary_rules.py) -- this module lives in app.v2.tools specifically because that
package carries no such restriction, and because collection needs to stay a clearly separate concern from the
deterministic evidence-storage core it feeds. It has no database handle: every function here returns bytes and
plain metadata; app.v2.tools.cli is what calls ingest_evidence with the result.

SECURITY (Increment 18.3's own explicit requirements):
  1. SEC-supported access: EDGAR's own documented archive URLs and its own documented full-text search API
     (efts.sec.gov) -- both public, free, no API key.
  2. User-Agent: REQUIRED, no default. SEC's own policy requires a real identifying User-Agent (name + contact);
     sending a generic or fake one risks the operator's IP being blocked. See COLLECTOR_USER_AGENT_ENV.
  3. Timeouts: a (connect, read) tuple on every request; see DEFAULT_TIMEOUT.
  4. Response-size limit: enforced WHILE STREAMING (the connection is aborted the moment the limit is exceeded),
     never by buffering an unbounded response and checking afterward.
  5. Bounded retries with exponential backoff on transient failures (connection errors, 5xx); Retry-After is
     read and respected (capped -- see MAX_RESPECTED_RETRY_AFTER_SECONDS) on 429/503; 4xx (other than 429) is
     never retried, since a retry cannot succeed.
  6. SSRF: the target hostname is checked against a hard-coded allowlist (SEC_HOSTS) before every single
     request (not just the first of a batch); the hostname is then resolved and EVERY resolved address is
     checked against `ipaddress` for private/loopback/link-local/multicast/reserved/unspecified ranges, refusing
     the request if any resolved address is not a global unicast address. Redirects are NEVER followed
     (allow_redirects=False) -- a 3xx from EDGAR for these specific, stable, known paths is unexpected, and
     refusing outright is simpler and safer than validating and following one.
  7. Only two URL shapes are ever constructed, both from validated inputs (CIK: digits only; accession: the
     exact NNNNNNNNNN-NN-NNNNNN shape) -- never a caller-supplied path or URL, which also rules out path
     injection into the constructed request.
  8. Only Form D primary documents are fetched (the collector constructs the EDGAR primary_doc.xml URL itself
     from CIK/accession; it does not fetch or follow anything else).
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

# ---------------------------------------------------------------- configuration

COLLECTOR_USER_AGENT_ENV = "VENTUREGPS_SEC_COLLECTOR_USER_AGENT"

SEC_ARCHIVE_HOST = "www.sec.gov"
SEC_FULL_TEXT_SEARCH_HOST = "efts.sec.gov"
ALLOWED_SEC_HOSTS = frozenset({SEC_ARCHIVE_HOST, SEC_FULL_TEXT_SEARCH_HOST})

DEFAULT_TIMEOUT = (10, 20)  # (connect_seconds, read_seconds)
MAX_RESPONSE_BYTES = 1024 * 1024  # 1 MiB -- matches app.v2.ingestion.service's own evidence size limit
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0
BACKOFF_MULTIPLIER = 2.0
MAX_RESPECTED_RETRY_AFTER_SECONDS = 120
MAX_DISCOVERY_RESULTS = 25  # a bound on "bounded batch collection" -- never an unbounded scrape

_CIK_RE = re.compile(r"[0-9]{1,10}")
_ACCESSION_RE = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}")


class CollectionError(Exception):
    """Base class for every way collection can fail. Static, non-sensitive messages only (no response bodies,
    no headers, no credentials) -- these are reported directly to a human via the CLI."""


class UnsafeTargetError(CollectionError):
    """The target host/address failed the SSRF allowlist or IP-safety check. Never reached for the two
    hard-coded SEC hosts under normal DNS; exists as a real, enforced check, not a formality."""


class RateLimitedError(CollectionError):
    """429/503 persisted past MAX_RETRIES, or Retry-After exceeded MAX_RESPECTED_RETRY_AFTER_SECONDS."""


class ResponseTooLargeError(CollectionError):
    """The response exceeded MAX_RESPONSE_BYTES while streaming; the connection was aborted immediately."""


class UpstreamError(CollectionError):
    """A non-retryable HTTP status, or retries were exhausted on a transient one."""


def require_user_agent() -> str:
    """No default: SEC's own policy requires a real identifying contact. Failing loudly here is deliberate --
    silently sending a generic User-Agent risks the operator's IP being rate-limited or blocked."""
    value = os.environ.get(COLLECTOR_USER_AGENT_ENV, "").strip()
    if not value or "@" not in value:
        raise CollectionError(
            f"{COLLECTOR_USER_AGENT_ENV} must be set to a real identifying User-Agent including contact "
            f'information (SEC\'s own policy), e.g. "VentureGPS Research (contact: you@example.com)"'
        )
    return value


def validate_cik(value: str) -> str:
    if not isinstance(value, str) or _CIK_RE.fullmatch(value) is None:
        raise CollectionError("CIK must be 1-10 digits")
    return value


def normalize_cik(value: str) -> str:
    """EDGAR's archive server 301-redirects a zero-padded CIK path segment to its canonical non-padded form
    (confirmed directly against the real server) -- this module refuses to follow ANY redirect (see the module
    docstring's SSRF/redirect policy), so the fix is to build the correct URL in the first place, not to permit
    that one redirect. Discovery (discover_form_d_filings) returns EDGAR's own zero-padded display form; this
    normalizes it before a URL is ever built. Never strips to an empty string: an all-zero input keeps one 0."""
    cik = validate_cik(value)
    return cik.lstrip("0") or "0"


def validate_accession(value: str) -> str:
    if not isinstance(value, str) or _ACCESSION_RE.fullmatch(value) is None:
        raise CollectionError("accession number must look like NNNNNNNNNN-NN-NNNNNN")
    return value


def form_d_primary_document_url(cik: str, accession: str) -> str:
    """The one URL shape this module fetches evidence from: EDGAR's own stable archive convention. Never built
    from a caller-supplied URL or path -- only from a validated, normalized CIK and a validated accession."""
    cik = normalize_cik(cik)
    accession = validate_accession(accession)
    accession_no_dashes = accession.replace("-", "")
    return f"https://{SEC_ARCHIVE_HOST}/Archives/edgar/data/{cik}/{accession_no_dashes}/primary_doc.xml"


# ---------------------------------------------------------------- SSRF guard

def _assert_safe_target(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UnsafeTargetError("only https is permitted")
    if parts.hostname not in ALLOWED_SEC_HOSTS:
        raise UnsafeTargetError("host is not on the SEC allowlist")
    if parts.port not in (None, 443):
        raise UnsafeTargetError("only the default https port is permitted")
    try:
        addrinfo = socket.getaddrinfo(parts.hostname, 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise UnsafeTargetError("could not resolve the target host") from exc
    for family, _type, _proto, _canon, sockaddr in addrinfo:
        raw_ip = sockaddr[0]
        try:
            addr = ipaddress.ip_address(raw_ip)
        except ValueError:
            raise UnsafeTargetError("resolved address is not a valid IP") from None
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved or addr.is_unspecified:
            raise UnsafeTargetError("resolved address is not a global unicast address")


# ---------------------------------------------------------------- fetch primitive

@dataclass(frozen=True)
class FetchResult:
    url: str
    content: bytes
    status_code: int
    fetched_at: datetime  # UTC, when this specific fetch completed


def _stream_bounded(response: requests.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            response.close()
            raise ResponseTooLargeError(f"response exceeded {MAX_RESPONSE_BYTES} bytes; aborted")
        chunks.append(chunk)
    return b"".join(chunks)


def _sleep_for_backoff(attempt: int, retry_after_header: str | None) -> None:
    if retry_after_header is not None:
        try:
            seconds = float(retry_after_header)
        except ValueError:
            seconds = INITIAL_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER ** attempt)
        if seconds > MAX_RESPECTED_RETRY_AFTER_SECONDS:
            raise RateLimitedError(f"Retry-After ({seconds:.0f}s) exceeds the {MAX_RESPECTED_RETRY_AFTER_SECONDS}s bound this tool will wait")
        time.sleep(seconds)
        return
    time.sleep(INITIAL_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER ** attempt))


def fetch(url: str, *, user_agent: str, params: dict[str, str] | None = None) -> FetchResult:
    """One SSRF-checked, timeout-bounded, size-bounded, retried GET. Never follows a redirect."""
    _assert_safe_target(url)
    headers = {"User-Agent": user_agent, "Accept-Encoding": "identity"}

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT, stream=True, allow_redirects=False)
        except requests.exceptions.Timeout as exc:
            last_error = UpstreamError("request timed out")
            _maybe_backoff_or_raise(attempt, last_error, exc)
            continue
        except requests.exceptions.ConnectionError as exc:
            last_error = UpstreamError("connection failed")
            _maybe_backoff_or_raise(attempt, last_error, exc)
            continue

        if response.is_redirect or 300 <= response.status_code < 400:
            response.close()
            raise UnsafeTargetError(f"refusing to follow a redirect (status {response.status_code})")

        if response.status_code == 429 or response.status_code == 503:
            retry_after = response.headers.get("Retry-After")
            response.close()
            if attempt == MAX_RETRIES - 1:
                raise RateLimitedError(f"rate limited (status {response.status_code}) after {MAX_RETRIES} attempts")
            _sleep_for_backoff(attempt, retry_after)
            continue

        if 500 <= response.status_code < 600:
            response.close()
            last_error = UpstreamError(f"upstream server error (status {response.status_code})")
            if attempt == MAX_RETRIES - 1:
                raise last_error
            _sleep_for_backoff(attempt, None)
            continue

        if response.status_code != 200:
            response.close()  # never retried; never reads the body of a non-200 we won't use
            raise UpstreamError(f"unexpected status {response.status_code}")

        content = _stream_bounded(response)
        return FetchResult(url=response.url, content=content, status_code=response.status_code, fetched_at=datetime.now(timezone.utc))

    raise last_error or UpstreamError("request failed for an unknown reason")


def _maybe_backoff_or_raise(attempt: int, error: Exception, cause: Exception) -> None:
    if attempt == MAX_RETRIES - 1:
        raise error from cause
    _sleep_for_backoff(attempt, None)


# ---------------------------------------------------------------- Form D collection

@dataclass(frozen=True)
class CollectedFiling:
    cik: str
    accession: str
    url: str
    content: bytes
    fetched_at: datetime


def collect_form_d_filing(cik: str, accession: str, *, user_agent: str | None = None) -> CollectedFiling:
    """Fetch one Form D primary_doc.xml. Returns the exact, unmodified bytes -- this function does not parse,
    validate as Form D, or touch the database; app.v2.tools.form_d_xml / the CLI's ingest step do that,
    unchanged from Increment 18.2."""
    agent = user_agent or require_user_agent()
    url = form_d_primary_document_url(cik, accession)
    result = fetch(url, user_agent=agent)
    return CollectedFiling(cik=cik, accession=accession, url=url, content=result.content, fetched_at=result.fetched_at)


# ---------------------------------------------------------------- bounded discovery (EDGAR's own full-text search)

@dataclass(frozen=True)
class DiscoveredFiling:
    cik: str
    accession: str
    display_name: str
    file_date: str


def discover_form_d_filings(query: str, *, user_agent: str | None = None, max_results: int = MAX_DISCOVERY_RESULTS) -> list[DiscoveredFiling]:
    """A BOUNDED search against EDGAR's own full-text search API (efts.sec.gov), restricted to Form D
    (`forms=D`). Never collects anything itself -- returns a capped list for a human (or collect_form_d_batch,
    which still reports each one individually) to act on. This is discovery, not a general search client: the
    query is passed through as one parameter to one specific, SEC-documented endpoint, nothing else."""
    if max_results > MAX_DISCOVERY_RESULTS:
        raise CollectionError(f"max_results may not exceed {MAX_DISCOVERY_RESULTS} (bounded batch collection, not a scrape)")
    agent = user_agent or require_user_agent()
    url = f"https://{SEC_FULL_TEXT_SEARCH_HOST}/LATEST/search-index"
    result = fetch(url, user_agent=agent, params={"q": query, "forms": "D"})
    try:
        import json
        payload = json.loads(result.content)
        hits = payload["hits"]["hits"]
    except (ValueError, KeyError, TypeError) as exc:
        raise UpstreamError("unexpected response shape from SEC full-text search") from exc

    discovered: list[DiscoveredFiling] = []
    for hit in hits[:max_results]:
        source = hit.get("_source", {})
        ciks = source.get("ciks") or []
        adsh = source.get("adsh")
        if not ciks or not adsh:
            continue
        display_names = source.get("display_names") or [""]
        discovered.append(DiscoveredFiling(cik=ciks[0], accession=adsh, display_name=display_names[0], file_date=source.get("file_date", "")))
    return discovered
