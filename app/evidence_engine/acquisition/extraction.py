"""
Grounded, structured evidence extraction (Task 20 items 8-10).

**Item 8: the model's job is extraction/classification into the engine's
already-approved vocabulary, never a score.** `EvidenceExtractor`
(`providers.py`) returns `ExtractedClaimCandidate`s -- a `structured_fact`
with a `kind`/label from the SAME closed vocabularies every pillar's own
`classify_with_recovery()` already validates against, never a numeric
score, never a free-form quality judgment. This module's own `_KNOWN_
DIMENSIONS` set is the same dimension-name vocabulary `cross_pillar_
audit.py` already builds from `parameters.py` -- extraction cannot
invent a dimension the methodology does not define.

**Item 9: grounding.** `validate_candidate()` is the ONE gate every
candidate must pass before `claim_identity.py::finalize_claim()` is ever
called -- reusing the exact five rejection conditions item 9 lists,
implemented deterministically, never "repaired" by asking the model
again with different instructions (a validation failure means retry
with the SAME grounding rules restated, per `extract_candidates_with_
recovery()` below, mirroring `classification.py::classify_with_
recovery()`'s own one-retry, never-relaxed pattern exactly).

**Item 10: prompt-injection resistance.** Nothing in this module ever
reads `candidate.claim_text`/`excerpt` as an instruction -- they are
data fields compared/validated as strings, never evaluated, interpolated
into a system prompt, or used to alter validation logic. A malicious
source telling the extractor to "score this company 10/10" can, at
worst, produce a candidate whose own `assessment_criteria` names a
real dimension with a plausible-sounding `structured_fact` -- and that
candidate is still subject to the exact same grounding check (item 9)
and, once it reaches a pillar, the exact same `requires_named_entity_
fact`/`requires_minimum_distinct_facts` label-requirement checks every
pillar already enforces (Tasks 8-17). See `test_acquisition_pipeline.py`
for the adversarial fixture proving this end-to-end.
"""

from __future__ import annotations

import re

from app.evidence_engine import parameters as P
from app.evidence_engine.acquisition.models import (
    ClaimRejectionReason,
    ExtractedClaimCandidate,
    ExtractionRequest,
    ExtractionResponse,
    RejectedClaimCandidate,
    RetrievedSource,
)
from app.evidence_engine.acquisition.providers import EvidenceExtractor

_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text.lower()).strip()


# The complete, closed dimension-name vocabulary across all six pillars,
# plus the two pseudo-dimensions (`team_identity`, `stage_signal`) that
# are not themselves scored but are legitimate, real `assessment_
# criteria` values. Built directly from the same `*_DIMENSION_WEIGHTS`
# dicts every pillar's own evaluator already uses -- never a second,
# hand-maintained list that could drift from the real one.
_KNOWN_DIMENSIONS: frozenset[str] = frozenset(
    {
        *P.PRODUCT_TECHNOLOGY_DIMENSION_WEIGHTS,
        *P.MARKET_OPPORTUNITY_DIMENSION_WEIGHTS,
        *P.TEAM_LEADERSHIP_DIMENSION_WEIGHTS,
        *P.COMMERCIAL_TRACTION_DIMENSION_WEIGHTS,
        *P.EXECUTION_MOMENTUM_DIMENSION_WEIGHTS,
        *P.FINANCIAL_FUNDING_DIMENSION_WEIGHTS,
        "team_identity",
        "stage_signal",
    }
)


