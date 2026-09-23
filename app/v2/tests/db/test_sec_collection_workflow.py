"""
Increment 18.3: the collector wired into the real pipeline, against the disposable V2 test database, with
requests.get mocked (never the real network -- the one real collection is demonstrated separately, see this
increment's report). Required coverage: duplicate collection, partial batch failures, no automatic canonical
promotion.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.v2.repositories.sources import register_source
from app.v2.tools import cli, sec_form_d_collector
from app.v2.tools.sec_form_d_collector import CollectionError

pytestmark = pytest.mark.db

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
REAL_FILING = (FIXTURE_DIR / "gecko_robotics_form_d_real.xml").read_bytes()
VALID_UA = "VentureGPS Research (contact: research@venturegps.example)"


class FakeResponse:
    def __init__(self, status_code=200, content=b"", headers=None, url="https://www.sec.gov/x"):
        self.status_code = status_code
        self._content = content
        self.headers = headers or {}
        self.url = url
        self.is_redirect = False

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]

    def close(self):
        pass


@pytest.fixture(autouse=True)
def env_and_dns(monkeypatch):
    monkeypatch.setenv(sec_form_d_collector.COLLECTOR_USER_AGENT_ENV, VALID_UA)
    import socket

    def fake_getaddrinfo(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("96.6.235.12", 443))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


@pytest.fixture
def registered_source(migrated_db):
    register_source(migrated_db, cli.SOURCE_SEC_FORM_D_AUTO)
    return migrated_db


def _canonical_counts(db) -> dict:
    with db.connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM v2.{t}")).scalar()
                for t in ("company", "financing_event", "resolution_decision", "financing_resolution_decision")}


# ---------------------------------------------------------------- valid collection + no automatic promotion

def test_a_real_filing_is_ingested_and_extracted_with_no_automatic_canonical_promotion(registered_source):
    with patch.object(sec_form_d_collector.requests, "get", return_value=FakeResponse(200, REAL_FILING)):
        outcome = cli._collect_and_extract_one(registered_source, "1747029", "0001747029-25-000002", dry_run=False)

    assert outcome["status"] == "new"
    assert outcome["pending_review"] is True
    assert len(outcome["candidate_ids"]) == 1

    # The whole point of "no automatic canonical promotion": collection + extraction never creates a Company,
    # a FinancingEvent, or any resolution decision -- only untrusted candidates exist until a human decides.
    counts = _canonical_counts(registered_source)
    assert counts == {"company": 0, "financing_event": 0, "resolution_decision": 0, "financing_resolution_decision": 0}


def test_dry_run_makes_no_network_call_and_no_database_write(registered_source):
    with patch.object(sec_form_d_collector.requests, "get") as mock_get:
        outcome = cli._collect_and_extract_one(registered_source, "1747029", "0001747029-25-000002", dry_run=True)
    assert outcome["status"] == "dry_run"
    mock_get.assert_not_called()
    with registered_source.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.observation")).scalar() == 0


# ---------------------------------------------------------------- duplicate collection

def test_collecting_the_identical_filing_twice_is_reported_as_duplicate_not_reingested(registered_source):
    with patch.object(sec_form_d_collector.requests, "get", return_value=FakeResponse(200, REAL_FILING)):
        first = cli._collect_and_extract_one(registered_source, "1747029", "0001747029-25-000002", dry_run=False)
        second = cli._collect_and_extract_one(registered_source, "1747029", "0001747029-25-000002", dry_run=False)

    assert first["status"] == "new"
    assert second["status"] == "duplicate"
    assert first["observation_id"] == second["observation_id"]
    assert first["candidate_ids"] == second["candidate_ids"]  # the SAME candidate reused, never a second one

    with registered_source.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.observation")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM v2.company_candidate")).scalar() == 1
        # Two real acquisition events did happen, though -- a second Sighting, not a second Observation.
        assert conn.execute(text("SELECT count(*) FROM v2.observation_sighting")).scalar() == 2


# ---------------------------------------------------------------- partial batch failures

def test_a_batch_with_one_failing_item_still_persists_the_successful_one(registered_source):
    """Increment 18.3's own required "partial batch failures" case: one item's collection failure must not
    abort the batch or roll back a different item's already-successful work."""
    call_count = {"n": 0}

    def flaky_get(url, **kwargs):
        call_count["n"] += 1
        if "9999999" in url:  # the second, deliberately-failing filing
            import requests as _requests
            raise _requests.exceptions.ConnectionError("simulated failure")
        return FakeResponse(200, REAL_FILING)

    items = [("1747029", "0001747029-25-000002"), ("9999999", "0009999999-25-000001")]
    with patch.object(sec_form_d_collector.requests, "get", side_effect=flaky_get), \
         patch.object(sec_form_d_collector.time, "sleep", lambda s: None):
        outcomes = [cli._collect_and_extract_one(registered_source, cik, accession, dry_run=False) for cik, accession in items]

    assert outcomes[0]["status"] == "new"
    assert outcomes[1]["status"] == "failed"
    # The successful item's evidence really is there, unaffected by the other item's failure.
    with registered_source.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.observation")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM v2.company_candidate")).scalar() == 1


def test_discovery_failure_is_a_clean_exit_not_an_unhandled_exception(registered_source):
    """A discovery-layer failure (e.g. SEC's search API unreachable) must be a clean, reported error -- not an
    unhandled exception propagating out of the CLI -- since cmd_collect_form_d_batch calls
    discover_form_d_filings before any collection is attempted."""
    class Args:
        query = "x"
        max_results = 5
        dry_run = False

    with patch.object(sec_form_d_collector, "discover_form_d_filings", side_effect=CollectionError("simulated discovery failure")):
        with pytest.raises(SystemExit) as exc_info:
            cli.cmd_collect_form_d_batch(Args(), registered_source)
    assert exc_info.value.code == 1
    # Nothing was written: discovery failed before any item was even attempted.
    with registered_source.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.observation")).scalar() == 0
