"""
Stage determination (NEW_ENGINE_SPEC.md Part 4.1) -- an independent,
from-scratch implementation for this isolated engine. It reuses the
general SHAPE of "prior-round-label > scale > age > Undetermined" the spec
itself already reasoned through, not any code or values from either prior
engine.

Scoped honestly for this phase: the "scale" fallback the full spec
describes (Part 4.1 item 2, reading Commercial Traction's Disclosed Scale)
cannot be implemented yet -- Commercial Traction does not exist as a
pillar in this codebase. This module supports the round-type signal and
the founding-age signal only, and falls through to UNDETERMINED
otherwise, never guessing. Extend once Commercial Traction exists.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from app.evidence_engine import parameters as P
from app.evidence_engine.ledger import EvidenceLedger, resolve_dimension_evidence

STAGE_SIGNAL_DIMENSION = "stage_signal"


class Stage(str, Enum):
    IDEA = "Idea"
    PRE_SEED = "Pre-Seed"
    SEED = "Seed"
    SERIES_A = "Series A"
    SERIES_B_PLUS = "Series B+"
    GROWTH = "Growth"
    UNDETERMINED = "Undetermined"


class StageTier(str, Enum):
    """Product & Technology's own evaluation grouping (Task 9's own
    "early-stage, growth-stage, established" framing) -- a coarser lens
    than the 6-state Stage enum above, used only for this pillar's
    stage-indexed label->score tables (spec Part 4.2). Other pillars, if
    and when built, are free to use the 6-state Stage directly instead."""

    EARLY = "early"
    GROWTH = "growth"
    ESTABLISHED = "established"


_STAGE_TO_TIER: dict[Stage, StageTier] = {
    Stage.IDEA: StageTier.EARLY,
    Stage.PRE_SEED: StageTier.EARLY,
    Stage.SEED: StageTier.EARLY,
    Stage.SERIES_A: StageTier.GROWTH,
    Stage.SERIES_B_PLUS: StageTier.GROWTH,
    Stage.GROWTH: StageTier.ESTABLISHED,
}

# Ordered so "most permissive" (spec Part 4.3) means "first in this list
# whose band is at least as generous" -- in practice, for this pillar's
# monotonically-descending early>growth>established tables (Part 4.2's own
# "the same evidence is more remarkable, and therefore worth more, at an
# earlier stage" design decision, documented in parameters.py), the most
# permissive tier is always EARLY. This ordering is asserted, not assumed,
# by a dedicated test (test_stage_aware_evaluation.py).
ALL_TIERS: tuple[StageTier, ...] = (StageTier.EARLY, StageTier.GROWTH, StageTier.ESTABLISHED)


def tier_for_stage(stage: Stage) -> StageTier | None:
    """None for Stage.UNDETERMINED -- callers must handle that case
    explicitly (spec Part 4.3: evaluate against the most permissive
    applicable band across all tiers, never guess a specific one)."""
    return _STAGE_TO_TIER.get(stage)


# --- Round-type keyword mapping (an independently-authored equivalent of --
# --- the spec's own reasoning, not imported from either prior engine) -----
_ROUND_TYPE_KEYWORDS: tuple[tuple[str, Stage], ...] = (
    # Task 12, item 2: expanded from real financing terminology
    # NEW_ENGINE_LIVE_EVALUATION.md §3.3 found unrecognized -- a Y
    # Combinator batch identifier (checked before the bare "seed" keyword
    # below, since YC's own standard deal is conventionally reported as
    # Pre-Seed regardless of what the batch season code itself contains)
    # and a "tender offer" (a late-stage/growth secondary-liquidity event
    # for existing shareholders, not a new primary financing round, but
    # the same kind of stage signal in spirit -- mapped to Growth).
    ("y combinator", Stage.PRE_SEED),
    ("yc s", Stage.PRE_SEED),
    ("yc w", Stage.PRE_SEED),
    ("pre-seed", Stage.PRE_SEED),
    ("pre seed", Stage.PRE_SEED),
    ("idea", Stage.IDEA),
    ("seed", Stage.SEED),
    ("series a", Stage.SERIES_A),
    ("series b", Stage.SERIES_B_PLUS),
    ("series c", Stage.SERIES_B_PLUS),
    ("series d", Stage.SERIES_B_PLUS),
    ("growth", Stage.GROWTH),
    ("late-stage", Stage.GROWTH),
    ("tender offer", Stage.GROWTH),
    ("ipo", Stage.GROWTH),
)

# CALIBRATION REQUIRED (spec Part 6.7 pattern extended to this module):
# these age bands are a reasoned placeholder, not a calibrated value.
_FOUNDING_AGE_BANDS: tuple[tuple[int, Stage], ...] = (
    (1, Stage.IDEA),
    (2, Stage.PRE_SEED),
    (4, Stage.SEED),
    (7, Stage.SERIES_A),
    (12, Stage.SERIES_B_PLUS),
)


def _map_round_type(value: str) -> Stage | None:
    lowered = value.strip().lower()
    for keyword, stage in _ROUND_TYPE_KEYWORDS:
        if keyword in lowered:
            return stage
    return None


def _map_founding_age(founding_year: int, as_of: date) -> Stage:
    age_years = as_of.year - founding_year
    for max_age, stage in _FOUNDING_AGE_BANDS:
        if age_years <= max_age:
            return stage
    return Stage.GROWTH


def determine_stage(ledger: EvidenceLedger, company_ref: str, as_of: date) -> Stage:
    """spec Part 4.1's priority order: most-recent disclosed funding-round
    type first, then founding-age, else Undetermined -- never a silent
    default to any single real stage.

    Task 12, item 2: routed through the exact same admissibility check
    (`resolve_dimension_evidence`) every scored dimension already uses --
    a disputed or stale stage-signal claim is excluded here exactly as it
    would be for a scored dimension, rather than being read directly off
    the raw ledger the way this function did before this fix (a real gap
    NEW_ENGINE_LIVE_EVALUATION.md §5.3 found: two disputed claims could
    previously still decide the stage, silently, by whichever had the
    later `published_at`)."""
    scoped = EvidenceLedger.from_list([c for c in ledger.claims if c.company_ref == company_ref])
    evidence = resolve_dimension_evidence(
        scoped, STAGE_SIGNAL_DIMENSION, as_of, P.STAGE_SIGNAL_STALENESS_DAYS
    )
    signal_claims = [c for c in evidence.admissible if c.structured_fact]

    round_type_claims = [c for c in signal_claims if c.structured_fact.get("kind") == "funding_round_type"]
    if round_type_claims:
        # Most recent disclosed round wins (a later round supersedes an
        # earlier one as the current-stage signal), by retrieved_at as the
        # tiebreaker when published_at is absent, matching the ledger's own
        # recency convention (spec Part 2.3).
        latest = max(round_type_claims, key=lambda c: c.published_at or c.retrieved_at)
        mapped = _map_round_type(latest.structured_fact["value"])
        if mapped is not None:
            return mapped

    founding_year_claims = [c for c in signal_claims if c.structured_fact.get("kind") == "founding_year"]
    if founding_year_claims:
        latest = max(founding_year_claims, key=lambda c: c.retrieved_at)
        try:
            year = int(latest.structured_fact["value"])
        except (TypeError, ValueError):
            return Stage.UNDETERMINED
        return _map_founding_age(year, as_of)

    return Stage.UNDETERMINED
