"""End-to-end Capital Signal: real canonical FinancingEvents, real primary classification, real 8-window history.
Exercises the repository orchestration (which reuses the Increment 12 engine) against real Postgres data."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.v2.classification import service as classification
from app.v2.domain.capital_signal import (
    CapitalDirection,
    ConcentrationTrend,
    HISTORICAL_WINDOW_COUNT,
    WINDOW_DURATION,
    build_windows,
)
from app.v2.domain.financing_resolution import FactSelection
from app.v2.domain.financing import FinancingDateKind
from app.v2.domain.taxonomy import ClassificationRole
from app.v2.financing_resolution import promotion
from app.v2.repositories import capital_signal as repo
from app.v2.repositories import financing_event_candidates as candidates
from app.v2.tests.db.financing_fakes import canonical_company, make_financing, start_attempt
from app.v2.tests.db.resolution_helpers import canonical_counts, untouched_snapshot
from app.v2.tests.db.financing_resolution_helpers import CANONICAL_TABLES
from app.v2.tests.db.taxonomy_fakes import ME, TV1, setup_taxonomy

pytestmark = pytest.mark.db

AS_OF = datetime(2026, 9, 21, tzinfo=timezone.utc)


def make_event(db, company, when, record_id, with_amount=True):
    """A canonical FinancingEvent for `company` whose announcement_date is exactly `when` -- built with the date
    baked into the evidence payload from the start (canonical facts are append-only; there is no way to
    'move' one after creation, by design)."""
    from app.v2.domain.financing import AmountSemantics, Stage as S
    from app.v2.domain.time import EventTime
    date_str = when.date().isoformat()
    payload = f"Acme Robotics announced a $20 million Series A financing on {date_str} (ref {record_id}).".encode()
    _, attempt = start_attempt(db, payload, record_id=record_id)
    proposal = make_financing(payload, company, event=b"announced a", stage=(S.SERIES_A, b"Series A"),
                              amounts=[(AmountSemantics.ANNOUNCED_ROUND_AMOUNT, "20000000", "USD", b"$20 million")],
                              dates=[(FinancingDateKind.ANNOUNCEMENT_DATE, EventTime.of_day(when.year, when.month, when.day), date_str.encode())])
    candidate = candidates.persist_financing_event_candidates(db, attempt.id, [proposal]).candidates[0]
    facts = FactSelection(dates=(FinancingDateKind.ANNOUNCEMENT_DATE,), verified_round_amount=with_amount)
    return promotion.create_event_from_candidate(db, candidate.id, ME, facts).financing_event_id


@pytest.fixture
def world(migrated_db):
    db = migrated_db
    taxonomy = setup_taxonomy(db, ("robotics", "Robotics"))
    company = canonical_company(db)
    classification.classify_company(db, company, taxonomy["robotics"].id, TV1, ClassificationRole.PRIMARY, ME)
    return db, taxonomy["robotics"], company


def run(db, market):
    return repo.compute_capital_signal_for_market(db, market.id, TV1, AS_OF)


# ---------------- attribution is inherited from Increment 12 (real data)

def test_a_financing_attributed_through_primary_classification_appears_in_the_correct_window(world):
    db, market, company = world
    current_start, current_end = build_windows(AS_OF)[0]
    make_event(db, company, current_start, "cw-1")
    result = run(db, market)
    assert result.current_window.metrics.financing_activity == 1


def test_secondary_classification_never_leaks_into_a_capital_signal(migrated_db):
    db = migrated_db
    taxonomy = setup_taxonomy(db, ("robotics", "Robotics"), ("ai-infrastructure", "AI Infrastructure"))
    company = canonical_company(db)
    classification.classify_company(db, company, taxonomy["robotics"].id, TV1, ClassificationRole.PRIMARY, ME)
    classification.classify_company(db, company, taxonomy["ai-infrastructure"].id, TV1, ClassificationRole.SECONDARY, ME)
    current_start, _ = build_windows(AS_OF)[0]
    make_event(db, company, current_start, "sec-1")
    assert repo.compute_capital_signal_for_market(db, taxonomy["ai-infrastructure"].id, TV1, AS_OF).current_window.metrics.financing_activity == 0
    assert repo.compute_capital_signal_for_market(db, taxonomy["robotics"].id, TV1, AS_OF).current_window.metrics.financing_activity == 1


def test_only_verified_round_amount_ever_reaches_the_signal_never_candidate_facts(world):
    db, market, company = world
    current_start, _ = build_windows(AS_OF)[0]
    make_event(db, company, current_start, "amt-1", with_amount=False)   # no verified amount accepted
    result = run(db, market)
    assert result.current_window.metrics.capital_deployed_by_currency == {}


# ---------------- broad, real-data scenario: historically ordinary current window

def test_current_window_historically_ordinary_yields_stable(world):
    db, market, company = world
    _, historical = build_windows(AS_OF)
    for i, (start, _) in enumerate(historical):
        for j in range(2):
            make_event(db, company, start, f"hist-{i}-{j}")
    current_start, _ = build_windows(AS_OF)[0]
    for j in range(2):
        make_event(db, company, current_start, f"cur-{j}")
    result = run(db, market)
    assert result.financing_activity.direction is CapitalDirection.STABLE
    assert result.companies_funded.direction is CapitalDirection.STABLE


def test_current_window_historically_high_yields_increase_or_strong_increase(world):
    db, market, company = world
    _, historical = build_windows(AS_OF)
    for i, (start, _) in enumerate(historical):
        make_event(db, company, start, f"hist-{i}")
    current_start, _ = build_windows(AS_OF)[0]
    for j in range(10):
        make_event(db, company, current_start, f"cur-{j}")
    result = run(db, market)
    assert result.financing_activity.direction in (CapitalDirection.INCREASE, CapitalDirection.STRONG_INCREASE)


def test_current_window_historically_low_yields_decrease_or_strong_decrease(world):
    db, market, company = world
    _, historical = build_windows(AS_OF)
    for i, (start, _) in enumerate(historical):
        for j in range(5):
            make_event(db, company, start, f"hist-{i}-{j}")
    result = run(db, market)   # nothing in the current window at all
    assert result.financing_activity.direction in (CapitalDirection.DECREASE, CapitalDirection.STRONG_DECREASE)


def test_robust_against_one_extreme_historical_outlier(world):
    db, market, company = world
    _, historical = build_windows(AS_OF)
    for i, (start, _) in enumerate(historical):
        make_event(db, company, start, f"hist-{i}")
    # the most extreme historical window ALSO gets a giant additional event (an outlier in COUNT, mirroring $)
    extreme_start = historical[0][0]
    for j in range(50):
        make_event(db, company, extreme_start, f"outlier-{j}", with_amount=False)
    current_start, _ = build_windows(AS_OF)[0]
    for j in range(1):
        make_event(db, company, current_start, "cur-1")
    result = run(db, market)
    # current (1 event) sits in the ordinary middle of {1,1,1,1,1,1,1,51}: outlier magnitude must not distort the rank
    assert result.financing_activity.direction in (CapitalDirection.STABLE, CapitalDirection.DECREASE)


# ---------------- companies funded: distinct-company semantics inherited from Increment 12

def test_companies_funded_counts_distinct_companies_even_with_many_events(world):
    db, market, company = world
    _, historical = build_windows(AS_OF)
    for i, (start, _) in enumerate(historical):
        for j in range(3):
            make_event(db, company, start, f"cf-hist-{i}-{j}")   # same company, many events per window
    current_start, _ = build_windows(AS_OF)[0]
    for j in range(3):
        make_event(db, company, current_start, f"cf-cur-{j}")
    result = run(db, market)
    assert all(v == 1 for v in result.companies_funded.historical_values)   # always ONE company funded, regardless of event count
    assert result.companies_funded.current_value == 1
    assert result.companies_funded.direction is CapitalDirection.STABLE   # (1 always equals 1: zero variance -> midpoint -> stable)


# ---------------- multi-currency

def test_currencies_are_never_combined_in_the_signal(migrated_db):
    db = migrated_db
    from app.v2.tests.db.financing_fakes import make_financing
    from app.v2.domain.financing import AmountSemantics, Stage as S
    from app.v2.domain.time import EventTime
    taxonomy = setup_taxonomy(db, ("robotics", "Robotics"))
    company = canonical_company(db)
    classification.classify_company(db, company, taxonomy["robotics"].id, TV1, ClassificationRole.PRIMARY, ME)
    current_start, _ = build_windows(AS_OF)[0]

    def eur_event(when, record_id):
        date_str = when.date().isoformat()
        payload = f"Acme Robotics announced an 8 million euro Series A financing on {date_str} (ref {record_id}).".encode()
        _, attempt = start_attempt(db, payload, record_id=record_id)
        proposal = make_financing(payload, company, event=b"announced an", stage=(S.SERIES_A, b"Series A"),
                                  amounts=[(AmountSemantics.ANNOUNCED_ROUND_AMOUNT, "8000000", "EUR", b"8 million euro")],
                                  dates=[(FinancingDateKind.ANNOUNCEMENT_DATE, EventTime.of_day(when.year, when.month, when.day), date_str.encode())])
        c = candidates.persist_financing_event_candidates(db, attempt.id, [proposal]).candidates[0]
        promotion.create_event_from_candidate(db, c.id, ME, FactSelection(verified_round_amount=True, dates=(FinancingDateKind.ANNOUNCEMENT_DATE,)))

    make_event(db, company, current_start, "usd-cur")
    eur_event(current_start, "eur-cur")
    _, historical = build_windows(AS_OF)
    for i, (start, _) in enumerate(historical):
        make_event(db, company, start, f"usd-hist-{i}")
        eur_event(start, f"eur-hist-{i}")

    result = run(db, taxonomy["robotics"])
    by_currency = {c.currency_code: c for c in result.capital_deployed}
    assert set(by_currency) == {"USD", "EUR"}
    for c in result.capital_deployed:
        assert c.currency_code in ("USD", "EUR")


# ---------------- preservation

def test_computing_a_signal_mutates_nothing(world):
    db, market, company = world
    current_start, _ = build_windows(AS_OF)[0]
    make_event(db, company, current_start, "pres-1")
    before_canonical = canonical_counts(db)
    before_evidence = untouched_snapshot(db)
    with db.connect() as conn:
        before_financing = {t: conn.execute(text(f"SELECT count(*) FROM v2.{t}")).scalar() for t in CANONICAL_TABLES}
        before_classification = conn.execute(text("SELECT count(*) FROM v2.company_market_classification")).scalar()
    run(db, market)
    run(db, market)   # twice, to also prove idempotent reads
    assert canonical_counts(db) == before_canonical and untouched_snapshot(db) == before_evidence
    with db.connect() as conn:
        after_financing = {t: conn.execute(text(f"SELECT count(*) FROM v2.{t}")).scalar() for t in CANONICAL_TABLES}
        after_classification = conn.execute(text("SELECT count(*) FROM v2.company_market_classification")).scalar()
    assert after_financing == before_financing and after_classification == before_classification


def test_reproducible_same_inputs_same_signal(world):
    db, market, company = world
    current_start, _ = build_windows(AS_OF)[0]
    make_event(db, company, current_start, "repro-1")
    assert run(db, market) == run(db, market)
