"""
End-to-end Increment 18.2 workflow tests against the disposable V2 test database: source -> evidence -> Form D
extraction -> human resolution -> classification -> Capital metrics/signal, using the REAL Gecko Robotics Form D
filing fixture (app/v2/tests/fixtures/gecko_robotics_form_d_real.xml). Increment 18.2's own required coverage:
duplicate filings, idempotent ingestion, insufficient market history, rejected candidate records never entering
canonical metrics. (Malformed XML, evidence locator integrity, conflicting amounts/dates and absent identifiers
are covered without a database in app/v2/tests/tools/ -- this file only covers what genuinely needs Postgres:
persistence, idempotency and the metrics/signal read path.)
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.v2.classification.service import classify_company
from app.v2.domain.resolution import human_authority
from app.v2.domain.source import CollectionMethod, Source, SourceType
from app.v2.domain.taxonomy import ClassificationRole
from app.v2.financing_resolution import promotion as financing_promotion
from app.v2.ingestion.models import IngestionCommand
from app.v2.ingestion.service import ingest_evidence
from app.v2.repositories import financing_event_candidates as financing_candidates_repo
from app.v2.repositories import markets
from app.v2.repositories import processing_attempts as attempts
from app.v2.repositories import sources
from app.v2.repositories.capital_metrics import compute_capital_metrics_for_market
from app.v2.repositories.capital_signal import compute_capital_signal_for_market
from app.v2.resolution import promotion as company_promotion
from app.v2.candidates.service import persist_verified_candidates
from app.v2.tools.form_d_company_proposer import FormDCompanyProposer
from app.v2.tools.form_d_financing_proposer import propose_financing_from_form_d
from app.v2.domain.financing_resolution import FactSelection

pytestmark = pytest.mark.db

HUMAN = human_authority("admin:jerrod")
TAXONOMY_VERSION = "venturegps_taxonomy.v1"
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
REAL_FILING = (FIXTURE_DIR / "gecko_robotics_form_d_real.xml").read_bytes()


def _register_source(db):
    return sources.register_source(db, Source(
        source_key="sec_edgar_form_d", name="SEC EDGAR -- Form D filings", source_type=SourceType.GOVERNMENT_REGULATORY,
        collection_method=CollectionMethod.MANUAL_UPLOAD, url="https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets",
        is_active=True,
    ))


def _ingest_filing(db, *, acquisition_key="test-run"):
    return ingest_evidence(db, IngestionCommand(
        source_key="sec_edgar_form_d", source_record_identifier="0001747029-25-000002", observation_type="sec_form_d_filing",
        event_time=None, observed_time=datetime.now(timezone.utc), collection_version="manual_upload.v1",
        collector_id="test_suite", declared_media_type=None, payload_bytes=REAL_FILING, acquisition_key=acquisition_key,
    ))


def _setup_market(db):
    markets.register_taxonomy_version(db, TAXONOMY_VERSION)
    return markets.register_market(db, "robotics", "Robotics")


def _extract_and_create_company(db, observation_id):
    attempt = attempts.start_processing(db, observation_id, "form_d_company_extractor", "form_d_company_extractor.v1")
    result = persist_verified_candidates(db, attempt.id, FormDCompanyProposer())
    attempts.mark_processed(db, attempt.id)
    candidate = result.candidates[0]
    promotion = company_promotion.create_company_from_candidate(db, candidate.id, HUMAN)
    return promotion.company_id


def _extract_financing_candidate(db, observation_id, company_id, *, processor_id="form_d_financing_extractor"):
    attempt = attempts.start_processing(db, observation_id, processor_id, f"{processor_id}.v1")
    [proposal] = propose_financing_from_form_d(_payload_for(db, observation_id), company_id)
    result = financing_candidates_repo.persist_financing_event_candidates(db, attempt.id, [proposal])
    attempts.mark_processed(db, attempt.id)
    return result.candidates[0]


def _payload_for(db, observation_id):
    from app.v2.repositories.observations import get_observation_by_id
    from app.v2.repositories.raw_payloads import get_raw_payload
    observation = get_observation_by_id(db, observation_id)
    return get_raw_payload(db, observation.observation.content_hash, verify=True)


# ---------------------------------------------------------------- idempotent ingestion / duplicate filings

def test_ingesting_the_identical_filing_twice_is_idempotent(migrated_db):
    """Increment 18.2's own required "idempotent repeated ingestion" and "duplicate filings" cases: the SAME
    filing, ingested twice with the SAME acquisition_key, must not create a second observation or payload."""
    _register_source(migrated_db)
    first = _ingest_filing(migrated_db, acquisition_key="same-run")
    second = _ingest_filing(migrated_db, acquisition_key="same-run")

    assert first.observation.id == second.observation.id
    assert first.payload_created is True
    assert second.payload_created is False
    assert second.observation_created is False
    assert second.is_replay is True


def test_ingesting_the_same_filing_with_a_different_acquisition_key_adds_a_sighting_not_a_duplicate(migrated_db):
    """A genuinely later, independent check of the same evidence (a new acquisition) is recorded as a new
    Sighting of the SAME Observation, not a duplicate document -- proves re-checking a filing later (e.g. a
    scheduled re-verification) never inflates the evidence record."""
    _register_source(migrated_db)
    first = _ingest_filing(migrated_db, acquisition_key="first-check")
    second = _ingest_filing(migrated_db, acquisition_key="second-check")

    assert first.observation.id == second.observation.id
    assert second.sighting_created is True
    assert second.is_replay is False


# ---------------------------------------------------------------- rejected candidates never reach canonical metrics

def test_rejected_financing_candidate_never_becomes_a_canonical_event_or_a_metric(migrated_db):
    """Increment 18.2's own required case: a rejected candidate must never enter canonical metrics."""
    _register_source(migrated_db)
    market = _setup_market(migrated_db)
    observation = _ingest_filing(migrated_db).observation
    company_id = _extract_and_create_company(migrated_db, observation.id)
    classify_company(migrated_db, company_id, market.id, TAXONOMY_VERSION, ClassificationRole.PRIMARY, HUMAN)

    candidate = _extract_financing_candidate(migrated_db, observation.id, company_id)
    financing_promotion.reject_candidate(migrated_db, candidate.id, HUMAN, "does_not_qualify")

    as_of = datetime(2025, 9, 23, tzinfo=timezone.utc)
    from app.v2.domain.capital_signal import build_windows
    current_window, _hist = build_windows(as_of)
    metrics = compute_capital_metrics_for_market(migrated_db, market.id, TAXONOMY_VERSION, current_window[0], current_window[1])
    signal = compute_capital_signal_for_market(migrated_db, market.id, TAXONOMY_VERSION, as_of)

    assert metrics.financing_activity == 0
    assert metrics.companies_funded == 0
    assert metrics.capital_deployed_by_currency == {}
    assert signal.overall.value == "insufficient_data"


