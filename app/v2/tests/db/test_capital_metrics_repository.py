"""End-to-end Capital metrics: canonical Company -> primary classification -> canonical FinancingEvent -> metrics.
Exercises the real repository query layer feeding the pure engine against real Postgres data."""

from datetime import datetime, timezone
from fractions import Fraction

import pytest
from sqlalchemy import text

from app.v2.classification import service as classification
from app.v2.domain.financing import AmountSemantics, FinancingDateKind, Stage
from app.v2.domain.financing_resolution import FactSelection
from app.v2.domain.taxonomy import ClassificationRole
from app.v2.repositories import capital_metrics as repo
from app.v2.repositories import markets
from app.v2.financing_resolution import promotion
from app.v2.tests.db.financing_fakes import ANNOUNCEMENT, FORM_D, announcement, canonical_company, form_d, start_attempt
from app.v2.tests.db.financing_resolution_helpers import CANONICAL_TABLES
from app.v2.tests.db.resolution_helpers import canonical_counts, untouched_snapshot
from app.v2.repositories import financing_event_candidates as candidates
from app.v2.tests.db.taxonomy_fakes import ME, TV1, TV2, setup_taxonomy

pytestmark = pytest.mark.db

PRIMARY, SECONDARY = ClassificationRole.PRIMARY, ClassificationRole.SECONDARY


def dt(y, m=1, d=1):
    return datetime(y, m, d, tzinfo=timezone.utc)


def make_event(db, company, payload, *, facts=FactSelection(verified_round_amount=True, stage=True, dates=(FinancingDateKind.ANNOUNCEMENT_DATE,)), record_id=None):
    """A canonical FinancingEvent (created + facts accepted) for `company`, from an announcement-shaped payload."""
    _, attempt = start_attempt(db, payload, record_id=record_id)
    candidate = candidates.persist_financing_event_candidates(db, attempt.id, [announcement(company, payload)]).candidates[0]
    return promotion.create_event_from_candidate(db, candidate.id, ME, facts).financing_event_id


@pytest.fixture
def world(migrated_db):
    db = migrated_db
    taxonomy = setup_taxonomy(db, ("robotics", "Robotics"), ("ai-infrastructure", "AI Infrastructure"))
    return db, taxonomy


def classify(db, company, market, tv=TV1, role=PRIMARY):
    classification.classify_company(db, company, market.id, tv, role, ME)


def run(db, market_id, tv=TV1, start=dt(2026, 1, 1), end=dt(2027, 1, 1)):
    return repo.compute_capital_metrics_for_market(db, market_id, tv, start, end)


# ---------------- attribution: primary owns it, secondary never does

def test_a_financing_is_attributed_through_the_companys_primary_market(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT)
    result = run(db, taxonomy["robotics"].id)
    assert result.financing_activity == 1
    assert run(db, taxonomy["ai-infrastructure"].id).financing_activity == 0


