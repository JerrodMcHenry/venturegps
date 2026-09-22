"""Deterministic financing-candidate fixtures for the Capital tests. No AI, no network, no extractor: the
proposals are built by hand from exact payload bytes, the way a future extractor would have to."""

import itertools
from decimal import Decimal

from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.financing import (
    AmountSemantics,
    FinancingDateKind,
    FinancingEventCandidateProposal,
    FinancingType,
    Money,
    ProposedAmount,
    ProposedFinancingDate,
    ProposedFinancingType,
    ProposedStage,
    Stage,
)
from app.v2.domain.time import EventTime
from app.v2.observations.hashing import compute_content_hash
from app.v2.repositories import processing_attempts as attempts
from app.v2.resolution import promotion
from app.v2.domain.resolution import human_authority
from app.v2.tests.db.evidence_helpers import ingest_one
from app.v2.tests.db.resolution_helpers import HUMAN, make_candidate

FORM_D = (b"SEC Form D notice. Issuer: Acme Robotics, Inc. Type of securities offered: Equity. "
          b"Date of first sale: 2026-03-15. Date filed: 2026-04-02. "
          b"Total offering amount: $10,000,000. Total amount sold: $7,000,000.")
ANNOUNCEMENT = (b"Acme Robotics announced a $20 million Series A financing in March 2026. "
                b"The company previously closed a seed round.")
SEED_NEWS = b"Acme Robotics closed a $2 million seed round, the startup said on 2025-11-04 in a pre-seed retrospective."
CONFLICTING = b"Acme Robotics announced a $25 million Series A financing in April 2026."

_counter = itertools.count(1)


def locate(payload: bytes, needle: bytes, *, before: int = 0, after: int = 0) -> EvidenceLocator:
    index = payload.index(needle)
    start, end = max(0, index - before), min(len(payload), index + len(needle) + after)
    return EvidenceLocator(byte_start=start, byte_end=end, evidence_hash=compute_content_hash(payload[start:end]))


def make_financing(payload: bytes, company_id, *, event=b"SEC Form D", stage=None, ftype=None, amounts=(), dates=(), pad=4):
    """stage=(Stage, needle) ftype=(FinancingType, needle) amounts=[(AmountSemantics, "10000000", "USD", needle)]
    dates=[(FinancingDateKind, EventTime, needle)]"""
    return FinancingEventCandidateProposal(
        company_id=company_id, event_evidence=locate(payload, event, before=pad, after=pad),
        stage=ProposedStage(stage=stage[0], evidence=locate(payload, stage[1], before=pad, after=pad)) if stage else None,
        financing_type=ProposedFinancingType(financing_type=ftype[0], evidence=locate(payload, ftype[1], before=pad, after=pad)) if ftype else None,
        amounts=tuple(ProposedAmount(semantics=s, money=Money.from_decimal(Decimal(v), c), evidence=locate(payload, n, before=pad, after=pad))
                      for s, v, c, n in amounts),
        dates=tuple(ProposedFinancingDate(kind=k, time=t, evidence=locate(payload, n, before=pad, after=pad)) for k, t, n in dates),
    )


def form_d(company_id, payload=FORM_D):
    return make_financing(
        payload, company_id, event=b"SEC Form D notice", ftype=(FinancingType.EQUITY, b"Equity"),
        amounts=[(AmountSemantics.OFFERING_AMOUNT, "10000000", "USD", b"$10,000,000"), (AmountSemantics.AMOUNT_SOLD, "7000000", "USD", b"$7,000,000")],
        dates=[(FinancingDateKind.FIRST_SALE_DATE, EventTime.of_day(2026, 3, 15), b"2026-03-15"),
               (FinancingDateKind.FILING_DATE, EventTime.of_day(2026, 4, 2), b"2026-04-02")])


def announcement(company_id, payload=ANNOUNCEMENT, amount="20000000"):
    needle = b"$20 million" if b"$20 million" in payload else b"$25 million"
    month = (3, b"March 2026") if b"March 2026" in payload else (4, b"April 2026")
    return make_financing(
        payload, company_id, event=b"announced a", stage=(Stage.SERIES_A, b"Series A"),
        amounts=[(AmountSemantics.ANNOUNCED_ROUND_AMOUNT, amount, "USD", needle)],
        dates=[(FinancingDateKind.ANNOUNCEMENT_DATE, EventTime.of_month(2026, month[0]), month[1])])


def canonical_company(db, name="Acme Robotics, Inc.", domain="acmerobotics.com"):
    """A REAL canonical Company, made the only way one can be: candidate -> human ResolutionDecision -> Company."""
    return promotion.create_company_from_candidate(db, make_candidate(db, name, domain=domain).id, human_authority(HUMAN)).company_id


def start_attempt(db, payload: bytes, *, record_id=None):
    n = next(_counter)
    observation = ingest_one(db, record_id=record_id or f"fin-{n}", payload=payload, key=f"fin-run-{n}").observation
    return observation, attempts.start_processing(db, observation.id, f"fin_extractor_{n}", f"fin_extractor_{n}.v1")
