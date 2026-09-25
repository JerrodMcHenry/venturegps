"""
Website / URL Ingestion: fetches and extracts the visible text content of a
company website so it can enter the SAME canonical SIE pipeline
(run_due_diligence) that company_text/PDF input already goes through --
this module only produces plain text, it never touches scoring, evidence,
or persistence.

SECURITY -- this function accepts a URL from an untrusted end user and
fetches it server-side, which is a textbook SSRF (Server-Side Request
Forgery) vector: without safeguards, a user could point it at
http://169.254.169.254/ (a cloud metadata endpoint), http://localhost:5432,
an internal admin panel, etc. This module closes that off in layers:

1. Only http/https schemes are accepted (no file://, gopher://, ...).
2. The hostname is DNS-resolved and every candidate address must be a
   public, routable address -- private (RFC1918), loopback, link-local
   (which also covers the 169.254.169.254 cloud metadata address),
   multicast, reserved, unspecified, and IPv4-mapped-IPv6 wrappers around
   any of the above are all rejected. Every surviving public address from
   that ONE resolution (IPv4 preferred, bounded count) is a legal
   candidate -- see _resolve_validated_ips().
3. The actual HTTP connection is pinned to one validated IP address at a
   time (rather than handing the hostname to the HTTP client and letting
   it resolve DNS again on its own). This is what actually closes the DNS
   rebinding gap: a hostname whose DNS record returns a public IP at
   validation time and a private/internal IP moments later (at the time
   the HTTP client would normally connect) would otherwise sail through a
   naive "validate the URL, then fetch the URL" check. TLS certificate
   validation still checks against the real hostname (assert_hostname /
   server_hostname below), so pinning the socket doesn't weaken it. If a
   given candidate can't be CONNECTED to at all, _fetch_validated() falls
   back to the next already-validated candidate from the same resolution
   -- never a new, unvalidated address, and never in response to an HTTP
   error or content rejection (see its own comment).
4. Redirects are NOT auto-followed by the HTTP client. Each hop's target
   URL is independently re-validated and re-pinned via the same path as
   the original URL, up to a bounded number of hops -- an allowed URL
   redirecting to a disallowed one is caught, not silently followed.
5. The response body is read as a bounded stream with a hard size cap,
   so a huge or slow-drip response can't exhaust memory.
6. A short, fixed per-request timeout bounds how long a single hop can
   hang.

No new dependency was added for this -- urllib3 (already installed as a
requests dependency) exposes the pinning primitives directly, and
ipaddress/socket/urllib.parse are all standard library.
"""

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import urllib3
from bs4 import BeautifulSoup

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB -- generous for a marketing/product page's HTML
REQUEST_TIMEOUT_SECONDS = 10
# Bounded fallback (Portfolio Release -- IPv6/IPv4 address-selection fix):
# a hostname's DNS answer is rarely more than a couple of A/AAAA records;
# 4 is generous headroom while still bounding worst-case per-URL latency
# if several resolved addresses are unreachable-but-slow-to-fail rather
# than promptly refused (see _resolve_validated_ips()'s own docstring).
MAX_ADDRESS_ATTEMPTS = 4
_DISALLOWED_HOSTNAME_SUFFIXES = (".local",)
_DISALLOWED_HOSTNAMES = {"localhost", "localhost.localdomain"}
# Content-Types that are clearly not a webpage -- rejected up front rather
# than spending the size-capped read on something BeautifulSoup can't
# usefully extract text from anyway.
_DISALLOWED_CONTENT_TYPE_PREFIXES = (
    "image/",
    "video/",
    "audio/",
    "application/octet-stream",
    "application/pdf",
    "application/zip",
    "font/",
)


class WebsiteFetchError(ValueError):
    """
    A deliberate, safe-to-display failure fetching or validating a
    website URL -- every message raised as this (or plain ValueError, its
    parent) anywhere in this module is written to be shown to the end
    user as-is, the same contract app/pdf_extractor.py already follows
    for its own ValueErrors.
    """