def test_secondary_classification_never_receives_primary_capital_attribution(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"], role=PRIMARY)
    classify(db, company, taxonomy["ai-infrastructure"], role=SECONDARY)
    make_event(db, company, ANNOUNCEMENT)
    assert run(db, taxonomy["robotics"].id).financing_activity == 1
    assert run(db, taxonomy["ai-infrastructure"].id).financing_activity == 0    # the secondary market: nothing


def test_the_same_financing_is_never_double_counted_across_two_markets(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"], role=PRIMARY)
    classify(db, company, taxonomy["ai-infrastructure"], role=SECONDARY)
    make_event(db, company, ANNOUNCEMENT, facts=FactSelection(verified_round_amount=True, dates=(FinancingDateKind.ANNOUNCEMENT_DATE,)))
    total_deployed = sum(m.capital_deployed_by_currency.get("USD").minor_units if m.capital_deployed_by_currency.get("USD") else 0
                         for m in (run(db, taxonomy["robotics"].id), run(db, taxonomy["ai-infrastructure"].id)))
    assert total_deployed == 2_000_000_000                                       # counted once total, not twice


def test_a_financing_candidate_never_stores_a_market_id(migrated_db):
    with migrated_db.connect() as conn:
        columns = {r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name='financing_event'"))}
    assert "market_id" not in columns


def test_no_company_with_no_classification_is_ever_attributed(world):
    db, taxonomy = world
    company = canonical_company(db)
    make_event(db, company, ANNOUNCEMENT)                                        # no classification at all
    assert run(db, taxonomy["robotics"].id).financing_activity == 0


def test_changing_taxonomy_version_can_change_attribution_without_mutating_the_old_version(world):
    db, taxonomy = world
    markets.register_taxonomy_version(db, TV2)
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"], tv=TV1, role=PRIMARY)
    classify(db, company, taxonomy["ai-infrastructure"], tv=TV2, role=PRIMARY)
    make_event(db, company, ANNOUNCEMENT)
    assert run(db, taxonomy["robotics"].id, tv=TV1).financing_activity == 1
    assert run(db, taxonomy["ai-infrastructure"].id, tv=TV2).financing_activity == 1
    assert run(db, taxonomy["ai-infrastructure"].id, tv=TV1).financing_activity == 0   # v1 attribution is untouched
    assert run(db, taxonomy["robotics"].id, tv=TV2).financing_activity == 0


# ---------------- financing activity / companies funded

def test_one_canonical_event_counts_once_no_matter_how_many_candidates_attached(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    event_id = make_event(db, company, ANNOUNCEMENT, record_id="a")
    for i, payload in enumerate((FORM_D, ANNOUNCEMENT), start=1):
        _, attempt = start_attempt(db, payload, record_id=f"extra-{i}")
        c = candidates.persist_financing_event_candidates(
            db, attempt.id, [form_d(company) if payload is FORM_D else announcement(company, payload)]).candidates[0]
        promotion.attach_candidate_to_event(db, c.id, event_id, ME)
    assert run(db, taxonomy["robotics"].id).financing_activity == 1


def test_three_canonical_events_count_three(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    for i in range(3):
        make_event(db, company, ANNOUNCEMENT, record_id=f"three-{i}")
    assert run(db, taxonomy["robotics"].id).financing_activity == 3


def test_multiple_events_for_one_company_count_one_company_funded(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    for i in range(3):
        make_event(db, company, ANNOUNCEMENT, record_id=f"cf-{i}")
    result = run(db, taxonomy["robotics"].id)
    assert result.financing_activity == 3 and result.companies_funded == 1


def test_multiple_companies_count_distinctly(world):
    db, taxonomy = world
    c1, c2 = canonical_company(db, "One Co", "one.example"), canonical_company(db, "Two Co", "two.example")
    classify(db, c1, taxonomy["robotics"])
    classify(db, c2, taxonomy["robotics"])
    make_event(db, c1, ANNOUNCEMENT, record_id="mc-1")
    make_event(db, c2, ANNOUNCEMENT, record_id="mc-2")
    result = run(db, taxonomy["robotics"].id)
    assert result.financing_activity == 2 and result.companies_funded == 2


# ---------------- capital deployed

def test_verified_amounts_summed_and_candidate_only_amounts_ignored(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT, facts=FactSelection(verified_round_amount=True, dates=(FinancingDateKind.ANNOUNCEMENT_DATE,)))      # verified: $20M USD
    _, attempt = start_attempt(db, FORM_D)                                                      # a Form D candidate: never accepted
    candidates.persist_financing_event_candidates(db, attempt.id, [form_d(company)])
    result = run(db, taxonomy["robotics"].id)
    assert result.capital_deployed_by_currency["USD"].minor_units == 2_000_000_000              # only the accepted $20M


def test_offering_and_amount_sold_are_never_counted_as_deployed_capital(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    _, attempt = start_attempt(db, FORM_D)
    candidate = candidates.persist_financing_event_candidates(db, attempt.id, [form_d(company)]).candidates[0]
    promotion.create_event_from_candidate(db, candidate.id, ME, FactSelection(dates=(FinancingDateKind.FIRST_SALE_DATE,)))   # only a date accepted
    result = run(db, taxonomy["robotics"].id)
    assert result.financing_activity == 1 and result.capital_deployed_by_currency == {}          # $25M offering / $18M sold: never counted


def test_an_event_without_verified_amount_still_counts_as_activity(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT, facts=FactSelection(dates=(FinancingDateKind.ANNOUNCEMENT_DATE,)))
    result = run(db, taxonomy["robotics"].id)
    assert result.financing_activity == 1 and result.diagnostics.events_without_verified_amount == 1


def test_capital_deployed_arithmetic_is_exact_integer_no_float(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT, record_id="x1")
    result = run(db, taxonomy["robotics"].id)
    assert type(result.capital_deployed_by_currency["USD"].minor_units) is int


# ---------------- multi-currency and concentration

def test_multi_currency_totals_are_never_summed_together(world):
    db, taxonomy = world
    from app.v2.domain.financing import AmountSemantics as AS
    from app.v2.domain.financing import Stage as S
    from app.v2.domain.time import EventTime
    from app.v2.tests.db.financing_fakes import make_financing
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT, record_id="usd-1")                                     # $20M USD
    eur_payload = b"Acme Robotics announced an 8 million euro Series A financing in March 2026."
    _, attempt = start_attempt(db, eur_payload, record_id="eur-1")
    proposal = make_financing(eur_payload, company, event=b"announced an", stage=(S.SERIES_A, b"Series A"),
                              amounts=[(AS.ANNOUNCED_ROUND_AMOUNT, "8000000", "EUR", b"8 million euro")],
                              dates=[(FinancingDateKind.ANNOUNCEMENT_DATE, EventTime.of_month(2026, 3), b"March 2026")])
    c = candidates.persist_financing_event_candidates(db, attempt.id, [proposal]).candidates[0]
    promotion.create_event_from_candidate(db, c.id, ME, FactSelection(verified_round_amount=True, dates=(FinancingDateKind.ANNOUNCEMENT_DATE,)))
    result = run(db, taxonomy["robotics"].id)
    assert result.capital_deployed_by_currency["USD"].minor_units == 2_000_000_000
    assert result.capital_deployed_by_currency["EUR"].minor_units == 800_000_000
    assert result.capital_concentration_by_currency["USD"].share == Fraction(1, 1)
    assert result.capital_concentration_by_currency["EUR"].share == Fraction(1, 1)


def test_concentration_across_two_financings_in_one_currency(world):
    db, taxonomy = world
    from app.v2.tests.db.financing_fakes import CONFLICTING
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT, record_id="cc-1")                                       # $20M
    make_event(db, company, CONFLICTING, record_id="cc-2")                                        # $25M (announcement() defaults 20M; override below)
    result = run(db, taxonomy["robotics"].id)
    total = result.capital_deployed_by_currency["USD"].minor_units
    assert total == 4_000_000_000                                                                  # both default to $20M in this helper
    assert result.capital_concentration_by_currency["USD"].share == Fraction(1, 2)


def test_no_verified_capital_means_concentration_is_absent(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT, facts=FactSelection())
    result = run(db, taxonomy["robotics"].id)
    assert result.capital_concentration_by_currency == {}


# ---------------- stage distribution

def test_canonical_stage_is_counted_candidate_only_stage_is_ignored(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT, facts=FactSelection(stage=True, dates=(FinancingDateKind.ANNOUNCEMENT_DATE,)))    # accepted: series_a
    make_event(db, company, ANNOUNCEMENT, facts=FactSelection(dates=(FinancingDateKind.ANNOUNCEMENT_DATE,)), record_id="unacc-1")   # stage PROPOSED but never accepted
    result = run(db, taxonomy["robotics"].id)
    assert result.stage_distribution == {Stage.SERIES_A: 1, Stage.UNKNOWN: 1}


def test_stage_is_never_inferred_from_amount_in_real_data(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT, facts=FactSelection(verified_round_amount=True, dates=(FinancingDateKind.ANNOUNCEMENT_DATE,)))   # $20M accepted, stage NOT
    result = run(db, taxonomy["robotics"].id)
    assert result.stage_distribution == {Stage.UNKNOWN: 1}


# ---------------- date policy

def test_events_with_no_usable_canonical_date_are_excluded_with_a_diagnostic(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT, facts=FactSelection())                                   # no dates accepted
    result = run(db, taxonomy["robotics"].id)
    assert result.financing_activity == 0 and result.diagnostics.events_excluded_missing_date == 1


def test_announcement_date_is_used_when_accepted(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT, facts=FactSelection(dates=(FinancingDateKind.ANNOUNCEMENT_DATE,)))
    assert run(db, taxonomy["robotics"].id, start=dt(2026, 3, 1), end=dt(2026, 4, 1)).financing_activity == 1


def test_first_sale_date_fallback_when_announcement_not_accepted(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    _, attempt = start_attempt(db, FORM_D)
    candidate = candidates.persist_financing_event_candidates(db, attempt.id, [form_d(company)]).candidates[0]
    promotion.create_event_from_candidate(db, candidate.id, ME, FactSelection(dates=(FinancingDateKind.FIRST_SALE_DATE,)))
    assert run(db, taxonomy["robotics"].id, start=dt(2026, 3, 1), end=dt(2026, 3, 16)).financing_activity == 1


def test_filing_date_used_only_as_a_last_resort(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    _, attempt = start_attempt(db, FORM_D)
    candidate = candidates.persist_financing_event_candidates(db, attempt.id, [form_d(company)]).candidates[0]
    promotion.create_event_from_candidate(db, candidate.id, ME, FactSelection(dates=(FinancingDateKind.FILING_DATE,)))
    assert run(db, taxonomy["robotics"].id, start=dt(2026, 4, 1), end=dt(2026, 4, 3)).financing_activity == 1


def test_observed_time_is_never_used_as_a_financing_date(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT, facts=FactSelection())                # no canonical date at all
    # even though the Observation was observed "now" (2026), a period covering "now" must NOT include this event
    result = run(db, taxonomy["robotics"].id, start=dt(2020, 1, 1), end=dt(2030, 1, 1))
    assert result.financing_activity == 0 and result.diagnostics.events_excluded_missing_date == 1


def test_exact_period_boundary_behavior_half_open(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT, facts=FactSelection(dates=(FinancingDateKind.ANNOUNCEMENT_DATE,)))   # March 2026 -> month start = 2026-03-01
    assert run(db, taxonomy["robotics"].id, start=dt(2026, 3, 1), end=dt(2026, 4, 1)).financing_activity == 1   # start inclusive
    assert run(db, taxonomy["robotics"].id, start=dt(2026, 2, 1), end=dt(2026, 3, 1)).financing_activity == 0   # end exclusive


# ---------------- diagnostics

def test_diagnostics_expose_missing_date_missing_amount_and_unknown_stage_counts(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT, facts=FactSelection(dates=(FinancingDateKind.ANNOUNCEMENT_DATE,)), record_id="d1")           # in period, no amount/stage
    make_event(db, company, ANNOUNCEMENT, facts=FactSelection(), record_id="d2")                                                        # no date at all
    result = run(db, taxonomy["robotics"].id)
    assert result.diagnostics.events_considered == 2
    assert result.diagnostics.events_included == 1
    assert result.diagnostics.events_excluded_missing_date == 1
    assert result.diagnostics.events_without_verified_amount == 1
    assert result.diagnostics.events_without_known_stage == 1


# ---------------- preservation

def test_computing_metrics_mutates_nothing(world):
    db, taxonomy = world
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_event(db, company, ANNOUNCEMENT)
    before_canonical = canonical_counts(db)
    before_evidence = untouched_snapshot(db)
    with db.connect() as conn:
        before_financing = {t: conn.execute(text(f"SELECT count(*) FROM v2.{t}")).scalar() for t in CANONICAL_TABLES}
        before_classification = conn.execute(text("SELECT count(*) FROM v2.company_market_classification")).scalar()
    run(db, taxonomy["robotics"].id)
    run(db, taxonomy["ai-infrastructure"].id)
    assert canonical_counts(db) == before_canonical and untouched_snapshot(db) == before_evidence
    with db.connect() as conn:
        after_financing = {t: conn.execute(text(f"SELECT count(*) FROM v2.{t}")).scalar() for t in CANONICAL_TABLES}
        after_classification = conn.execute(text("SELECT count(*) FROM v2.company_market_classification")).scalar()
    assert after_financing == before_financing and after_classification == before_classification