def validate_candidate(
    candidate: ExtractedClaimCandidate, source: RetrievedSource | None,
) -> RejectedClaimCandidate | None:
    """Returns None (accepted) or a `RejectedClaimCandidate` naming
    exactly why. Every check here is item 9's own list, in order."""
    if not candidate.source_id:
        return RejectedClaimCandidate(candidate, ClaimRejectionReason.NO_SOURCE_ID, "candidate carries no source_id")
    if source is None or source.source_id != candidate.source_id:
        return RejectedClaimCandidate(
            candidate, ClaimRejectionReason.UNKNOWN_SOURCE_ID,
            f"source_id {candidate.source_id!r} does not match any retrieved source in this run",
        )
    if not candidate.excerpt or not candidate.excerpt.strip():
        return RejectedClaimCandidate(candidate, ClaimRejectionReason.EMPTY_EXCERPT, "candidate carries no excerpt")

    # Grounding: the excerpt must be verbatim (normalized whitespace/case
    # only -- no paraphrase tolerance) present in the source's own
    # retrieved content. This is not a stricter rule than the rest of
    # this engine already has -- spec Part 2.1's own Claim.excerpt field
    # was always defined as "the verbatim source text... never
    # paraphrased"; this is that same rule, checked mechanically for the
    # first time because acquisition is the first place an excerpt is
    # ever machine-proposed rather than human-copied.
    if _normalize(candidate.excerpt) not in _normalize(source.content):
        return RejectedClaimCandidate(
            candidate, ClaimRejectionReason.EXCERPT_NOT_GROUNDED_IN_SOURCE,
            "the cited excerpt does not appear verbatim in the source's own retrieved content",
        )

    if not candidate.assessment_criteria or not any(d in _KNOWN_DIMENSIONS for d in candidate.assessment_criteria):
        return RejectedClaimCandidate(
            candidate, ClaimRejectionReason.NO_RECOGNIZED_DIMENSION,
            f"assessment_criteria {candidate.assessment_criteria!r} names no dimension this methodology defines",
        )

    if candidate.structured_fact is not None and "kind" not in candidate.structured_fact:
        return RejectedClaimCandidate(
            candidate, ClaimRejectionReason.MALFORMED_STRUCTURED_FACT,
            "structured_fact is present but carries no 'kind' -- fails closed rather than guessing one",
        )

    return None


def extract_with_recovery(
    extractor: EvidenceExtractor,
    request: ExtractionRequest,
    max_attempts: int = 2,
) -> tuple[tuple[ExtractedClaimCandidate, ...], tuple[RejectedClaimCandidate, ...], int]:
    """Item 17's own bounded-retry requirement, mirroring `classification.
    py::classify_with_recovery()`'s exact shape: at most `max_attempts`
    calls to the SAME extractor for the SAME source, every attempt
    validated identically (never relaxed), rejected candidates from the
    FINAL attempt returned for observability. Unlike the pillar-level
    classifiers, this extractor call has no `validation_feedback` channel
    to feed back into -- it is a fixed-shape deterministic/mock call in
    this task's own offline tests (item 20); a real provider's own retry
    would additionally pass back rejection reasons the same way
    `classify_with_recovery` already does, left for the task that wires
    in a real, approved provider.

    Returns (accepted_candidates, rejected_candidates_from_final_attempt,
    attempts_used)."""
    accepted: tuple[ExtractedClaimCandidate, ...] = ()
    rejected: tuple[RejectedClaimCandidate, ...] = ()
    attempts_used = 0

    for attempt in range(1, max_attempts + 1):
        attempts_used = attempt
        response = extractor.extract(request)
        accepted_this_attempt: list[ExtractedClaimCandidate] = []
        rejected_this_attempt: list[RejectedClaimCandidate] = []
        for candidate in response.candidates:
            rejection = validate_candidate(candidate, request.source)
            if rejection is None:
                accepted_this_attempt.append(candidate)
            else:
                rejected_this_attempt.append(rejection)

        accepted = tuple(accepted_this_attempt)
        rejected = tuple(rejected_this_attempt)

        # Succeed once at least one candidate is accepted, or the
        # extractor genuinely proposed zero candidates (a real "this
        # source had nothing relevant" outcome, distinct from "every
        # proposed candidate failed grounding" -- only the latter is
        # worth retrying).
        if accepted or not response.candidates:
            break

    return accepted, rejected, attempts_used
