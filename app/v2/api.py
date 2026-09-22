"""
Read-only Capital Intelligence API (Increment 14).

    Canonical FinancingEvents -> primary Market classification -> Capital Metrics -> Capital Signal -> HTTP

Every number in every response comes from the existing V2 read repositories and pure domain engines
(app.v2.repositories.capital_metrics, app.v2.repositories.capital_signal, app.v2.domain.capital_metrics,
app.v2.domain.capital_signal) -- this module contains NO calculation of its own, only query orchestration,
validation and JSON shaping (app.v2.api_schemas). It never re-derives market attribution, verified-amount
handling, date policy or currency policy.

READ-ONLY, STRUCTURALLY: this module imports only read functions from app.v2.repositories.markets
(get_market/get_market_by_slug/list_markets/count_markets/get_taxonomy_version/list_taxonomy_versions/
count_primary_classified_companies) and the two compute_* query functions above. It imports NO candidate write
repository, NO promotion/resolution/classification service, and NO ingestion service -- see
app/v2/tests/architecture/test_capital_api_boundaries.py, which fails if any of those ever appears here. A GET
request can change no canonical data.

PUBLIC: these are public market-intelligence reads, matching the existing app's own public endpoints (/discover,
/rankings) -- no Clerk auth dependency, mirroring that precedent rather than the authenticated /me* or /ventures*
surface (see app/auth.py).
"""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import DBAPIError, OperationalError

from app.observability import capture_exception
from app.v2.api_schemas import (
    CapitalMetricsResponse,
    CapitalSignalResponse,
    MarketDetailOut,
    MarketListOut,
    capital_metrics_response,
    capital_signal_response,
    market_out,
)
from app.v2.config import ConfigurationError
from app.v2.db.engine import get_engine
from app.v2.repositories import capital_metrics as capital_metrics_repo
from app.v2.repositories import capital_signal as capital_signal_repo
from app.v2.repositories import markets as markets_repo

router = APIRouter(prefix="/api/v2", tags=["capital-intelligence"])

# Mirrors app.v2.domain.versions.validate_version_id's own pattern exactly (that module's regex is private, so
# this is a documented literal copy, not a shared constant) -- used only for early, structural (422) rejection of
# a malformed taxonomy_version before it ever reaches the database.
_TAXONOMY_VERSION_PATTERN = r"^[a-z][a-z0-9_]{0,63}\.v[1-9][0-9]{0,5}$"
_TAXONOMY_VERSION_QUERY = Query(..., pattern=_TAXONOMY_VERSION_PATTERN, description="e.g. venturegps_taxonomy.v1")
_SERVICE_UNAVAILABLE = "Capital intelligence service is temporarily unavailable."


def _engine_or_503():
    """The engine dependency. A FastAPI `Depends`, deliberately -- so a test can override it
    (`app.dependency_overrides[_engine_or_503] = ...`) to point at a disposable test database without touching
    process environment variables or the process-wide `get_engine()` singleton."""
    try:
        return get_engine()
    except ConfigurationError:
        raise HTTPException(status_code=503, detail=_SERVICE_UNAVAILABLE) from None


EngineDep = Depends(_engine_or_503)


def _run(fn, *args, **kwargs):
    """Every DB-touching call in this router goes through here: OperationalError/DBAPIError (the database is
    unreachable) becomes a generic 503 with no connection details; any other unexpected exception is logged
    (mirroring app/api.py's own traceback+Sentry pattern) and surfaces as a generic 500 -- neither ever echoes
    internal exception text or a stack trace to the client."""
    try:
        return fn(*args, **kwargs)
    except (OperationalError, DBAPIError):
        raise HTTPException(status_code=503, detail=_SERVICE_UNAVAILABLE) from None
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - the one deliberate catch-all, matching app/api.py's own pattern
        capture_exception(exc)
        raise HTTPException(status_code=500, detail="An internal error occurred.") from None


def _utc_midnight(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def _require_market(engine, market_id: uuid.UUID):
    market = _run(markets_repo.get_market, engine, market_id)
    if market is None:
        raise HTTPException(status_code=404, detail="No such market.")
    return market


def _require_taxonomy_version(engine, taxonomy_version: str) -> None:
    if _run(markets_repo.get_taxonomy_version, engine, taxonomy_version) is None:
        raise HTTPException(status_code=404, detail="No such taxonomy version.")


@router.get("/markets", response_model=MarketListOut)
def list_markets(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), engine=EngineDep):
    rows = _run(markets_repo.list_markets, engine, limit=limit, offset=offset)
    total = _run(markets_repo.count_markets, engine)
    return MarketListOut(markets=[market_out(m) for m in rows], limit=limit, offset=offset, total=total)


@router.get("/markets/{market_id}", response_model=MarketDetailOut)
def get_market(market_id: uuid.UUID, engine=EngineDep):
    market = _require_market(engine, market_id)
    versions = [v.taxonomy_version for v in _run(markets_repo.list_taxonomy_versions, engine)]
    return MarketDetailOut(id=market.id, slug=market.slug, display_name=market.display_name, taxonomy_versions=versions)


@router.get("/markets/{market_id}/capital/metrics", response_model=CapitalMetricsResponse)
def get_capital_metrics(
    market_id: uuid.UUID,
    taxonomy_version: str = _TAXONOMY_VERSION_QUERY,
    start_date: date = Query(..., description="Period start (inclusive), ISO 8601 date."),
    end_date: date = Query(..., description="Period end (exclusive), ISO 8601 date."),
    engine=EngineDep,
):
    if start_date >= end_date:
        raise HTTPException(status_code=400, detail="start_date must be strictly before end_date.")

    market = _require_market(engine, market_id)
    _require_taxonomy_version(engine, taxonomy_version)

    period_start, period_end = _utc_midnight(start_date), _utc_midnight(end_date)
    metrics = _run(capital_metrics_repo.compute_capital_metrics_for_market, engine, market_id, taxonomy_version, period_start, period_end)
    classified = _run(markets_repo.count_primary_classified_companies, engine, market_id, taxonomy_version)
    return capital_metrics_response(market, taxonomy_version, period_start, period_end, metrics, classified)


@router.get("/markets/{market_id}/capital/signal", response_model=CapitalSignalResponse)
def get_capital_signal(
    market_id: uuid.UUID,
    taxonomy_version: str = _TAXONOMY_VERSION_QUERY,
    as_of: date = Query(..., description="The instant the current 30-day window ends, ISO 8601 date (interpreted as UTC midnight)."),
    engine=EngineDep,
):
    market = _require_market(engine, market_id)
    _require_taxonomy_version(engine, taxonomy_version)

    signal = _run(capital_signal_repo.compute_capital_signal_for_market, engine, market_id, taxonomy_version, _utc_midnight(as_of))
    classified = _run(markets_repo.count_primary_classified_companies, engine, market_id, taxonomy_version)
    return capital_signal_response(market, signal, classified)
