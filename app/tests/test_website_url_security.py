"""
Regression/security tests for Website / URL Ingestion (app/website_scrapper.py
and WebsiteAnalysisRequest in app/models/startup.py).

These exercise the SSRF-hardening layer directly: scheme allow-listing,
private/loopback/link-local/metadata-address rejection, DNS-rebinding-safe
IP pinning, bounded redirects with per-hop re-validation, and bounded
response size. Two cases (valid public HTTP/HTTPS URL) make a real,
outbound network call to https://example.com/ (IANA's dedicated
example-content domain -- stable, no auth, tiny response) since that's the
only way to prove the full fetch-and-pin path actually reaches a real
public site end to end; every other case is fully offline and
deterministic (private-network/scheme rejection short-circuits before any
network I/O, and the redirect/oversized-response/fallback cases fake DNS
resolution and/or the connection pool rather than touching the network).

Portfolio Release -- IPv6/IPv4 address-selection fix (GitHub Actions run
#5): example.com resolves to both an IPv4 and an IPv6 address, and the
previous _resolve_validated_ip() picked one of them via a hash-randomized
Python `set` -- on a GitHub-hosted runner (no outbound IPv6 route) it
could, and reproducibly did, pick the unreachable IPv6 one, failing both
"valid public URL" cases above even though example.com's IPv4 address was
right there and perfectly reachable. _resolve_validated_ips() (plural) now
returns every public candidate IPv4-first, deterministically, and
_fetch_validated() falls back to the next one only on a genuine connection
failure -- which, as a direct consequence, also makes the two real-network
cases above reliably succeed via IPv4 on any runner with only IPv4 egress,
without needing to fake them out. The five test_ipv6_.../test_.../
test_fallback_... cases below add fully offline, deterministic coverage of
that new selection/fallback logic itself (fake socket.getaddrinfo() +
fake connection pool, same technique test_redirect_to_private_destination_
rejected already established) -- unreachable-IPv6-with-reachable-IPv4,
every candidate unreachable, mixed public/private DNS answers, all-private
DNS answers, and no-retry-on-an-HTTP-error-status.

Run with:
    python -m app.tests.test_website_url_security
"""

from pydantic import ValidationError

import app.website_scrapper as ws
from app.models.startup import WebsiteAnalysisRequest
from app.website_scrapper import WebsiteFetchError, extract_text_from_website


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_rejected(url: str, message_substring: str = "") -> None:
    try:
        extract_text_from_website(url)
    except WebsiteFetchError as error:
        if message_substring:
            expect(
                message_substring.lower() in str(error).lower(),
                f"Expected rejection message to mention {message_substring!r}, "
                f"got {error!r}",
            )
        return

    raise AssertionError(f"Expected {url!r} to be rejected, but it was accepted.")


def test_valid_public_https_url_is_fetched() -> None:
    text = extract_text_from_website("https://example.com")
    expect(len(text) > 0, "Expected non-empty text from a real public HTTPS site.")


def test_valid_public_http_url_is_fetched() -> None:
    text = extract_text_from_website("http://example.com")
    expect(len(text) > 0, "Expected non-empty text from a real public HTTP site.")


def test_localhost_rejected() -> None:
    expect_rejected("http://localhost:8000/")


def test_loopback_ip_rejected() -> None:
    expect_rejected("http://127.0.0.1/", "private or internal")


def test_private_ipv4_rejected() -> None:
    for host in ("http://10.0.0.5/", "http://172.16.0.5/", "http://192.168.1.1/"):
        expect_rejected(host, "private or internal")


def test_link_local_and_metadata_rejected() -> None:
    # 169.254.169.254 is the AWS/GCP/Azure cloud metadata endpoint -- the
    # single highest-value SSRF target this guard exists to stop.
    expect_rejected("http://169.254.169.254/latest/meta-data/", "private or internal")


def test_non_http_scheme_rejected() -> None:
    for url in ("file:///etc/passwd", "ftp://example.com/", "gopher://example.com/"):
        expect_rejected(url, "http and https")


def test_malformed_url_rejected() -> None:
    expect_rejected("not a url")
    expect_rejected("http://")


