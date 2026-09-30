"""
Grounded, structured evidence extraction (Task 20 items 8-10).

**Item 8: the model's job is extraction/classification into the engine's
already-approved vocabulary, never a score.** `EvidenceExtractor`
(`providers.py`) returns `ExtractedClaimCandidate`s -- a `structured_fact`
with a `kind`/label from the SAME closed vocabularies every pillar's own
`classify_with_recovery()` already validates against, never a numeric
score, never a free-form quality judgment. This module's own
`KNOWN_DIMENSIONS` set is the same dimension-name vocabulary `cross_pillar_
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
from app.evidence_engine.acquisition.claim_identity import IDENTITY_KEY_FIELDS
from app.evidence_engine.acquisition.models import (
    ClaimRejectionReason,
    ExtractedClaimCandidate,
    ExtractionRequest,
    ExtractionResponse,
    RejectedClaimCandidate,
    RetrievedSource,
    RoutingDecision,
)
from app.evidence_engine.acquisition.canonicalization import canonicalize_structured_fact
from app.evidence_engine.acquisition.relevance import (
    sanitize_subject_relationship,
    strip_unrelated_third_party_dimensions,
)
from app.evidence_engine.acquisition.routing import route_candidate
from app.evidence_engine.acquisition.providers import EvidenceExtractor

_WHITESPACE = re.compile(r"\s+")

# The complete, closed `structured_fact.kind` vocabulary -- reused
# directly from claim_identity.py's own identity-key table (the single
# place every recognized kind is already enumerated) rather than a
# second, hand-maintained list that could drift from it (Task 21 item 14:
# "reject an unrecognized fact kind").
KNOWN_FACT_KINDS: frozenset[str] = frozenset(IDENTITY_KEY_FIELDS.keys())

# The complete, closed set of `structured_fact` VALUE fields any pillar
# anywhere in this engine actually reads (verified by grepping every
# `pillars/*.py` file's own `fact.get(...)`/`fact[...]` accesses -- "kind"
# plus these 12). Deliberately a single global allowlist rather than a
# per-kind field table: every `_parse_*` function downstream already
# ignores any key it does not itself look for, so the real protection
# this closes is a field NO pillar recognizes at all -- most pointedly
# something like "score"/"rating"/"grade"/"confidence"/"quality", which
# would otherwise be a structurally-valid-looking but semantically
# score-like field a compromised or credulous extractor could try to
# smuggle in even though `ExtractedClaimCandidate` has no top-level score
# field (item 14's own "no model-provided score accepted").
ALLOWED_STRUCTURED_FACT_FIELDS: frozenset[str] = frozenset({
    "kind", "amount", "currency", "financing_type", "metric", "named_entity",
    "period_date", "person_id", "role", "round_date", "status", "value",
    "value_type", "topic",
})


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text.lower()).strip()


# The complete, closed dimension-name vocabulary across all six pillars,
# plus the two pseudo-dimensions (`team_identity`, `stage_signal`) that
# are not themselves scored but are legitimate, real `assessment_
# criteria` values. Built directly from the same `*_DIMENSION_WEIGHTS`
# dicts every pillar's own evaluator already uses -- never a second,
# hand-maintained list that could drift from the real one.
KNOWN_DIMENSIONS: frozenset[str] = frozenset(
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

    if not candidate.assessment_criteria or not any(d in KNOWN_DIMENSIONS for d in candidate.assessment_criteria):
        return RejectedClaimCandidate(
            candidate, ClaimRejectionReason.NO_RECOGNIZED_DIMENSION,
            f"assessment_criteria {candidate.assessment_criteria!r} names no dimension this methodology defines",
        )

    if candidate.structured_fact is not None and "kind" not in candidate.structured_fact:
        return RejectedClaimCandidate(
            candidate, ClaimRejectionReason.MALFORMED_STRUCTURED_FACT,
            "structured_fact is present but carries no 'kind' -- fails closed rather than guessing one",
        )

    # Task 21 item 14's own fuller validation: an unrecognized `kind`
    # fails closed rather than flowing through to claim_identity.py's own
    # fallback text-based grouping, which would silently downgrade a
    # fabricated-but-plausible-looking kind to weaker, approximate
    # dedup instead of rejecting it outright.
    if candidate.structured_fact is not None:
        kind = candidate.structured_fact.get("kind")
        if kind not in KNOWN_FACT_KINDS:
            return RejectedClaimCandidate(
                candidate, ClaimRejectionReason.INVALID_FACT_KIND,
                f"structured_fact.kind {kind!r} is not one of this methodology's recognized fact kinds",
            )
        unexpected_fields = set(candidate.structured_fact) - ALLOWED_STRUCTURED_FACT_FIELDS
        if unexpected_fields:
            return RejectedClaimCandidate(
                candidate, ClaimRejectionReason.DISALLOWED_FACT_FIELD,
                f"structured_fact carries unrecognized field(s) {sorted(unexpected_fields)!r} "
                "-- no pillar in this engine reads them, and a score-like field "
                "(e.g. 'score'/'rating'/'grade') is never accepted from an extractor",
            )

    return None


def _sanitize_assessment_criteria(candidate: ExtractedClaimCandidate) -> ExtractedClaimCandidate:
    """Filters `assessment_criteria` down to only recognized, LEGITIMATE
    dimension names before a candidate is finalized into a `Claim`
    (Task 21 item 14, extended by Task 23's own LINEAR_001 remediation).
    `validate_candidate` above only requires that AT LEAST ONE listed
    criterion be recognized (item 9's own original rule, unchanged -- a
    candidate genuinely relevant to one real dimension should not be
    rejected outright for also carrying one unrecognized label); this
    function is the separate, additive step that narrows the list
    further, in four passes, each independently documented:

    0. **Canonicalization** (Task 29 item 2, `acquisition/
       canonicalization.py::canonicalize_structured_fact()`) -- applied
       to `structured_fact` FIRST, before anything below reads it. Fixes
       the `LIVE_EVALUATION_FISH_AUDIO_002.md` §5 ordering defect: a
       person-identity-relevant fact's `person_id`, a numeric amount like
       `"$52M"`, or an explicit-but-non-ISO date are all deterministically
       derivable from what the model already grounded, and must be
       canonical BEFORE the applicability check below reads them -- not
       backfilled only later, in `claim_identity.py::finalize_claim()`,
       by which point this function's own routing decision would already
       be locked in on the stale, pre-canonical shape.
    1. **Vocabulary** (Task 21, unchanged) -- drop anything not a real
       dimension name at all.
    2. **Deterministic eligibility+applicability+semantic-fit routing**
       (Task 23 item 4, extended by Task 25 items 2-3 and Task 29 items
       6-10, `routing.py::route_candidate()`)
       -- when `structured_fact.kind` is a recognized, kind-gated kind,
       keep only the tag(s) that kind's own consuming pillar dimension(s)
       actually are (ELIGIBILITY, unchanged from Task 23 -- this is what
       stops a real funding-round fact from ALSO riding into an unrelated
       dimension the model happened to also propose, LINEAR_001's own
       single highest-impact finding). Task 25 adds APPLICABILITY on top:
       when the model's own proposal names no applicable dimension at
       all, but the fact's own fields are sufficient by that dimension's
       real evidence contract, `route_candidate()` deterministically
       routes it anyway -- fixing `LIVE_EVALUATION_LINEAR_002.md`'s own
       new finding, where a correctly-typed `funding_round`/`founding_
       year` fact silently ended up with `assessment_criteria == []`
       because the model's proposal, though present, named nothing
       eligible, and nothing then checked whether the RESULT was still
       usable.
    3. **Relevance** (Task 23 item 9, `relevance.py`) -- when the
       extractor marked a candidate `unrelated_third_party`, drop the
       four kind-agnostic, company-quality-claiming dimensions that have
       no positive kind-gate of their own and would otherwise have no
       structural defense against exactly this case (LINEAR_001's own
       dev.to hobbyist-tool finding).

    The full decision (proposed/eligible/final/removed/added criteria,
    routing status and reason, proposed vs. final subject_relationship)
    is attached to the returned candidate's own `routing_decision` field
    (Task 25 item 7/9) -- never persisted onto the final `Claim` (item 8's
    own "rather than polluting core scoring models"); `pipeline.py`
    pairs it with the finalized `claim_id` once one exists.

    Passes never ADD a tag the model did not propose UNLESS `route_
    candidate()`'s own deterministic-fallback branch fires (which itself
    only ever adds a tag the FACT's own fields justify, never one the
    model merely failed to mention for an unrelated reason -- item 11's
    own "invalid model routing cannot broaden evidence" invariant), and
    never reject the candidate outright for losing every tag this way."""
    if candidate.structured_fact is not None:
        canonical_fact = canonicalize_structured_fact(candidate.structured_fact)
        if canonical_fact != candidate.structured_fact:
            candidate = candidate.model_copy(update={"structured_fact": canonical_fact})

    vocabulary_filtered = [d for d in candidate.assessment_criteria if d in KNOWN_DIMENSIONS]
    if vocabulary_filtered != candidate.assessment_criteria:
        candidate = candidate.model_copy(update={"assessment_criteria": vocabulary_filtered})

    decision = route_candidate(candidate)
    after_routing = list(decision.final_criteria)

    sanitized_relationship = sanitize_subject_relationship(candidate.subject_relationship)
    after_relevance = strip_unrelated_third_party_dimensions(after_routing, sanitized_relationship)
    relevance_removed = [c for c in after_routing if c not in after_relevance]

    routing_decision = RoutingDecision(
        status=decision.status.value,
        reason=decision.reason,
        fact_kind=decision.fact_kind,
        proposed_criteria=list(decision.proposed_criteria),
        eligible_criteria=list(decision.eligible_criteria),
        final_criteria=after_relevance,
        removed_criteria=list(decision.removed_criteria),
        added_criteria=list(decision.added_criteria),
        proposed_subject_relationship=candidate.subject_relationship,
        final_subject_relationship=sanitized_relationship,
        relevance_removed_criteria=relevance_removed,
        semantic_fit_status=decision.semantic_fit_status,
    )

    updates: dict[str, object] = {"routing_decision": routing_decision}
    if after_relevance != candidate.assessment_criteria:
        updates["assessment_criteria"] = after_relevance
    if sanitized_relationship != candidate.subject_relationship:
        updates["subject_relationship"] = sanitized_relationship
    return candidate.model_copy(update=updates)


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
                accepted_this_attempt.append(_sanitize_assessment_criteria(candidate))
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


def extract_many(
    extractor: EvidenceExtractor,
    requests: tuple[ExtractionRequest, ...],
    max_attempts: int = 2,
) -> tuple[
    dict[str, tuple[ExtractedClaimCandidate, ...]],
    dict[str, tuple[RejectedClaimCandidate, ...]],
    dict[str, Exception],
    int,
]:
    """Task 21 item 6's own batching entry point. `EvidenceExtractor`
    (providers.py) is unchanged -- still one `.extract(request)` method,
    one source per call, exactly Task 20's own Protocol. A provider that
    ALSO wants to serve several sources in one real external call
    (`providers_live.py::OpenAIEvidenceExtractor`) additionally exposes
    an `extract_batch(requests) -> ExtractionResponse` method (duck-typed,
    not part of the Protocol itself -- see that module's own docstring
    for why); this function is the ONE place that checks for it and
    prefers it when present, falling back to per-request `extract_with_
    recovery()` calls otherwise.

    **Task 21A item 4 (retry ownership):** the batch-capable path below
    calls `extract_batch()` EXACTLY ONCE and never loops itself -- retry
    (both transient-failure and validation-driven) is now owned entirely
    by the provider's own `extract_batch()` implementation (see
    `providers_live.py::OpenAIEvidenceExtractor`'s own "Retry ownership"
    section), so it is not duplicated or multiplied here. `validate_
    candidate()` still runs again on whatever comes back, unconditionally
    -- item 3's own "do not weaken downstream validation just because the
    API validates syntax/schema" -- this is a second, cheap, pure-function
    check, not a retry. `max_attempts` is therefore only meaningful for
    the FALLBACK (non-batch-capable) path below, unchanged from Task 20.

    This preserves EVERY existing fake in `fakes.py` (none of which
    implement `extract_batch`) and every one of Task 20's 22 pipeline
    tests' own OBSERVABLE behavior unchanged -- they all go through the
    fallback path, which is a per-request loop functionally identical to
    calling `extract_with_recovery()` directly, EXCEPT that this function
    additionally isolates a single request's own raised exception from
    every OTHER request in the same batch (see `errors_by_source` below)
    -- a real correctness requirement once several sources can share one
    batch/task, not merely a Task 20 carry-over: Task 20's own version
    called `extract_with_recovery()` once per source, in its own
    independent try/except, so one source's exception could never have
    affected another source's result either; this function's fallback
    path now explicitly reproduces that same per-source isolation itself,
    rather than relying on the (now batched) caller to provide it.

    Returns ({source_id: accepted_candidates}, {source_id:
    rejected_candidates}, {source_id: raised_exception}, total_attempts_
    used) -- keyed by source_id so callers never have to worry about
    response-vs-request ordering (item 6's own "source attribution
    preserved"). A source_id appears in AT MOST ONE of the first three
    dicts: `errors_by_source` for a request whose extraction call itself
    raised (as opposed to merely proposing a candidate that failed
    grounding validation, which lands in `rejected_by_source` instead).
    """
    accepted_by_source: dict[str, tuple[ExtractedClaimCandidate, ...]] = {}
    rejected_by_source: dict[str, tuple[RejectedClaimCandidate, ...]] = {}
    errors_by_source: dict[str, Exception] = {}

    batch_extract = getattr(extractor, "extract_batch", None)
    if callable(batch_extract) and requests:
        responses = batch_extract(tuple(requests))
        for request, response in zip(requests, responses):
            sid = request.source.source_id
            acc: list[ExtractedClaimCandidate] = []
            rej: list[RejectedClaimCandidate] = []
            for candidate in response.candidates:
                rejection = validate_candidate(candidate, request.source)
                if rejection is None:
                    acc.append(_sanitize_assessment_criteria(candidate))
                else:
                    rej.append(rejection)
            accepted_by_source[sid] = tuple(acc)
            rejected_by_source[sid] = tuple(rej)
        # `errors_by_source` stays empty on this path -- a batch-capable
        # provider makes its own, internally-bounded number of real calls
        # for the whole batch and is responsible for its own graceful
        # degradation (providers_live.py); an exception escaping it here
        # is a genuine whole-batch failure, correctly left to propagate to
        # this function's own caller (which already treats one batch/
        # task's exception as that one batch's own failure, isolated from
        # every OTHER concurrently-run batch).
        return accepted_by_source, rejected_by_source, errors_by_source, 1

    total_attempts = 0
    for request in requests:
        sid = request.source.source_id
        try:
            accepted, rejected, attempts = extract_with_recovery(extractor, request, max_attempts=max_attempts)
        except Exception as exc:  # noqa: BLE001 -- isolated per-source so it never destroys sibling requests in this batch
            errors_by_source[sid] = exc
            total_attempts += 1
            continue
        accepted_by_source[sid] = accepted
        rejected_by_source[sid] = rejected
        total_attempts += attempts

    return accepted_by_source, rejected_by_source, errors_by_source, total_attempts
