"""Shared fixtures for the Capital API tests: a real canonical FinancingEvent whose announcement_date is exactly
the date requested, built the same way Increment 13's own repository tests build one (canonical facts are
append-only -- there is no way to place an event in a specific window except by baking the date into its
evidence from the start)."""

from app.v2.domain.financing import AmountSemantics, FinancingDateKind, Stage
from app.v2.domain.financing_resolution import FactSelection
from app.v2.domain.resolution import human_authority
from app.v2.domain.time import EventTime
from app.v2.financing_resolution import promotion
from app.v2.repositories import financing_event_candidates as candidates
from app.v2.tests.db.financing_fakes import make_financing, start_attempt
from app.v2.tests.db.taxonomy_fakes import HUMAN

ME = human_authority(HUMAN)


def make_priced_event(db, company, when, record_id, *, amount="20000000", currency="USD", with_amount=True, with_stage=True):
    """A canonical FinancingEvent for `company`: announced_round_amount (default $20M USD), Series A (if
    with_stage), dated exactly `when` (UTC midnight)."""
    date_str = when.date().isoformat()
    amount_needle = f"${amount}".encode()
    payload = f"Acme Robotics announced a ${amount} Series A financing on {date_str} (ref {record_id}) currency {currency}.".encode()
    _, attempt = start_attempt(db, payload, record_id=record_id)
    proposal = make_financing(
        payload, company, event=b"announced a", stage=(Stage.SERIES_A, b"Series A"),
        amounts=[(AmountSemantics.ANNOUNCED_ROUND_AMOUNT, amount, currency, amount_needle)],
        dates=[(FinancingDateKind.ANNOUNCEMENT_DATE, EventTime.of_day(when.year, when.month, when.day), date_str.encode())],
    )
    candidate = candidates.persist_financing_event_candidates(db, attempt.id, [proposal]).candidates[0]
    facts = FactSelection(dates=(FinancingDateKind.ANNOUNCEMENT_DATE,), verified_round_amount=with_amount, stage=with_stage)
    return promotion.create_event_from_candidate(db, candidate.id, ME, facts).financing_event_id


def make_undated_event(db, company, record_id, *, amount="5000000"):
    """A canonical FinancingEvent with NO canonical date accepted at all (a candidate proposed one, but it was
    never accepted) -- exercises the 'events exist but are missing dates' diagnostic honestly."""
    payload = f"Acme Robotics announced a ${amount} financing in 2026 (ref {record_id}).".encode()
    _, attempt = start_attempt(db, payload, record_id=record_id)
    proposal = make_financing(
        payload, company, event=b"announced a",
        amounts=[(AmountSemantics.ANNOUNCED_ROUND_AMOUNT, amount, "USD", f"${amount}".encode())],
        dates=[(FinancingDateKind.ANNOUNCEMENT_DATE, EventTime.of_day(2026, 1, 1), b"2026")],
    )
    candidate = candidates.persist_financing_event_candidates(db, attempt.id, [proposal]).candidates[0]
    return promotion.create_event_from_candidate(db, candidate.id, ME, FactSelection(verified_round_amount=True)).financing_event_id
