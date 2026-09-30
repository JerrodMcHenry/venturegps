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


def map_round_type(value: str) -> Stage | None:
    lowered = value.strip().lower()
    for keyword, stage in _ROUND_TYPE_KEYWORDS:
        if keyword in lowered:
            return stage
    return None


def funding_round_type_fields_are_sufficient(fact: dict[str, str] | None) -> bool:
    """Task 25 -- lets `acquisition/routing.py` determine, at acquisition
    time, whether a `funding_round_type` fact is structurally sufficient
    to legitimately reach `stage_signal`: not merely "kind matches," but
    "the `value` field this module actually reads
    (`resolve_stage()`'s own `latest.structured_fact["value"]`) is
    present AND maps to a real `Stage` via this module's own `map_round_
    type()` -- reused directly, not re-implemented, so this can never
    silently drift from what `resolve_stage()` itself would accept."""
    fact = fact or {}
    if fact.get("kind") != "funding_round_type":
        return False
    value = fact.get("value")
    if not value:
        return False
    return map_round_type(value) is not None


def founding_year_fields_are_sufficient(fact: dict[str, str] | None) -> bool:
    """Task 25 -- same purpose as `funding_round_type_fields_are_
    sufficient()` above, for `founding_year`: `resolve_stage()` reads
    `latest.structured_fact["value"]` (NOT "amount" -- a real, live
    mismatch `LIVE_EVALUATION_LINEAR_002.md` found, see
    `LINEAR_002_REMEDIATION.md`) and requires it to parse as an int."""
    fact = fact or {}
    if fact.get("kind") != "founding_year":
        return False
    value = fact.get("value")
    if not value:
        return False
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


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
        # `.get("value")`, not `["value"]` (Task 27, test_fact_contracts.py's
        # own consumer test caught this live): a "value"-less funding_round_
        # type fact reaching this function -- possible for any ledger built
        # outside extraction.py's own routing pass, e.g. a hand-built
        # fixture or the calibration suite -- must fail closed to "no
        # mapped stage from this claim," never raise KeyError. Task 25's
        # own `funding_round_type_fields_are_sufficient()` already keeps
        # a malformed fact like this OUT of stage_signal on the normal,
        # routed extraction path; this is defense-in-depth for the path
        # that check does not gate, not a second, competing rule.
        raw_value = latest.structured_fact.get("value")
        mapped = map_round_type(raw_value) if raw_value else None
        if mapped is not None:
            return mapped

    founding_year_claims = [c for c in signal_claims if c.structured_fact.get("kind") == "founding_year"]
    if founding_year_claims:
        latest = max(founding_year_claims, key=lambda c: c.retrieved_at)
        # Same fix, same rationale: `.get("value")` so a founding_year fact
        # that (mistakenly) used "amount" instead of "value" -- the exact,
        # repeatedly-observed real bug LINEAR_002/COHORT_001 documented --
        # fails closed to Undetermined rather than raising KeyError.
        try:
            year = int(latest.structured_fact.get("value"))
        except (TypeError, ValueError):
            return Stage.UNDETERMINED
        return _map_founding_age(year, as_of)

    return Stage.UNDETERMINED
