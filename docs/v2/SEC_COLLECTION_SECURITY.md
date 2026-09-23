# SEC Form D collection: security and failure-handling — Increment 18.3

Scope: `app/v2/tools/sec_form_d_collector.py`, the only module anywhere in `app/v2` that performs network I/O.
Everything downstream (`app/v2/ingestion`, `app/v2/candidates`, `app/v2/resolution`,
`app/v2/financing_resolution`, `app/v2/classification`, `app/v2/repositories`) is a `no_network_package`
(`app/v2/tests/architecture/boundary_rules.py`) and stays exactly as network-free as it was before this
increment — this document is entirely about the one module where a real outbound request happens.

## Threat model

This is not a general-purpose fetcher a caller points at an arbitrary URL — there is no `url` parameter
anywhere in its public API. The only inputs are a CIK, an accession number, and (for discovery) a free-text
search query, all validated before use. The realistic risks this module actually guards against:

1. A caller (or a bug) supplying a malformed CIK/accession that, if concatenated unvalidated into a URL path,
   could reach an unintended path.
2. SEC's own server misbehaving or being compromised and issuing a redirect to somewhere unsafe.
3. A resolved hostname (even an allowlisted one) pointing at a private/internal address, whether through
   misconfiguration or a DNS-rebinding-style attack.
4. An oversized, slow, or maliciously crafted response consuming unbounded memory or time.
5. Legitimate rate limiting from SEC, mishandled as either a hard failure or an unbounded wait.

## Controls, and exactly where each is enforced

| Control | Enforcement | Test coverage |
|---|---|---|
| Host allowlist (`www.sec.gov`, `efts.sec.gov` only) | `_assert_safe_target`, checked on **every** request, not just the first | `test_unsafe_urls_are_refused_before_any_request_is_made` |
| HTTPS only, default port only | Same function | Same test (parametrized) |
| No path/URL ever built from unvalidated input | `validate_cik`/`validate_accession` (regex, full-match) before any string formatting | `test_malformed_cik_is_rejected`, `test_malformed_accession_is_rejected` (including literal path-traversal attempts) |
| Redirects never followed | `allow_redirects=False` on every request; any 3xx response (or `response.is_redirect`) raises `UnsafeTargetError` before its body is ever read | `test_any_redirect_status_is_refused_never_followed` (301/302/303/307/308) — and a REAL one, from the real server, was caught live during this increment's development (see the runbook's "CIK zero-padding" section) |
| Resolved-address safety (defends misconfiguration and DNS-rebinding-style attacks) | `socket.getaddrinfo` resolved before connecting; every returned address checked via `ipaddress` for private/loopback/link-local/multicast/reserved/unspecified, refusing if any one address fails | `test_a_resolved_private_address_is_refused_even_for_an_allowlisted_host`, `test_dns_resolution_failure_is_refused_as_unsafe` |
| Required, real User-Agent (SEC's own published policy) | `require_user_agent()`, no default, checked before every collect/discover call | `test_no_user_agent_configured_refuses_to_collect`, `test_a_user_agent_without_contact_info_is_refused` |
| Timeouts | `(10, 20)` second (connect, read) tuple on every request | exercised by every mocked-timeout test |
| Response size limit | Enforced **while streaming** (`iter_content`, aborted the instant the running total exceeds 1 MiB) — never buffers an unbounded response first | `test_a_response_exceeding_the_size_limit_is_aborted_while_streaming`, `test_a_response_at_exactly_the_size_limit_is_accepted` (boundary) |
| Bounded retries, exponential backoff | Max 3 attempts total; 1s initial backoff, ×2 per attempt, on connection errors/timeouts/5xx | `test_persistent_timeout_exhausts_retries_and_raises`, `test_connection_error_is_retried_with_bounded_attempts` |
| `Retry-After` respected, but bounded | Read on 429/503; slept for exactly that duration, **unless** it exceeds 120s, in which case the request fails rather than blocking the caller indefinitely | `test_429_with_retry_after_is_respected_then_succeeds`, `test_a_retry_after_beyond_the_bound_is_refused_not_slept_through` |
| 4xx (other than 429) never retried | Checked explicitly — a 404 cannot succeed on retry | `test_a_client_error_is_never_retried` |
| Bounded discovery ("batch collection", never a scrape) | `MAX_DISCOVERY_RESULTS = 25`, enforced in `discover_form_d_filings`; a caller cannot request more | `test_discovery_requesting_more_than_the_hard_cap_is_refused` |
| Evidence preserved exactly, never modified | The fetched bytes are handed to the existing, unmodified `ingest_evidence` unchanged — no re-encoding, no BOM stripping, nothing | `test_valid_form_d_collection_preserves_bytes_exactly` (byte-for-byte `==`), and the real run's `result.content == <checked-in fixture>` check |

## Failure handling, end to end

Every failure mode below is a `CollectionError` subclass (or an ordinary ingestion/extraction error), caught at
the CLI layer and reported as a structured `{"status": "failed", "reason": ...}` entry — never an unhandled
traceback, and (in `collect-form-d-batch`) never aborts processing of the remaining items:

- `UnsafeTargetError` — SSRF/redirect/host-allowlist violation.
- `ResponseTooLargeError` — streamed response exceeded the size limit.
- `RateLimitedError` — 429/503 persisted past the retry budget, or `Retry-After` exceeded the respected bound.
- `UpstreamError` — a non-retryable HTTP status, or a transient one that exhausted its retries.
- `CollectionError` (base) — malformed CIK/accession, missing User-Agent, malformed discovery response.
- A malformed Form D document (e.g. not well-formed XML, or missing a required field) is **not** a collection
  failure — the bytes were collected successfully; `FormDParseError`, raised by the same, unmodified Increment
  18.2 parser, is a separate, later failure mode, already covered by that increment's own tests.

Error messages throughout are static text and, at most, small structural details (a status code, a byte count)
— never response bodies, headers, or the query/CIK/accession values themselves, matching the same
"no evidence content in error messages" convention `app/v2/candidates/evidence.py` already established.

## What this document does not claim

- It does not claim SEC EDGAR itself is trustworthy in some absolute sense — it claims that if the connection
  reaches an unexpected place, this module refuses to proceed, and that the two hosts it will ever reach are
  hard-coded, not configurable at runtime by a caller.
- It does not implement TLS certificate pinning or a raw-socket-with-manual-SNI connection (the most rigorous,
  and most complex, defense against a compromised CA or a resolver that lies about IP *and* serves a valid
  certificate for it). Given the fixed, non-caller-supplied host allowlist and the explicit
  "do not introduce ... unnecessary infrastructure" instruction for this increment, the IP-safety check plus
  the standard TLS certificate validation `requests`/`urllib3` already perform were judged the proportionate
  control; revisit if this collector's scope ever grows to caller-supplied hosts.
