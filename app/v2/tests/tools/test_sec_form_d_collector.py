"""
sec_form_d_collector.py, entirely against MOCKED network responses (Increment 18.3's own explicit instruction --
no automated test hits the real SEC.gov; the real collection is demonstrated separately and manually, see this
increment's report). Required coverage: valid collection, rate limiting, timeouts/retries, invalid/oversized
responses, unsafe redirects/SSRF attempts, malformed discovery responses.
"""

import socket
from unittest.mock import patch

import pytest
import requests

from app.v2.tools import sec_form_d_collector as collector

REAL_CIK = "1747029"
REAL_ACCESSION = "0001747029-25-000002"
VALID_UA = "VentureGPS Research (contact: research@venturegps.example)"


class FakeResponse:
    """The minimal subset of requests.Response the collector actually uses."""

    def __init__(self, status_code=200, content=b"", headers=None, url="https://www.sec.gov/x", is_redirect=False):
        self.status_code = status_code
        self._content = content
        self.headers = headers or {}
        self.url = url
        self.is_redirect = is_redirect
        self.closed = False

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def resolve_sec_hosts_to_a_public_address(monkeypatch):
    """Every real test here mocks requests.get directly, so DNS never actually needs to succeed -- but
    _assert_safe_target calls socket.getaddrinfo BEFORE requests.get is even reached, so it needs a real-looking
    answer. 96.6.235.12 is one of www.sec.gov's own real, currently-routed, genuinely global IPv4 addresses
    (confirmed by a real lookup during this increment's development, not a documentation/TEST-NET range -- Python's
    ipaddress module treats RFC 5737 TEST-NET ranges as `is_private`, which made an earlier version of this
    fixture fail this exact safety check it was trying to satisfy). Keeps these tests fully network-independent
    while still exercising the real IP-safety logic for the "safe" path; a separate test overrides this fixture
    to prove the private-address case is refused."""
    def fake_getaddrinfo(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("96.6.235.12", 443))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


# ---------------------------------------------------------------- valid collection

def test_valid_form_d_collection_preserves_bytes_exactly():
    real_content = (
        b'<?xml version="1.0"?>\n<edgarSubmission><submissionType>D</submissionType>'
        b"<primaryIssuer><entityName>Example Robotics, Inc.</entityName></primaryIssuer></edgarSubmission>"
    )
    with patch.object(collector.requests, "get", return_value=FakeResponse(200, real_content)) as mock_get:
        result = collector.collect_form_d_filing(REAL_CIK, REAL_ACCESSION, user_agent=VALID_UA)
    assert result.content == real_content  # byte-exact, never re-encoded or modified
    assert result.cik == REAL_CIK
    assert result.accession == REAL_ACCESSION
    called_url = mock_get.call_args.args[0] if mock_get.call_args.args else mock_get.call_args.kwargs["url"]
    assert called_url == collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION)
    assert mock_get.call_args.kwargs["allow_redirects"] is False
    assert mock_get.call_args.kwargs["headers"]["User-Agent"] == VALID_UA


def test_no_user_agent_configured_refuses_to_collect(monkeypatch):
    monkeypatch.delenv(collector.COLLECTOR_USER_AGENT_ENV, raising=False)
    with pytest.raises(collector.CollectionError):
        collector.collect_form_d_filing(REAL_CIK, REAL_ACCESSION)


def test_a_user_agent_without_contact_info_is_refused(monkeypatch):
    monkeypatch.setenv(collector.COLLECTOR_USER_AGENT_ENV, "just a name, no email")
    with pytest.raises(collector.CollectionError):
        collector.require_user_agent()


# ---------------------------------------------------------------- SSRF / unsafe targets

@pytest.mark.parametrize("bad_url", [
    "https://example.com/Archives/edgar/data/1/1/primary_doc.xml",
    "http://www.sec.gov/Archives/edgar/data/1/1/primary_doc.xml",  # not https
    "https://www.sec.gov:8443/Archives/edgar/data/1/1/primary_doc.xml",  # not the default port
    "https://attacker.example/www.sec.gov/Archives/edgar/data/1/1/primary_doc.xml",  # host confusion attempt
])
def test_unsafe_urls_are_refused_before_any_request_is_made(bad_url):
    with patch.object(collector.requests, "get") as mock_get:
        with pytest.raises(collector.UnsafeTargetError):
            collector.fetch(bad_url, user_agent=VALID_UA)
        mock_get.assert_not_called()  # SSRF check happens before the network call, not after


