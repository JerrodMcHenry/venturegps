"""
The Capital Signal query layer: fetches canonical data ONCE and hands it to the pure engines
(app.v2.domain.capital_signal, app.v2.domain.capital_metrics) to build the current window, the 8 historical
windows, and the overall signal. Read-only -- nothing here writes.

    compute_capital_signal_for_market(db, market_id, taxonomy_version, as_of) -> CapitalSignal

This does NOT re-derive market attribution, verified-amount handling, stage handling, date policy or currency
policy: it calls app.v2.repositories.capital_metrics.get_primary_attributed_financing_events exactly once (the
same primary-classification attribution Increment 12 established) and reuses
app.v2.domain.capital_metrics.compute_capital_metrics for each of the 9 windows, so there is exactly one
implementation of every one of those rules in the codebase.
"""

from uuid import UUID

from sqlalchemy.engine import Connection, Engine

from app.v2.domain.capital_metrics import compute_capital_metrics
from app.v2.domain.capital_signal import CapitalSignal, build_windows, compute_capital_signal
from app.v2.repositories.capital_metrics import get_primary_attributed_financing_events


def compute_capital_signal_for_market(db: Engine | Connection, market_id: UUID, taxonomy_version: str, as_of) -> CapitalSignal:
    current_window, historical_windows = build_windows(as_of)
    inputs = get_primary_attributed_financing_events(db, market_id, taxonomy_version)   # one query, reused for every window

    current_metrics = compute_capital_metrics(inputs, market_id=market_id, taxonomy_version=taxonomy_version,
                                              period_start=current_window[0], period_end=current_window[1])
    historical_metrics = tuple(
        compute_capital_metrics(inputs, market_id=market_id, taxonomy_version=taxonomy_version, period_start=start, period_end=end)
        for start, end in historical_windows
    )
    return compute_capital_signal(current_metrics, historical_metrics, market_id=market_id, taxonomy_version=taxonomy_version,
                                  as_of=as_of, current_window=current_window, historical_windows=historical_windows)
