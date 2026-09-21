"""
Runtime proof that the pure code never reads the environment or touches the
network: every public operation is exercised while both are booby-trapped.
(The static side is app/v2/tests/architecture/test_pure_zone_rules.py.)
"""

import os
import socket
from datetime import datetime, timezone

import pytest

from app.v2.domain.content import MediaType, assess_media_agreement, normalize_declared_media_type
from app.v2.domain.errors import DomainError
from app.v2.domain.processing import ProcessingStatus, assert_transition, next_attempt_number
from app.v2.domain.source import CollectionMethod, Source, SourceType, validate_source_url
from app.v2.domain.time import EventTime, ensure_utc
from app.v2.domain.versions import make_version_id, version_name, version_number
from app.v2.observations.hashing import compute_content_hash
from app.v2.observations.media import sniff_media_type
from app.v2.tests.domain.factories import make_observation


def test_the_tripwires_actually_trip(env_tripwire):
    with env_tripwire():
        with pytest.raises(AssertionError, match="environment"):
            os.getenv("ANYTHING")
        with pytest.raises(AssertionError, match="environment"):
            os.environ.get("ANYTHING")
    assert isinstance(os.environ, os._Environ)  # the real environment is restored after the block
    with pytest.raises(AssertionError, match="network"):
        socket.getaddrinfo("example.com", 443)
    with pytest.raises(AssertionError, match="network"):
        socket.create_connection(("example.com", 443))


def _exercise_everything():
    ensure_utc(datetime(2025, 1, 1, tzinfo=timezone.utc))
    EventTime.of_year(2025), EventTime.of_month(2025, 2), EventTime.of_day(2025, 2, 3)
    EventTime.at_instant(datetime(2025, 1, 1, 1, tzinfo=timezone.utc))
    version_number(make_version_id("manual_upload", 1)), version_name("manual_upload.v1")
    for payload in (b"", b"text", b"<html>", b'{"a": 1}', b"%PDF-1.7", b"\x00\xff"):
        compute_content_hash(payload)
        sniff_media_type(payload)
    normalize_declared_media_type("Text/HTML; charset=utf-8")
    assess_media_agreement("text/html", MediaType.TEXT_HTML)
    validate_source_url("https://example.com/path?q=1")           # URL is data only: never fetched
    Source(source_key="sec_edgar", name="SEC EDGAR", source_type=SourceType.OTHER,
           collection_method=CollectionMethod.HTTP_FETCH, url="https://www.sec.gov/edgar", is_active=True)
    obs = make_observation(event_time=EventTime.of_year(2025), declared_media_type="text/html",
                           sniffed_media_type=MediaType.TEXT_HTML)
    obs.media_agreement, obs.media_type_mismatch, obs.dedup_key
    assert_transition(ProcessingStatus.PROCESSING, ProcessingStatus.FAILED)
    next_attempt_number(1, ProcessingStatus.FAILED)
    for bad in (lambda: ensure_utc(datetime(2025, 1, 1)), lambda: validate_source_url("ftp://x"),
                lambda: compute_content_hash("text")):
        with pytest.raises(DomainError):
            bad()


def test_pure_operations_never_read_the_environment_or_use_the_network(env_tripwire):
    with env_tripwire():
        _exercise_everything()  # any os.environ / os.getenv / socket use raises AssertionError
