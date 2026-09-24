"""
Increment 18.5: run_bounded_collection (app.v2.tools.scheduled_collection) against the disposable V2 test
database, with requests.get mocked and discover_form_d_filings mocked (never the real network -- see this
increment's runbook for the one, explicit, bounded real demonstration). Required coverage: no overlapping
runs, idempotent repeats, partial batch failures recorded accurately, interrupted-run recovery, no automatic
canonical promotion, and the max-filings bound.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.v2.domain.collection import CollectionRunStatus, CollectionTriggerType
from app.v2.repositories.collection_runs import (
    CollectionAlreadyRunningError,
    list_collection_runs,
    start_run,
)
from app.v2.repositories.sources import register_source
from app.v2.tools import cli, sec_form_d_collector
from app.v2.tools.scheduled_collection import run_bounded_collection

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


def _one_discovered(cik="1747029", accession="0001747029-25-000002"):
    return [sec_form_d_collector.DiscoveredFiling(cik=cik, accession=accession, display_name="Gecko Robotics, Inc.", file_date="2025-01-01")]


# ---------------------------------------------------------------- basic success + no automatic promotion

def test_a_successful_run_is_recorded_with_no_automatic_canonical_promotion(registered_source):
    with patch.object(sec_form_d_collector, "discover_form_d_filings", return_value=_one_discovered()), \
         patch.object(sec_form_d_collector.requests, "get", return_value=FakeResponse(200, REAL_FILING)):
        run = run_bounded_collection(
            registered_source, query="robotics", max_filings=5, trigger_type=CollectionTriggerType.MANUAL,
            triggered_by="admin:test",
        )

    assert run.status is CollectionRunStatus.SUCCEEDED
    assert run.discovered_count == 1
    assert run.collected_count == 1
    assert run.candidate_count == 1
    assert run.completed_at is not None

    # The whole point: extraction never creates a Company, FinancingEvent, or any resolution decision.
    assert _canonical_counts(registered_source) == {
        "company": 0, "financing_event": 0, "resolution_decision": 0, "financing_resolution_decision": 0,
    }


# ---------------------------------------------------------------- no overlapping runs

def test_a_second_concurrent_run_for_the_same_job_is_refused(registered_source):
    start_run(registered_source, job_name="sec_form_d", trigger_type=CollectionTriggerType.MANUAL,
              triggered_by="admin:test", query="robotics", max_filings=5, lease_seconds=60)

    with patch.object(sec_form_d_collector, "discover_form_d_filings") as mock_discover:
        with pytest.raises(CollectionAlreadyRunningError):
            run_bounded_collection(
                registered_source, query="robotics", max_filings=5, trigger_type=CollectionTriggerType.MANUAL,
                triggered_by="admin:test",
            )
    mock_discover.assert_not_called()  # refused before any network call was even attempted


def test_a_different_job_name_is_not_blocked_by_another_jobs_active_run(registered_source):
    start_run(registered_source, job_name="sec_form_d", trigger_type=CollectionTriggerType.MANUAL,
              triggered_by="admin:test", query="robotics", max_filings=5, lease_seconds=60)

    with patch.object(sec_form_d_collector, "discover_form_d_filings", return_value=[]):
        run = run_bounded_collection(
            registered_source, query="anything", max_filings=5, trigger_type=CollectionTriggerType.MANUAL,
            triggered_by="admin:test", job_name="a_different_job",
        )
    assert run.status is CollectionRunStatus.SUCCEEDED


# ---------------------------------------------------------------- idempotent repeats

def test_repeating_the_same_run_twice_does_not_duplicate_evidence_or_candidates(registered_source):
    with patch.object(sec_form_d_collector, "discover_form_d_filings", return_value=_one_discovered()), \
         patch.object(sec_form_d_collector.requests, "get", return_value=FakeResponse(200, REAL_FILING)):
        first = run_bounded_collection(registered_source, query="robotics", max_filings=5,
                                       trigger_type=CollectionTriggerType.MANUAL, triggered_by="admin:test")
        second = run_bounded_collection(registered_source, query="robotics", max_filings=5,
                                        trigger_type=CollectionTriggerType.MANUAL, triggered_by="admin:test")

    assert first.status is CollectionRunStatus.SUCCEEDED
    assert first.collected_count == 1 and first.duplicate_count == 0
    assert second.status is CollectionRunStatus.SUCCEEDED
    assert second.collected_count == 0 and second.duplicate_count == 1  # reported as duplicate, not re-collected

    with registered_source.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.observation")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM v2.company_candidate")).scalar() == 1

    # Two distinct job-history rows exist -- job history itself is never deduplicated, only the evidence is.
    runs = list_collection_runs(registered_source, job_name="sec_form_d")
    assert len(runs) == 2


# ---------------------------------------------------------------- partial batch failures

def test_partial_batch_failure_is_recorded_accurately(registered_source):
    def flaky_get(url, **kwargs):
        if "9999999" in url:
            import requests as _requests
            raise _requests.exceptions.ConnectionError("simulated failure")
        return FakeResponse(200, REAL_FILING)

    discovered = _one_discovered() + _one_discovered(cik="9999999", accession="0009999999-25-000001")
    with patch.object(sec_form_d_collector, "discover_form_d_filings", return_value=discovered), \
         patch.object(sec_form_d_collector.requests, "get", side_effect=flaky_get), \
         patch.object(sec_form_d_collector.time, "sleep", lambda s: None):
        run = run_bounded_collection(registered_source, query="robotics", max_filings=5,
                                     trigger_type=CollectionTriggerType.MANUAL, triggered_by="admin:test")

    assert run.status is CollectionRunStatus.PARTIAL
    assert run.discovered_count == 2
    assert run.collected_count == 1
    assert run.failed_count == 1
    assert run.failure_detail is not None and "1 of 2" in run.failure_detail
    assert run.result_detail is not None and "failed" in run.result_detail


def test_discovery_failure_completes_the_run_as_failed_not_a_stuck_running_row(registered_source):
    with patch.object(sec_form_d_collector, "discover_form_d_filings",
                      side_effect=sec_form_d_collector.CollectionError("simulated discovery failure")):
        run = run_bounded_collection(registered_source, query="robotics", max_filings=5,
                                     trigger_type=CollectionTriggerType.MANUAL, triggered_by="admin:test")

    assert run.status is CollectionRunStatus.FAILED
    assert run.completed_at is not None
    assert run.failure_detail is not None and "CollectionError" in run.failure_detail
    # And the lock is released: a fresh run for the same job can start immediately.
    with patch.object(sec_form_d_collector, "discover_form_d_filings", return_value=[]):
        next_run = run_bounded_collection(registered_source, query="robotics", max_filings=5,
                                          trigger_type=CollectionTriggerType.MANUAL, triggered_by="admin:test")
    assert next_run.status is CollectionRunStatus.SUCCEEDED


# ---------------------------------------------------------------- interrupted-run recovery

def test_a_run_whose_lease_expired_is_recovered_and_does_not_block_a_new_run(registered_source):
    stale = start_run(registered_source, job_name="sec_form_d", trigger_type=CollectionTriggerType.SCHEDULED,
                      triggered_by="cli:scheduled", query="robotics", max_filings=5, lease_seconds=1)

    # Simulate real time passing by directly expiring the lease (no real sleep in a test).
    with registered_source.begin() as conn:
        conn.execute(text("UPDATE v2.collection_run SET lease_expires_at = :t WHERE id = :id"),
                     {"t": datetime.now(timezone.utc) - timedelta(seconds=1), "id": stale.id})

    with patch.object(sec_form_d_collector, "discover_form_d_filings", return_value=[]):
        run = run_bounded_collection(registered_source, query="robotics", max_filings=5,
                                     trigger_type=CollectionTriggerType.MANUAL, triggered_by="admin:test")

    assert run.status is CollectionRunStatus.SUCCEEDED
    runs = {r.id: r for r in list_collection_runs(registered_source, job_name="sec_form_d")}
    assert runs[stale.id].status is CollectionRunStatus.INTERRUPTED
    assert runs[stale.id].failure_detail == "lease_expired"


# ---------------------------------------------------------------- bounds

def test_max_filings_above_the_hard_cap_is_rejected(registered_source):
    from app.v2.domain.errors import InvalidInputError
    with pytest.raises(InvalidInputError):
        run_bounded_collection(registered_source, query="robotics", max_filings=26,
                               trigger_type=CollectionTriggerType.MANUAL, triggered_by="admin:test")


def test_dry_run_makes_no_collection_and_no_database_write(registered_source):
    with patch.object(sec_form_d_collector, "discover_form_d_filings", return_value=_one_discovered()), \
         patch.object(sec_form_d_collector.requests, "get") as mock_get:
        run = run_bounded_collection(registered_source, query="robotics", max_filings=5,
                                     trigger_type=CollectionTriggerType.MANUAL, triggered_by="admin:test", dry_run=True)
    assert run.status is CollectionRunStatus.SUCCEEDED
    assert run.discovered_count == 1
    assert run.collected_count == 0
    mock_get.assert_not_called()
    with registered_source.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.observation")).scalar() == 0