def test_redirect_to_private_destination_rejected() -> None:
    """A URL that validates fine on its own but redirects to a private
    address must still be rejected -- the redirect target gets the exact
    same validation as the original URL, not a blind follow. Faked at the
    connection-pool level (not the network) so this is deterministic; the
    rejection itself is real, unmocked _resolve_validated_ips logic. Uses
    a public IP literal (8.8.8.8) as the "origin" so no real DNS lookup
    is needed to reach the fake redirect response.
    """

    class _FakeResponse:
        def __init__(self, status: int, headers: dict) -> None:
            self.status = status
            self.headers = headers

        def stream(self, chunk_size, decode_content=True):
            return iter([])

        def release_conn(self) -> None:
            pass

    class _FakeRedirectPool:
        def __init__(self, host, port, **kwargs) -> None:
            pass

        def request(self, method, path, headers=None, preload_content=None, redirect=None):
            return _FakeResponse(302, {"Location": "http://169.254.169.254/"})

        def close(self) -> None:
            pass

    original_http_pool = ws.urllib3.HTTPConnectionPool
    original_https_pool = ws.urllib3.HTTPSConnectionPool

    ws.urllib3.HTTPConnectionPool = _FakeRedirectPool
    ws.urllib3.HTTPSConnectionPool = _FakeRedirectPool

    try:
        expect_rejected("http://8.8.8.8/", "private or internal")
    finally:
        ws.urllib3.HTTPConnectionPool = original_http_pool
        ws.urllib3.HTTPSConnectionPool = original_https_pool


def test_oversized_response_rejected() -> None:
    class _FakeOversizedResponse:
        def stream(self, chunk_size, decode_content=True):
            remaining = ws.MAX_RESPONSE_BYTES + 1
            while remaining > 0:
                take = min(chunk_size, remaining)
                yield b"x" * take
                remaining -= take

    try:
        ws._read_bounded(_FakeOversizedResponse(), ws.MAX_RESPONSE_BYTES)
    except WebsiteFetchError:
        return

    raise AssertionError("Expected an oversized response to be rejected.")


class _FakeTextResponse:
    """A minimal urllib3.HTTPResponse stand-in: 200 text/html with a fixed body."""

    def __init__(self, body: bytes) -> None:
        self.status = 200
        self.headers = {"Content-Type": "text/html"}
        self._body = body

    def stream(self, chunk_size, decode_content=True):
        return iter([self._body])

    def release_conn(self) -> None:
        pass


def _patched_getaddrinfo(fake_addr_infos):
    """Context manager-free monkeypatch of socket.getaddrinfo, restored by
    the caller's own finally block -- same manual-patch style every other
    test in this file already uses for urllib3.HTTP(S)ConnectionPool."""
    original = ws.socket.getaddrinfo
    ws.socket.getaddrinfo = lambda host, port: fake_addr_infos
    return original


def test_resolve_validated_ips_prefers_ipv4_deterministically() -> None:
    """_resolve_validated_ips() must put every IPv4 candidate ahead of
    every IPv6 candidate regardless of the order DNS returned them in --
    proven directly, no network or connection pool involved at all."""
    fake_ipv4 = "8.8.8.10"
    fake_ipv6 = "2606:4700:10::1"

    original_getaddrinfo = _patched_getaddrinfo(
        [
            (ws.socket.AF_INET6, ws.socket.SOCK_STREAM, 6, "", (fake_ipv6, 0, 0, 0)),
            (ws.socket.AF_INET, ws.socket.SOCK_STREAM, 6, "", (fake_ipv4, 0)),
        ]
    )

    try:
        candidates = ws._resolve_validated_ips("ipv6-first.example.test")
        expect(
            candidates == [fake_ipv4, fake_ipv6],
            f"Expected IPv4 before IPv6 regardless of DNS answer order, got {candidates}",
        )
    finally:
        ws.socket.getaddrinfo = original_getaddrinfo


