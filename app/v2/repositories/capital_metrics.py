"""
The Capital metrics query layer: reads canonical data and assembles the immutable inputs the pure engine
(app.v2.domain.capital_metrics) needs. Read-only -- nothing here writes.

    get_primary_attributed_financing_events(db, market_id, taxonomy_version) -> list[CapitalEventInput]
    compute_capital_metrics_for_market(db, market_id, taxonomy_version, period_start, period_end) -> CapitalMetrics

Attribution is derived, never stored: a FinancingEvent belongs to a Company (a real FK), and a Company's PRIMARY
classification into a Market (under the requested taxonomy version) is what attributes its financings to that
Market. SECONDARY classifications are never joined here -- they contribute nothing to Capital metrics, so the same
financing can never be double-counted across two Markets. `financing_event.market_id` does not exist and never
will: attribution is always looked up through the classification, not copied onto the event.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine

from app.v2.db.tables import company_market_classification_table as cmc
from app.v2.db.tables import financing_event_date_table as fed
from app.v2.db.tables import financing_event_stage_table as fes
from app.v2.db.tables import financing_event_table as fe
from app.v2.db.tables import financing_event_verified_round_amount_table as fev
from app.v2.domain.capital_metrics import CapitalEventInput, CapitalMetrics, choose_metric_date, compute_capital_metrics
from app.v2.domain.financing import FinancingDateKind, Money, Stage
from app.v2.domain.time import EventTime, EventTimePrecision
from app.v2.repositories._db import connection as _connection


def get_primary_attributed_financing_events(db: Engine | Connection, market_id: UUID, taxonomy_version: str) -> list[CapitalEventInput]:
    """Every canonical FinancingEvent whose Company holds a PRIMARY classification into `market_id` under
    `taxonomy_version` -- regardless of period or date availability; the pure engine decides qualification."""
    with _connection(db) as connection:
        events = connection.execute(
            select(fe.c.id, fe.c.company_id, fev.c.currency_code, fev.c.amount_minor_units, fes.c.stage)
            .select_from(fe.join(cmc, (cmc.c.company_id == fe.c.company_id) & (cmc.c.role == "primary")
                                 & (cmc.c.taxonomy_version == taxonomy_version) & (cmc.c.market_id == market_id))
                         .outerjoin(fev, fev.c.financing_event_id == fe.c.id)
                         .outerjoin(fes, fes.c.financing_event_id == fe.c.id))
        ).all()
        if not events:
            return []
        ids = [r.id for r in events]
        dates: dict[UUID, dict[FinancingDateKind, EventTime]] = {i: {} for i in ids}
        for r in connection.execute(select(fed.c.financing_event_id, fed.c.date_kind, fed.c.date_precision, fed.c.date_start)
                                    .where(fed.c.financing_event_id.in_(ids))):
            dates[r.financing_event_id][FinancingDateKind(r.date_kind)] = EventTime(
                precision=EventTimePrecision(r.date_precision), start=r.date_start)

    inputs = []
    for r in events:
        chosen = choose_metric_date(dates[r.id])
        inputs.append(CapitalEventInput(
            financing_event_id=r.id, company_id=r.company_id,
            metric_date=chosen[1].start if chosen else None, metric_date_kind=chosen[0] if chosen else None,
            verified_round_amount=None if r.currency_code is None else Money(currency_code=r.currency_code, minor_units=r.amount_minor_units),
            stage=Stage(r.stage) if r.stage is not None else Stage.UNKNOWN,
        ))
    return inputs


def compute_capital_metrics_for_market(db: Engine | Connection, market_id: UUID, taxonomy_version: str,
                                       period_start, period_end) -> CapitalMetrics:
    inputs = get_primary_attributed_financing_events(db, market_id, taxonomy_version)
    return compute_capital_metrics(inputs, market_id=market_id, taxonomy_version=taxonomy_version,
                                   period_start=period_start, period_end=period_end)
