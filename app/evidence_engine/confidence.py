"""
Dimension-level Confidence (NEW_ENGINE_SPEC.md Part 6.4), extended in the
Task 9 calibration pass to explicitly weigh source reliability (not just
support_status mix and corroboration count), and in Task 10 to count
corroboration via provenance-VERIFIED distinct facts
(app.evidence_engine.provenance) rather than trusting each claim's
self-declared `independence_group_id` at face value -- two claims
declared as separate groups but found to be a syndicated restatement of
the same disclosure no longer inflate this count.

A pure function of the CITED claims backing one already-scored dimension
-- never reads the dimension's own score (firewall property, spec Part
6.6).
"""

from __future__ import annotations

from app.evidence_engine import parameters as P
from app.evidence_engine.models import Claim, SupportStatus
from app.evidence_engine.provenance import verified_distinct_fact_count
from app.evidence_engine.scoring import ConfidenceLevel


def compute_dimension_confidence(claims: tuple[Claim, ...]) -> ConfidenceLevel:
    if not claims:
        return ConfidenceLevel.LOW

    distinct_groups = verified_distinct_fact_count(claims)
    all_directly_supported = all(c.support_status == SupportStatus.DIRECTLY_SUPPORTED for c in claims)
    avg_reliability = sum(
        P.SOURCE_RELIABILITY_WEIGHT.get(c.source_type.value, 0.3) for c in claims
    ) / len(claims)

    if (
        all_directly_supported
        and distinct_groups >= P.CONFIDENCE_MIN_CORROBORATION_GROUPS_FOR_HIGH
        and avg_reliability >= P.CONFIDENCE_MIN_RELIABILITY_FOR_HIGH
    ):
        return ConfidenceLevel.HIGH

    if avg_reliability >= P.CONFIDENCE_MIN_RELIABILITY_FOR_MEDIUM:
        return ConfidenceLevel.MEDIUM

    return ConfidenceLevel.LOW
