"""
The Evidence Ledger container and dimension-evidence resolution
(NEW_ENGINE_SPEC.md Part 2.3, 2.4).

`resolve_dimension_evidence()` is the one place staleness, disputed-claim
exclusion, and independence-group deduplication are applied -- every
dimension evaluator (app/evidence_engine/pillars/*.py) calls this instead
of touching `EvidenceLedger.claims` directly, so all three rules are
enforced uniformly rather than reimplemented per dimension.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.evidence_engine.models import Claim, SupportStatus


@dataclass(frozen=True)
class EvidenceLedger:
    claims: tuple[Claim, ...]

    @staticmethod
    def from_list(claims: list[Claim]) -> "EvidenceLedger":
        return EvidenceLedger(claims=tuple(claims))

    def by_id(self, claim_id: str) -> Claim | None:
        for c in self.claims:
            if c.claim_id == claim_id:
                return c
        return None

    def claims_for_dimension(self, dimension: str) -> tuple[Claim, ...]:
        return tuple(c for c in self.claims if dimension in c.assessment_criteria)


@dataclass(frozen=True)
class DimensionEvidence:
    """The resolved evidence backing one dimension for one company, as of
    one date -- staleness and disputed-claim exclusion already applied,
    duplicate restatements of the same underlying event already collapsed
    to one representative claim per independence group.
    """

    dimension: str

    # Claims that are usable as scoring evidence: not disputed, not stale,
    # deduplicated to one claim per independence_group_id (the earliest
    # retrieved, per spec Part 2.3 -- "only the earliest-retrieved entry in
    # a group counts toward a dimension's evidence").
    admissible: tuple[Claim, ...] = field(default_factory=tuple)

    # Retained for transparency and for the disputed/stale acceptance
    # tests, but excluded from scoring.
    disputed: tuple[Claim, ...] = field(default_factory=tuple)
    stale: tuple[Claim, ...] = field(default_factory=tuple)

    # All claims tagged for this dimension, admissible or not -- used by
    # dimension evaluators that need to distinguish "no evidence exists at
    # all" (empty) from "evidence exists but none of it is admissible"
    # (non-empty here, empty `admissible`).
    all_tagged: tuple[Claim, ...] = field(default_factory=tuple)

    @property
    def corroboration_group_count(self) -> int:
        """Distinct independent events backing this dimension's admissible
        evidence -- corroboration, per spec Part 2.3/5, is counted by
        independence_group_id, never by raw claim count (which would let
        ten restatements of one press release look like ten corroborating
        facts)."""
        return len({c.independence_group_id for c in self.admissible})


def _is_stale(claim: Claim, as_of: date, staleness_days: int) -> bool:
    reference = claim.published_at or claim.retrieved_at
    return (as_of - reference).days > staleness_days


def resolve_dimension_evidence(
    ledger: EvidenceLedger,
    dimension: str,
    as_of: date,
    staleness_days: int,
) -> DimensionEvidence:
    tagged = ledger.claims_for_dimension(dimension)
    if not tagged:
        return DimensionEvidence(dimension=dimension)

    disputed = tuple(c for c in tagged if c.support_status == SupportStatus.DISPUTED)
    non_disputed = tuple(c for c in tagged if c.support_status != SupportStatus.DISPUTED)

    stale = tuple(c for c in non_disputed if _is_stale(c, as_of, staleness_days))
    fresh = tuple(c for c in non_disputed if not _is_stale(c, as_of, staleness_days))

    # Deduplicate by independence_group_id: keep only the
    # earliest-retrieved claim per group as the group's representative for
    # scoring purposes (spec Part 2.3). Every fresh claim is still
    # available via `all_tagged` for transparency.
    earliest_by_group: dict[str, Claim] = {}
    for c in fresh:
        existing = earliest_by_group.get(c.independence_group_id)
        if existing is None or c.retrieved_at < existing.retrieved_at:
            earliest_by_group[c.independence_group_id] = c
    admissible = tuple(
        sorted(earliest_by_group.values(), key=lambda c: c.claim_id)
    )

    return DimensionEvidence(
        dimension=dimension,
        admissible=admissible,
        disputed=disputed,
        stale=stale,
        all_tagged=tagged,
    )