def test_a_resolved_private_address_is_refused_even_for_an_allowlisted_host(monkeypatch):
    """The DNS-rebinding-style case: the hostname is on the allowlist, but resolves to a private address."""
    def fake_getaddrinfo(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with patch.object(collector.requests, "get") as mock_get:
        with pytest.raises(collector.UnsafeTargetError):
            collector.fetch(collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION), user_agent=VALID_UA)
        mock_get.assert_not_called()


def test_dns_resolution_failure_is_refused_as_unsafe(monkeypatch):
    def fake_getaddrinfo(host, port, **kwargs):
        raise OSError("name resolution failed")
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(collector.UnsafeTargetError):
        collector.fetch(collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION), user_agent=VALID_UA)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_any_redirect_status_is_refused_never_followed(status):
    with patch.object(collector.requests, "get", return_value=FakeResponse(status, b"", headers={"Location": "https://attacker.example/"})):
        with pytest.raises(collector.UnsafeTargetError):
            collector.fetch(collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION), user_agent=VALID_UA)


def test_cik_leading_zeros_are_normalized_so_no_redirect_is_needed():
    """Confirmed directly against the real EDGAR server (see this increment's report): a zero-padded CIK path
    segment 301-redirects to its canonical form. Normalizing avoids ever needing that redirect."""
    assert collector.normalize_cik("0002082001") == "2082001"
    assert collector.normalize_cik("1747029") == "1747029"
    assert "0002082001" not in collector.form_d_primary_document_url("0002082001", REAL_ACCESSION)


# ---------------------------------------------------------------- path/input validation (no path injection)

@pytest.mark.parametrize("bad_cik", ["", "abc", "12 34", "../../etc/passwd", "1" * 11])
def test_malformed_cik_is_rejected(bad_cik):
    with pytest.raises(collector.CollectionError):
        collector.form_d_primary_document_url(bad_cik, REAL_ACCESSION)


@pytest.mark.parametrize("bad_accession", ["", "not-an-accession", "0001747029250000002", "../../secrets"])
def test_malformed_accession_is_rejected(bad_accession):
    with pytest.raises(collector.CollectionError):
        collector.form_d_primary_document_url(REAL_CIK, bad_accession)


# ---------------------------------------------------------------- rate limiting / Retry-After

def test_429_with_retry_after_is_respected_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr(collector.time, "sleep", lambda s: sleeps.append(s))
    responses = [FakeResponse(429, b"", headers={"Retry-After": "2"}), FakeResponse(200, b"ok-content")]
    with patch.object(collector.requests, "get", side_effect=responses):
        result = collector.fetch(collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION), user_agent=VALID_UA)
    assert result.content == b"ok-content"
    assert sleeps == [2.0]  # the exact Retry-After value, not a computed backoff


def test_429_persisting_past_max_retries_raises_rate_limited(monkeypatch):
    monkeypatch.setattr(collector.time, "sleep", lambda s: None)
    with patch.object(collector.requests, "get", return_value=FakeResponse(429, b"", headers={"Retry-After": "1"})):
        with pytest.raises(collector.RateLimitedError):
            collector.fetch(collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION), user_agent=VALID_UA)


def test_a_retry_after_beyond_the_bound_is_refused_not_slept_through(monkeypatch):
    monkeypatch.setattr(collector.time, "sleep", lambda s: pytest.fail("should never sleep past the bound"))
    huge = str(collector.MAX_RESPECTED_RETRY_AFTER_SECONDS + 1)
    with patch.object(collector.requests, "get", return_value=FakeResponse(429, b"", headers={"Retry-After": huge})):
        with pytest.raises(collector.RateLimitedError):
            collector.fetch(collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION), user_agent=VALID_UA)


def test_503_without_retry_after_uses_computed_backoff_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr(collector.time, "sleep", lambda s: sleeps.append(s))
    responses = [FakeResponse(503, b""), FakeResponse(200, b"ok")]
    with patch.object(collector.requests, "get", side_effect=responses):
        result = collector.fetch(collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION), user_agent=VALID_UA)
    assert result.content == b"ok"
    assert sleeps == [collector.INITIAL_BACKOFF_SECONDS]


# ---------------------------------------------------------------- timeouts and connection errors

def test_a_timeout_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr(collector.time, "sleep", lambda s: None)
    calls = [requests.exceptions.Timeout("timed out"), FakeResponse(200, b"ok")]

    def fake_get(*a, **k):
        item = calls.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    with patch.object(collector.requests, "get", side_effect=fake_get):
        result = collector.fetch(collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION), user_agent=VALID_UA)
    assert result.content == b"ok"


def test_persistent_timeout_exhausts_retries_and_raises(monkeypatch):
    monkeypatch.setattr(collector.time, "sleep", lambda s: None)
    with patch.object(collector.requests, "get", side_effect=requests.exceptions.Timeout("timed out")):
        with pytest.raises(collector.UpstreamError):
            collector.fetch(collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION), user_agent=VALID_UA)