def test_resolve_validated_ips_bounded_by_max_address_attempts() -> None:
    """More resolved public addresses than MAX_ADDRESS_ATTEMPTS must never
    all be returned -- the candidate list, and therefore the number of
    connection attempts _fetch_validated() can ever make, is bounded."""
    many_fake_ips = [f"8.8.8.{i}" for i in range(1, 20)]
    fake_addr_infos = [
        (ws.socket.AF_INET, ws.socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in many_fake_ips
    ]

    original_getaddrinfo = _patched_getaddrinfo(fake_addr_infos)

    try:
        candidates = ws._resolve_validated_ips("many-addresses.example.test")
        expect(
            len(candidates) == ws.MAX_ADDRESS_ATTEMPTS,
            f"Expected exactly MAX_ADDRESS_ATTEMPTS ({ws.MAX_ADDRESS_ATTEMPTS}) candidates, got {len(candidates)}",
        )
    finally:
        ws.socket.getaddrinfo = original_getaddrinfo


def test_mixed_public_and_private_dns_results_keeps_only_public_candidates() -> None:
    """A hostname resolving to a mix of public and private addresses must
    end up with ONLY the public one(s) as connection candidates -- proven
    two ways: the returned candidate list itself, and (via a fake pool)
    that the private address is never actually dialed."""
    fake_public_ip = "8.8.8.20"
    fake_private_ip = "10.1.2.3"

    original_getaddrinfo = _patched_getaddrinfo(
        [
            (ws.socket.AF_INET, ws.socket.SOCK_STREAM, 6, "", (fake_private_ip, 0)),
            (ws.socket.AF_INET, ws.socket.SOCK_STREAM, 6, "", (fake_public_ip, 0)),
        ]
    )

    try:
        candidates = ws._resolve_validated_ips("mixed-public-private.example.test")
        expect(
            candidates == [fake_public_ip],
            f"Expected only the public address as a candidate, got {candidates}",
        )
    finally:
        ws.socket.getaddrinfo = original_getaddrinfo

    attempted_hosts: list[str] = []

    class _FakePool:
        def __init__(self, host, port, **kwargs) -> None:
            self.host = host

        def request(self, method, path, headers=None, preload_content=None, redirect=None):
            attempted_hosts.append(self.host)
            return _FakeTextResponse(b"public site body")

        def close(self) -> None:
            pass

    original_getaddrinfo = _patched_getaddrinfo(
        [
            (ws.socket.AF_INET, ws.socket.SOCK_STREAM, 6, "", (fake_private_ip, 0)),
            (ws.socket.AF_INET, ws.socket.SOCK_STREAM, 6, "", (fake_public_ip, 0)),
        ]
    )
    original_https_pool = ws.urllib3.HTTPSConnectionPool
    ws.urllib3.HTTPSConnectionPool = _FakePool

    try:
        text = extract_text_from_website("https://mixed-public-private.example.test/")
        expect(text == "public site body", f"Expected the public candidate's body, got {text!r}")
        expect(
            fake_private_ip not in attempted_hosts,
            f"The private candidate must never be connected to, but it was: {attempted_hosts}",
        )
        expect(
            attempted_hosts == [fake_public_ip],
            f"Expected exactly one connection attempt, to the public candidate only, got {attempted_hosts}",
        )
    finally:
        ws.socket.getaddrinfo = original_getaddrinfo
        ws.urllib3.HTTPSConnectionPool = original_https_pool


def test_all_private_dns_results_rejected() -> None:
    """A hostname resolving ONLY to private/link-local addresses must be
    rejected before any connection is ever attempted -- not merely
    rejected eventually; the fake pool below asserts it is never even
    constructed."""
    original_getaddrinfo = _patched_getaddrinfo(
        [
            (ws.socket.AF_INET, ws.socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
            (ws.socket.AF_INET, ws.socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0)),
        ]
    )

    class _PoolThatMustNeverBeConstructed:
        def __init__(self, host, port, **kwargs) -> None:
            raise AssertionError(
                f"A connection pool must never be constructed for an all-private DNS result, "
                f"but one was attempted for {host!r}"
            )

    original_https_pool = ws.urllib3.HTTPSConnectionPool
    ws.urllib3.HTTPSConnectionPool = _PoolThatMustNeverBeConstructed

    try:
        expect_rejected("https://all-private.example.test/", "private or internal")
    finally:
        ws.socket.getaddrinfo = original_getaddrinfo
        ws.urllib3.HTTPSConnectionPool = original_https_pool


def test_ipv6_unreachable_ipv4_reachable_falls_back_to_ipv4() -> None:
    """
    The core case this fix exists for (GitHub Actions run #5): a hostname
    resolving to one unreachable IPv6 address and one reachable IPv4
    address must still succeed, by falling back to the IPv4 candidate --
    fully offline and deterministic, no real network or DNS involved.
    """
    fake_ipv4 = "8.8.8.30"
    fake_ipv6 = "2606:4700:10::30"
    attempted_hosts: list[str] = []

    class _FakeFallbackPool:
        def __init__(self, host, port, **kwargs) -> None:
            self.host = host

        def request(self, method, path, headers=None, preload_content=None, redirect=None):
            attempted_hosts.append(self.host)

            if self.host == fake_ipv6:
                # The exact exception class app/website_scrapper.py's
                # fallback loop watches for -- a connection-level failure,
                # simulating "GitHub-hosted runner, no outbound IPv6 route".
                raise ws.urllib3.exceptions.NewConnectionError(
                    None, "simulated: no outbound IPv6 route"
                )

            return _FakeTextResponse(b"ipv4 fallback body")

        def close(self) -> None:
            pass

    original_getaddrinfo = _patched_getaddrinfo(
        [
            (ws.socket.AF_INET6, ws.socket.SOCK_STREAM, 6, "", (fake_ipv6, 0, 0, 0)),
            (ws.socket.AF_INET, ws.socket.SOCK_STREAM, 6, "", (fake_ipv4, 0)),
        ]
    )
    original_https_pool = ws.urllib3.HTTPSConnectionPool
    ws.urllib3.HTTPSConnectionPool = _FakeFallbackPool

    try:
        text = extract_text_from_website("https://ipv6-then-ipv4.example.test/")
        expect(text == "ipv4 fallback body", f"Expected the IPv4 fallback candidate's body, got {text!r}")
        expect(
            attempted_hosts == [fake_ipv4],
            f"IPv4 sorts first (test_resolve_validated_ips_prefers_ipv4_deterministically), so it "
            f"should be the ONLY candidate tried when it succeeds on the first attempt, got {attempted_hosts}",
        )
    finally:
        ws.socket.getaddrinfo = original_getaddrinfo
        ws.urllib3.HTTPSConnectionPool = original_https_pool


def test_all_resolved_addresses_unreachable_raises_clean_error() -> None:
    """When every resolved public candidate fails to connect, the result
    must be the same clean, safe-to-display WebsiteFetchError as a single-
    candidate failure -- never an unhandled urllib3/socket exception
    leaking past extract_text_from_website(), and every candidate must
    actually have been tried (bounded fallback exhausted, not given up
    early)."""
    fake_ips = ["8.8.8.40", "8.8.8.41", "8.8.8.42"]
    attempted_hosts: list[str] = []

    class _FakeAllUnreachablePool:
        def __init__(self, host, port, **kwargs) -> None:
            self.host = host

        def request(self, method, path, headers=None, preload_content=None, redirect=None):
            attempted_hosts.append(self.host)
            raise ws.urllib3.exceptions.NewConnectionError(None, "simulated: unreachable")

        def close(self) -> None:
            pass

    original_getaddrinfo = _patched_getaddrinfo(
        [(ws.socket.AF_INET, ws.socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in fake_ips]
    )
    original_https_pool = ws.urllib3.HTTPSConnectionPool
    ws.urllib3.HTTPSConnectionPool = _FakeAllUnreachablePool

    try:
        expect_rejected("https://all-unreachable.example.test/", "could not reach")
        expect(
            attempted_hosts == fake_ips,
            f"Expected every resolved candidate to be tried, in order, got {attempted_hosts}",
        )
    finally:
        ws.socket.getaddrinfo = original_getaddrinfo
        ws.urllib3.HTTPSConnectionPool = original_https_pool


def test_fallback_does_not_retry_after_a_reached_http_error_status() -> None:
    """A candidate that CONNECTS but returns a non-2xx/non-redirect status
    must not trigger a fallback attempt against the next candidate --
    fallback exists only for connection-level failures (Part 6). Proven
    by making the second candidate a pool that would succeed if it were
    ever constructed, and asserting it never is."""
    fake_first_ip = "8.8.8.50"
    fake_second_ip = "8.8.8.51"

    class _FakeErrorStatusResponse:
        def __init__(self) -> None:
            self.status = 500
            self.headers: dict = {}

        def stream(self, chunk_size, decode_content=True):
            return iter([])

        def release_conn(self) -> None:
            pass

    class _FakeFirstCandidatePool:
        def __init__(self, host, port, **kwargs) -> None:
            pass

        def request(self, method, path, headers=None, preload_content=None, redirect=None):
            return _FakeErrorStatusResponse()

        def close(self) -> None:
            pass

    class _PoolThatMustNeverBeConstructed:
        def __init__(self, host, port, **kwargs) -> None:
            raise AssertionError(
                f"A second candidate must never be tried after the first one returned a real "
                f"HTTP error status (not a connection failure), but one was attempted for {host!r}"
            )

    class _RoutingPool:
        """Dispatches to the right fake based on which candidate IP urllib3
        was constructed for -- lets this one test assert BOTH "the first
        candidate's error status is what's raised" and "the second
        candidate is never even constructed", in one pass."""

        def __new__(cls, host, port, **kwargs):
            if host == fake_first_ip:
                return _FakeFirstCandidatePool(host, port, **kwargs)
            return _PoolThatMustNeverBeConstructed(host, port, **kwargs)

    original_getaddrinfo = _patched_getaddrinfo(
        [
            (ws.socket.AF_INET, ws.socket.SOCK_STREAM, 6, "", (fake_first_ip, 0)),
            (ws.socket.AF_INET, ws.socket.SOCK_STREAM, 6, "", (fake_second_ip, 0)),
        ]
    )
    original_https_pool = ws.urllib3.HTTPSConnectionPool
    ws.urllib3.HTTPSConnectionPool = _RoutingPool

    try:
        expect_rejected("https://first-candidate-http-error.example.test/", "HTTP 500")
    finally:
        ws.socket.getaddrinfo = original_getaddrinfo
        ws.urllib3.HTTPSConnectionPool = original_https_pool


def test_request_model_rejects_malformed_url() -> None:
    try:
        WebsiteAnalysisRequest(url="not a url")
    except ValidationError:
        return

    raise AssertionError(
        "Expected WebsiteAnalysisRequest to reject a URL missing http(s)://."
    )


def test_request_model_accepts_legitimate_url() -> None:
    request = WebsiteAnalysisRequest(url="https://example.com/about")
    expect(
        request.url == "https://example.com/about",
        f"Expected a legitimate URL to pass through unchanged, got {request.url!r}",
    )


TESTS = [
    test_valid_public_https_url_is_fetched,
    test_valid_public_http_url_is_fetched,
    test_localhost_rejected,
    test_loopback_ip_rejected,
    test_private_ipv4_rejected,
    test_link_local_and_metadata_rejected,
    test_non_http_scheme_rejected,
    test_malformed_url_rejected,
    test_redirect_to_private_destination_rejected,
    test_oversized_response_rejected,
    test_resolve_validated_ips_prefers_ipv4_deterministically,
    test_resolve_validated_ips_bounded_by_max_address_attempts,
    test_mixed_public_and_private_dns_results_keeps_only_public_candidates,
    test_all_private_dns_results_rejected,
    test_ipv6_unreachable_ipv4_reachable_falls_back_to_ipv4,
    test_all_resolved_addresses_unreachable_raises_clean_error,
    test_fallback_does_not_retry_after_a_reached_http_error_status,
    test_request_model_rejects_malformed_url,
    test_request_model_accepts_legitimate_url,
]


def main() -> None:
    print("\nWebsite / URL Ingestion security tests")
    print("-" * 72)

    failures: list[str] = []

    for test in TESTS:
        name = test.__name__

        try:
            test()
        except AssertionError as error:
            print(f"FAIL  {name}\n      {error}")
            failures.append(name)
        else:
            print(f"PASS  {name}")

    print("-" * 72)
    print(f"{len(TESTS) - len(failures)}/{len(TESTS)} passed")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