def _is_public_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)

    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        # ::ffff:a.b.c.d embeds an IPv4 address inside an IPv6 literal --
        # validate the embedded address, not the IPv6 wrapper around it,
        # so an IPv4-mapped loopback/private address can't slip past the
        # checks below just because they're written against ip.is_private
        # etc. on the outer (IPv6) object.
        ip = ip.ipv4_mapped

    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # covers 169.254.0.0/16, i.e. cloud metadata too
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_scheme_and_hostname(url: str) -> str:
    """Validates scheme + hostname shape only (no network I/O). Returns
    the hostname on success; raises WebsiteFetchError otherwise."""
    parts = urlsplit(url)

    if parts.scheme not in ALLOWED_SCHEMES:
        raise WebsiteFetchError("Only http and https website URLs are supported.")

    hostname = parts.hostname

    if not hostname:
        raise WebsiteFetchError("That doesn't look like a valid website URL.")

    lowered = hostname.lower()

    if lowered in _DISALLOWED_HOSTNAMES or lowered.endswith(_DISALLOWED_HOSTNAME_SUFFIXES):
        raise WebsiteFetchError("That website URL cannot be analyzed.")

    return hostname


def _resolve_validated_ips(hostname: str) -> list[str]:
    """
    DNS-resolves hostname and returns every distinct address confirmed
    public -- IPv4 addresses first, each family kept in the order DNS
    returned it, capped at MAX_ADDRESS_ATTEMPTS. Raises WebsiteFetchError
    if resolution fails or every resolved address is private/internal.

    Portfolio Release -- IPv6/IPv4 address-selection fix (GitHub Actions
    run #5): the previous version collected addresses into a `set` and
    returned an arbitrary one of them (Python's hash-randomized set
    iteration order, not DNS preference or reachability). On a host that
    resolves to both an IPv4 and an IPv6 address, that could -- and, in
    CI, reproducibly did -- pick an address this process has no outbound
    route to at all (GitHub-hosted runners have no IPv6 route), failing
    the whole fetch even though a perfectly reachable IPv4 address was
    also right there in the same DNS answer.
    `dict.fromkeys(...)` dedupes while preserving getaddrinfo()'s own
    answer order (a real, if implementation-dependent, ordering) instead
    of discarding it into a hash-random set; the stable sort below then
    moves every IPv4 address ahead of every IPv6 address without
    reordering within either family. The caller (_fetch_validated) tries
    these, in this order, one at a time, falling back to the next only on
    a genuine connection failure -- see its own comment for why that is
    safe and doesn't touch anything not already validated right here.
    """
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise WebsiteFetchError(
            "That website's address could not be resolved. Please check the URL."
        )

    resolved_ips = list(dict.fromkeys(info[4][0] for info in addr_infos))
    public_ips = [ip for ip in resolved_ips if _is_public_ip(ip)]

    if not public_ips:
        raise WebsiteFetchError(
            "That website URL cannot be analyzed because it points to a "
            "private or internal network address."
        )

    public_ips.sort(key=lambda ip: isinstance(ipaddress.ip_address(ip), ipaddress.IPv6Address))

    return public_ips[:MAX_ADDRESS_ATTEMPTS]