def test_connection_error_is_retried_with_bounded_attempts(monkeypatch):
    attempts = {"n": 0}
    monkeypatch.setattr(collector.time, "sleep", lambda s: None)

    def fake_get(*a, **k):
        attempts["n"] += 1
        raise requests.exceptions.ConnectionError("refused")
    with patch.object(collector.requests, "get", side_effect=fake_get):
        with pytest.raises(collector.UpstreamError):
            collector.fetch(collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION), user_agent=VALID_UA)
    assert attempts["n"] == collector.MAX_RETRIES


def test_a_client_error_is_never_retried():
    attempts = {"n": 0}

    def fake_get(*a, **k):
        attempts["n"] += 1
        return FakeResponse(404, b"not found")
    with patch.object(collector.requests, "get", side_effect=fake_get):
        with pytest.raises(collector.UpstreamError):
            collector.fetch(collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION), user_agent=VALID_UA)
    assert attempts["n"] == 1  # a 404 will never succeed on retry


# ---------------------------------------------------------------- oversized / invalid responses

def test_a_response_exceeding_the_size_limit_is_aborted_while_streaming():
    too_big = b"x" * (collector.MAX_RESPONSE_BYTES + 1)
    with patch.object(collector.requests, "get", return_value=FakeResponse(200, too_big)):
        with pytest.raises(collector.ResponseTooLargeError):
            collector.fetch(collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION), user_agent=VALID_UA)


def test_a_response_at_exactly_the_size_limit_is_accepted():
    exactly = b"x" * collector.MAX_RESPONSE_BYTES
    with patch.object(collector.requests, "get", return_value=FakeResponse(200, exactly)):
        result = collector.fetch(collector.form_d_primary_document_url(REAL_CIK, REAL_ACCESSION), user_agent=VALID_UA)
    assert len(result.content) == collector.MAX_RESPONSE_BYTES


# ---------------------------------------------------------------- discovery (bounded batch)

def test_discovery_returns_a_bounded_list_from_a_realistic_response():
    body = (
        b'{"hits":{"hits":['
        b'{"_source":{"ciks":["0001747029"],"adsh":"0001747029-25-000002","display_names":["Gecko Robotics, Inc."],"file_date":"2025-06-12"}},'
        b'{"_source":{"ciks":["0002082001"],"adsh":"0002082041-25-000004","display_names":["HII Gecko Robotics Series I"],"file_date":"2025-08-19"}}'
        b"]}}"
    )
    with patch.object(collector.requests, "get", return_value=FakeResponse(200, body)):
        results = collector.discover_form_d_filings("gecko robotics", user_agent=VALID_UA, max_results=10)
    assert len(results) == 2
    assert results[0].cik == "0001747029"
    assert results[0].accession == "0001747029-25-000002"


def test_discovery_is_capped_at_max_results_even_if_more_are_returned():
    hits = b",".join(
        f'{{"_source":{{"ciks":["{i:010d}"],"adsh":"0001747029-25-{i:06d}","display_names":["X"],"file_date":"2025-01-01"}}}}'.encode()
        for i in range(10)
    )
    body = b'{"hits":{"hits":[' + hits + b"]}}"
    with patch.object(collector.requests, "get", return_value=FakeResponse(200, body)):
        results = collector.discover_form_d_filings("x", user_agent=VALID_UA, max_results=3)
    assert len(results) == 3


def test_discovery_requesting_more_than_the_hard_cap_is_refused():
    with pytest.raises(collector.CollectionError):
        collector.discover_form_d_filings("x", user_agent=VALID_UA, max_results=collector.MAX_DISCOVERY_RESULTS + 1)


def test_malformed_discovery_response_is_reported_not_silently_swallowed():
    with patch.object(collector.requests, "get", return_value=FakeResponse(200, b"not json at all")):
        with pytest.raises(collector.UpstreamError):
            collector.discover_form_d_filings("x", user_agent=VALID_UA)


def test_discovery_skips_a_hit_missing_required_fields_rather_than_crashing():
    body = (
        b'{"hits":{"hits":['
        b'{"_source":{"display_names":["missing ciks and adsh"]}},'
        b'{"_source":{"ciks":["0001747029"],"adsh":"0001747029-25-000002","display_names":["Gecko Robotics, Inc."],"file_date":"2025-06-12"}}'
        b"]}}"
    )
    with patch.object(collector.requests, "get", return_value=FakeResponse(200, body)):
        results = collector.discover_form_d_filings("x", user_agent=VALID_UA)
    assert len(results) == 1
    assert results[0].accession == "0001747029-25-000002"