def test_deferred_financing_candidate_also_never_reaches_canonical_metrics(migrated_db):
    """Same guarantee for defer (not final -- see app.v2.financing_resolution.promotion's own docstring), which
    also must not leak into metrics while unresolved."""
    _register_source(migrated_db)
    market = _setup_market(migrated_db)
    observation = _ingest_filing(migrated_db).observation
    company_id = _extract_and_create_company(migrated_db, observation.id)
    classify_company(migrated_db, company_id, market.id, TAXONOMY_VERSION, ClassificationRole.PRIMARY, HUMAN)

    candidate = _extract_financing_candidate(migrated_db, observation.id, company_id)
    financing_promotion.defer_candidate(migrated_db, candidate.id, HUMAN, "needs_more_evidence")

    as_of = datetime(2025, 9, 23, tzinfo=timezone.utc)
    from app.v2.domain.capital_signal import build_windows
    current_window, _hist = build_windows(as_of)
    metrics = compute_capital_metrics_for_market(migrated_db, market.id, TAXONOMY_VERSION, current_window[0], current_window[1])
    assert metrics.financing_activity == 0
    assert metrics.capital_deployed_by_currency == {}


# ---------------------------------------------------------------- insufficient market history

def test_a_single_real_event_yields_insufficient_data_not_a_fabricated_direction(migrated_db):
    """Increment 18.2's own required "insufficient market history" case: one real, canonical, verified-amount
    financing event is not enough history (needs >=3 non-zero historical windows -- capital_signal.v1) to claim
    any real direction; the signal says so honestly rather than reporting "stable" or any other guess."""
    _register_source(migrated_db)
    market = _setup_market(migrated_db)
    observation = _ingest_filing(migrated_db).observation
    company_id = _extract_and_create_company(migrated_db, observation.id)
    classify_company(migrated_db, company_id, market.id, TAXONOMY_VERSION, ClassificationRole.PRIMARY, HUMAN)

    candidate = _extract_financing_candidate(migrated_db, observation.id, company_id)
    from app.v2.domain.financing import FinancingDateKind
    financing_promotion.create_event_from_candidate(
        migrated_db, candidate.id, HUMAN, FactSelection(dates=(FinancingDateKind.FIRST_SALE_DATE,))
    )

    as_of = datetime(2025, 9, 23, tzinfo=timezone.utc)
    signal = compute_capital_signal_for_market(migrated_db, market.id, TAXONOMY_VERSION, as_of)
    assert signal.financing_activity.historical_nonzero_windows == 1  # the one real event really is counted once
    assert signal.overall.value == "insufficient_data"  # but one window is still not enough real history