def _read_bounded(response: urllib3.HTTPResponse, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0

    for chunk in response.stream(8192, decode_content=True):
        total += len(chunk)

        if total > max_bytes:
            raise WebsiteFetchError(
                "That website's response was too large to analyze."
            )

        chunks.append(chunk)

    return b"".join(chunks)


def _fetch_validated(url: str, redirects_remaining: int) -> bytes:
    hostname = _validate_scheme_and_hostname(url)
    resolved_ips = _resolve_validated_ips(hostname)

    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    request_path = parts.path or "/"
    if parts.query:
        request_path = f"{request_path}?{parts.query}"

    pool_kwargs = {"timeout": REQUEST_TIMEOUT_SECONDS, "retries": False}

    if parts.scheme == "https":
        pool_cls = urllib3.HTTPSConnectionPool
        # Pin the TCP connection to the pre-validated IP (host below)
        # while still validating the TLS certificate against the real
        # hostname -- this is the piece that closes the DNS-rebinding
        # gap without weakening certificate verification. Computed once
        # from the real hostname and reused unchanged for every candidate
        # IP tried below -- which pinned address the socket happens to
        # use never affects what the certificate is checked against.
        pool_kwargs.update(
            assert_hostname=hostname,
            server_hostname=hostname,
            cert_reqs="CERT_REQUIRED",
        )
    else:
        pool_cls = urllib3.HTTPConnectionPool

    # Bounded fallback (Portfolio Release -- IPv6/IPv4 address-selection
    # fix): try each pre-validated, pre-filtered public candidate in turn
    # (resolved_ips is already IPv4-first, capped at MAX_ADDRESS_ATTEMPTS
    # -- see _resolve_validated_ips()), committing to the first one that
    # actually connects. Every candidate already passed the exact same
    # public-address check a single-candidate design would have applied;
    # nothing new is validated, accepted, or resolved mid-loop, and
    # urllib3 is only ever given an IP literal as `host` here -- never the
    # hostname -- so it can never perform its own independent DNS
    # resolution or connect anywhere outside this pre-approved list. Only
    # a CONNECTION-level failure (TCP connect / TLS handshake / connect
    # timeout -- urllib3.exceptions.HTTPError raised directly by
    # pool.request() below) advances to the next candidate; once
    # pool.request() returns a response at all, that candidate is final --
    # an HTTP error status, a disallowed content type, an oversized body,
    # or a bad redirect target are handled entirely below this loop and
    # are never retried against a different address (those are decisions
    # about what the reached server said, not about whether it was
    # reachable).
    pool = None
    response = None

    for candidate_ip in resolved_ips:
        candidate_pool = pool_cls(candidate_ip, port, **pool_kwargs)

        try:
            response = candidate_pool.request(
                "GET",
                request_path,
                headers={"User-Agent": "Mozilla/5.0", "Host": hostname},
                preload_content=False,
                redirect=False,
            )
            pool = candidate_pool
            break
        except urllib3.exceptions.HTTPError:
            candidate_pool.close()
            continue

    if pool is None or response is None:
        raise WebsiteFetchError(
            "Could not reach that website. Please check the URL and try again."
        )

    try:
        try:
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")

                if not location:
                    raise WebsiteFetchError(
                        "That website redirected without a valid destination."
                    )

                if redirects_remaining <= 0:
                    raise WebsiteFetchError(
                        "That website redirected too many times."
                    )

                next_url = urljoin(url, location)
                # Re-enter from the top: the redirect target gets the
                # exact same scheme/hostname/DNS/pinning validation as
                # the original URL, not a weaker "trust it" pass-through.
                return _fetch_validated(next_url, redirects_remaining - 1)

            if response.status != 200:
                raise WebsiteFetchError(
                    f"That website returned an error (HTTP {response.status})."
                )

            content_type = (response.headers.get("Content-Type") or "").lower()
            if content_type.startswith(_DISALLOWED_CONTENT_TYPE_PREFIXES):
                raise WebsiteFetchError(
                    "That URL doesn't point to a readable webpage."
                )

            return _read_bounded(response, MAX_RESPONSE_BYTES)
        finally:
            response.release_conn()
    finally:
        pool.close()


def extract_text_from_website(url: str) -> str:
    try:
        body = _fetch_validated(url, MAX_REDIRECTS)
    except WebsiteFetchError:
        raise
    except urllib3.exceptions.HTTPError:
        raise WebsiteFetchError(
            "Could not reach that website. Please check the URL and try again."
        )
    except socket.timeout:
        raise WebsiteFetchError("That website took too long to respond.")

    soup = BeautifulSoup(body, "html.parser")

    # Remove junk
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ")

    cleaned_text = " ".join(text.split())

    if not cleaned_text:
        raise WebsiteFetchError("No readable content found on website.")

    return cleaned_text