# ---------------------------------------------------------------- the real, full happy path (both evidence documents)

SYNTHETIC_ANNOUNCEMENT = (FIXTURE_DIR / "synthetic_announcement_snippet.html").read_bytes()


def test_full_workflow_a_verified_round_amount_from_a_second_document_reaches_capital_deployed(migrated_db):
    """The complete Increment 18.2 path, reproducing the real development-database run in this increment's
    report: Form D candidate creates the event; a SECOND, human-guided candidate (a different, synthetic
    "announcement" document here, standing in for the real SiliconANGLE evidence used in the actual run) attaches
    to the SAME event and supplies verified_round_amount, which is what actually reaches Capital Deployed."""
    from app.v2.tools.manual_fact import build_manual_amount, locate_evidence
    from app.v2.domain.financing import AmountSemantics, FinancingEventCandidateProposal

    _register_source(migrated_db)
    sources.register_source(migrated_db, Source(
        source_key="media_funding_announcement", name="Reputable media funding announcement (manual upload)",
        source_type=SourceType.MEDIA_NEWS, collection_method=CollectionMethod.MANUAL_UPLOAD, url=None, is_active=True,
    ))
    market = _setup_market(migrated_db)

    form_d_observation = _ingest_filing(migrated_db).observation
    company_id = _extract_and_create_company(migrated_db, form_d_observation.id)
    classify_company(migrated_db, company_id, market.id, TAXONOMY_VERSION, ClassificationRole.PRIMARY, HUMAN)

    form_d_candidate = _extract_financing_candidate(migrated_db, form_d_observation.id, company_id)
    # Accept the Form D dates onto the canonical event -- metric placement into a period needs a date; without
    # one the event is correctly excluded from every window (see "events_excluded_missing_date" in
    # CapitalMetrics.diagnostics), which is honest but not what this test is demonstrating.
    from app.v2.domain.financing import FinancingDateKind
    event = financing_promotion.create_event_from_candidate(
        migrated_db, form_d_candidate.id, HUMAN, FactSelection(dates=(FinancingDateKind.FIRST_SALE_DATE, FinancingDateKind.FILING_DATE))
    )

    announcement = ingest_evidence(migrated_db, IngestionCommand(
        source_key="media_funding_announcement", source_record_identifier=None, observation_type="funding_announcement_article",
        event_time=None, observed_time=datetime.now(timezone.utc), collection_version="manual_upload.v1",
        collector_id="test_suite", declared_media_type=None, payload_bytes=SYNTHETIC_ANNOUNCEMENT, acquisition_key="announcement-run",
    )).observation
    attempt = attempts.start_processing(migrated_db, announcement.id, "manual_fact_entry", "manual_fact_entry.v1")
    headline = "Example Robotics Co. raises $42M Series B"
    amount = build_manual_amount(SYNTHETIC_ANNOUNCEMENT, semantics=AmountSemantics.ANNOUNCED_ROUND_AMOUNT,
                                 amount="42000000", currency_code="USD", evidence_substring=headline, occurrence=0)
    proposal = FinancingEventCandidateProposal(company_id=company_id, event_evidence=locate_evidence(SYNTHETIC_ANNOUNCEMENT, headline, occurrence=0), amounts=(amount,))
    announcement_candidate = financing_candidates_repo.persist_financing_event_candidates(migrated_db, attempt.id, [proposal]).candidates[0]
    attempts.mark_processed(migrated_db, attempt.id)

    result = financing_promotion.attach_candidate_to_event(
        migrated_db, announcement_candidate.id, event.financing_event_id, HUMAN, FactSelection(verified_round_amount=True)
    )
    assert result.accepted_verified_round_amount is True

    as_of = datetime(2025, 9, 23, tzinfo=timezone.utc)
    # The real event's first_sale_date (2025-05-15) falls in an earlier window than "now" -- the live
    # development-database run in this increment's report showed the identical placement for the identical
    # fixture and as_of date.
    signal = compute_capital_signal_for_market(migrated_db, market.id, TAXONOMY_VERSION, as_of)
    all_windows = (signal.current_window, *signal.historical_windows)
    deployed_totals = [
        window.metrics.capital_deployed_by_currency["USD"].minor_units
        for window in all_windows
        if "USD" in window.metrics.capital_deployed_by_currency
    ]
    assert deployed_totals == [42_000_000_00]  # exactly one window carries the real verified amount
