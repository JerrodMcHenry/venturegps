"""
The AI classification/extraction interface (NEW_ENGINE_SPEC.md Part 5.1,
Design Principle 7). This is the schema-constrained boundary a real LLM
call will eventually sit behind; for now every caller in this codebase
supplies a Protocol-conforming mock (see MockClassificationModel /
MockExtractionModel below and the adversarial models in
tests/test_adversarial_robustness.py) -- no paid API call is made
anywhere in this package.

Two closed shapes only, matching spec Part 5.1 exactly:
  - ExtractionResponse: a typed fact, for a Computed dimension.
  - ClassificationResponse: a label from a fixed enum, for a Classified
    dimension.
Neither ever carries a numeric score. `validate_classification()` /
`validate_extraction()` are the deterministic gate every response must
pass before a dimension evaluator will use it -- an invalid label, a
supporting_claim_id that does not exist, is not tagged for this dimension,
is not currently admissible, or a label the cited evidence does not
structurally establish are all rejected here, regardless of what the
model itself asserts (this is the concrete defense against a model that
is wrong, careless, or manipulated by injected content in the evidence
it was given -- see Design Principle 7 and the prompt-injection tests).

Task 10, item 2 adds `classify_with_recovery()` / `extract_with_recovery()`:
on a validation failure, the SAME model is given one retry with the
violations fed back as structured `validation_feedback`, so a model
capable of self-correction (e.g. dropping a citation the validator
identified as insufficient) gets one real chance to do so. If the second
attempt is still invalid, the caller must fail closed to Unscored --
these two functions never return a response that hasn't passed the exact
same validation both times, and never substitute a score or accept an
unsupported citation on either attempt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from app.evidence_engine.ledger import DimensionEvidence
from app.evidence_engine.models import INDEPENDENT_SOURCE_TYPES, Claim, SourceType, SupportStatus
from app.evidence_engine.provenance import verify_independence


# --- Identity-blindness (spec Part 5.3) -------------------------------------

def redact_company_identity(text: str, company_names: tuple[str, ...]) -> str:
    """Replaces the company's own name(s)/brand terms with a neutral
    placeholder before evidence text is shown to a classification call --
    the research/retrieval step legitimately knows the company's name;
    the classification step must not be able to let brand recognition
    influence a label choice (Design Principle 10)."""
    redacted = text
    for name in company_names:
        if not name:
            continue
        redacted = redacted.replace(name, "[THE SUBJECT COMPANY]")
    return redacted


@dataclass(frozen=True)
class EvidenceItem:
    claim_id: str
    redacted_text: str
    source_type: SourceType
    support_status: SupportStatus
    independence_group_id: str
    # Task 13 (shared-layer extension, documented in the Market
    # Opportunity completion report): propagated from Claim.structured_fact
    # unchanged. Product & Technology's own Classified dimensions never
    # populate or read this (all four decide their label from
    # source_type/independence alone, never claim content) -- purely
    # additive, zero effect on any existing pillar. Market Opportunity's
    # magnitude-bearing dimensions (market size, growth rate) need a
    # deterministic stand-in for "the AI correctly read a number out of
    # this evidence's text," the same role structured_fact already plays
    # for stage-signal claims (stage.py) -- extending it to the
    # classification interface itself, rather than inventing a second,
    # parallel typed-fact mechanism, is the narrower change.
    structured_fact: dict[str, str] | None = None


def to_evidence_items(claims: tuple[Claim, ...], company_names: tuple[str, ...]) -> tuple[EvidenceItem, ...]:
    return tuple(
        EvidenceItem(
            claim_id=c.claim_id,
            redacted_text=redact_company_identity(c.excerpt or c.claim_text, company_names),
            source_type=c.source_type,
            support_status=c.support_status,
            independence_group_id=c.independence_group_id,
            structured_fact=c.structured_fact,
        )
        for c in claims
    )


# --- Classification (Classified dimensions) ---------------------------------

@dataclass(frozen=True)
class ClassificationRequest:
    dimension: str
    allowed_labels: tuple[str, ...]
    evidence_items: tuple[EvidenceItem, ...]
    # Populated only on a retry (Task 10, item 2): the exact violation
    # messages `validate_classification` produced for this same request on
    # the prior attempt. A model that ignores this field simply behaves
    # the same on both attempts (fine -- retry then has no effect beyond
    # one extra call); a self-correcting model can read it and adjust its
    # citations/label.
    validation_feedback: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ClassificationResponse:
    label: str
    supporting_claim_ids: tuple[str, ...]


class ClassificationModel(Protocol):
    def classify(self, request: ClassificationRequest) -> ClassificationResponse: ...


# Per-label "does the cited evidence actually establish this?" checks --
# dimension-specific business rules (spec Part 3.3's own admissible-
# evidence column), expressed as callbacks so validate_classification()
# stays generic. Each check receives only the CLAIMS THE RESPONSE ITSELF
# CITED (never the full evidence set) -- the whole point is that a model
# cannot get credit for evidence it didn't even reference.
LabelRequirementCheck = Callable[[str, tuple[Claim, ...]], str | None]


def requires_independent_source(qualifying_labels: frozenset[str]) -> LabelRequirementCheck:
    """A generic requirement: for any label in qualifying_labels, at least
    one of the cited claims must be from an INDEPENDENT_SOURCE_TYPES
    source. Reused by Differentiation Claim Corroboration ("CORROBORATED")
    and Defensibility Signal ("CORROBORATED_MOAT")."""

    def check(label: str, cited: tuple[Claim, ...]) -> str | None:
        if label not in qualifying_labels:
            return None
        if not any(c.source_type in INDEPENDENT_SOURCE_TYPES for c in cited):
            return (
                f"label {label!r} requires at least one independently-sourced cited claim, "
                f"but none of the cited claims ({[c.claim_id for c in cited]}) is independent"
            )
        return None

    return check


def requires_named_entity_fact(qualifying_labels: frozenset[str]) -> LabelRequirementCheck:
    """Task 14 (Team & Leadership): a generic requirement distinct from
    `requires_independent_source` -- some dimensions' own approved
    evidence bar is not about source INDEPENDENCE (a founder's own bio is
    explicitly admissible evidence per spec Part 3.3's own wording for
    Founder Relevant Experience/Public Track Record) but about whether the
    cited evidence names a SPECIFIC, checkable fact (a named company, a
    named role) rather than a vague, unsupported claim ("extensive
    industry experience," with nothing named). For any label in
    qualifying_labels, at least one cited claim must carry a
    `structured_fact` with a non-empty `named_entity` value -- the
    deterministic stand-in for "the AI extracted a specific, checkable
    name from this evidence," the same role `structured_fact` already
    plays throughout this engine (stage-signal claims, Market Opportunity's
    magnitude bands)."""

    def check(label: str, cited: tuple[Claim, ...]) -> str | None:
        if label not in qualifying_labels:
            return None
        if not any((c.structured_fact or {}).get("named_entity") for c in cited):
            return (
                f"label {label!r} requires at least one cited claim naming a specific, checkable "
                f"entity (a company or role), but none of the cited claims "
                f"({[c.claim_id for c in cited]}) name one"
            )
        return None

    return check


def requires_minimum_distinct_facts(label_minimums: dict[str, int]) -> LabelRequirementCheck:
    """For Technical Depth Signal: a label like SUBSTANTIAL requires at
    least N PROVENANCE-VERIFIED distinct facts among the CITED claims
    (Task 10, item 1) -- not just N raw claims, and not just N claims with
    different self-declared `independence_group_id`s, either. Two cited
    claims declared as separate groups but found (by
    app.evidence_engine.provenance) to be a syndicated restatement of the
    same underlying disclosure are folded together here and do not count
    twice."""

    def check(label: str, cited: tuple[Claim, ...]) -> str | None:
        minimum = label_minimums.get(label)
        if minimum is None:
            return None
        result = verify_independence(cited)
        confirmed = len(result.confirmed_independent)
        if confirmed < minimum:
            detail_parts = []
            if result.folded_duplicates:
                detail_parts.append(
                    f"{len(result.folded_duplicates)} cited claim(s) appear to be duplicate/syndicated "
                    f"restatements of an already-counted fact: {[c.claim_id for c in result.folded_duplicates]}"
                )
            if result.unknown_independence:
                detail_parts.append(
                    f"{len(result.unknown_independence)} cited claim(s) have UNKNOWN independence "
                    f"(not counted): {[c.claim_id for c in result.unknown_independence]}"
                )
            detail = " (" + "; ".join(detail_parts) + ")" if detail_parts else ""
            return (
                f"label {label!r} requires >= {minimum} provenance-verified distinct facts among "
                f"cited claims, but only {confirmed} are confirmed independent{detail}"
            )
        return None

    return check


def validate_classification(
    response: ClassificationResponse,
    request: ClassificationRequest,
    all_dimension_evidence: DimensionEvidence,
    label_requirement_check: LabelRequirementCheck | None = None,
) -> list[str]:
    """Returns a list of violations (empty = valid). Never trusts the
    response's label at face value -- every check here re-derives whether
    the citation is real and sufficient from the ledger's own admissible
    evidence, which is exactly what makes this robust to a model that
    fabricates a favorable label, cites evidence it wasn't given, or was
    influenced by injected instructions inside the evidence text itself
    (the label is just a claim; only the cited, real, admissible evidence
    the validator independently re-checks can make it stand)."""
    violations: list[str] = []

    if response.label not in request.allowed_labels:
        violations.append(
            f"{request.dimension}: label {response.label!r} is not one of the allowed labels "
            f"{request.allowed_labels}"
        )
        return violations  # no point checking citations for a structurally invalid label

    admissible_ids = {c.claim_id for c in all_dimension_evidence.admissible}
    admissible_by_id = {c.claim_id: c for c in all_dimension_evidence.admissible}

    cited: list[Claim] = []
    for claim_id in response.supporting_claim_ids:
        if claim_id not in admissible_ids:
            violations.append(
                f"{request.dimension}: cites claim_id {claim_id!r}, which is not currently "
                f"admissible evidence for this dimension (does not exist, is stale, or is disputed)"
            )
            continue
        cited.append(admissible_by_id[claim_id])

    if violations:
        return violations

    if label_requirement_check is not None:
        reason = label_requirement_check(response.label, tuple(cited))
        if reason is not None:
            violations.append(f"{request.dimension}: {reason}")

    return violations


@dataclass(frozen=True)
class ClassificationOutcome:
    response: ClassificationResponse | None
    violations: tuple[str, ...]
    attempts: int
    recovered: bool  # True only if attempt 1 failed and attempt 2 passed


def classify_with_recovery(
    model: ClassificationModel,
    request: ClassificationRequest,
    all_dimension_evidence: DimensionEvidence,
    label_requirement_check: LabelRequirementCheck | None = None,
    max_attempts: int = 2,
) -> ClassificationOutcome:
    """Task 10, item 2. Validation (not a raised exception -- that remains
    the caller's responsibility to catch) is retried once with the prior
    attempt's violations fed back to the model. Every attempt is validated
    identically via validate_classification(); there is no relaxed check
    on a later attempt and no path that accepts an unsupported citation or
    substitutes a score -- a model that is still wrong on the final
    attempt yields `response=None`, which callers must resolve to
    Unscored (never a fabricated fallback)."""
    violations: tuple[str, ...] = ()
    current_request = request
    for attempt in range(1, max_attempts + 1):
        response = model.classify(current_request)
        violations = tuple(validate_classification(response, request, all_dimension_evidence, label_requirement_check))
        if not violations:
            return ClassificationOutcome(response=response, violations=(), attempts=attempt, recovered=attempt > 1)
        if attempt < max_attempts:
            current_request = ClassificationRequest(
                dimension=request.dimension,
                allowed_labels=request.allowed_labels,
                evidence_items=request.evidence_items,
                validation_feedback=violations,
            )
    return ClassificationOutcome(response=None, violations=violations, attempts=max_attempts, recovered=False)


# --- Extraction (Computed dimensions) ---------------------------------------

@dataclass(frozen=True)
class ExtractionRequest:
    dimension: str
    evidence_items: tuple[EvidenceItem, ...]
    validation_feedback: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExtractionResponse:
    artifact_observed: bool
    supporting_claim_ids: tuple[str, ...]


class ExtractionModel(Protocol):
    def extract(self, request: ExtractionRequest) -> ExtractionResponse: ...


def validate_extraction(
    response: ExtractionResponse,
    all_dimension_evidence: DimensionEvidence,
) -> list[str]:
    violations: list[str] = []
    if not response.artifact_observed:
        if response.supporting_claim_ids:
            violations.append("artifact_observed is False but supporting_claim_ids is non-empty")
        return violations

    admissible_ids = {c.claim_id for c in all_dimension_evidence.admissible}
    if not response.supporting_claim_ids:
        violations.append("artifact_observed is True but zero supporting_claim_ids were cited")
    for claim_id in response.supporting_claim_ids:
        if claim_id not in admissible_ids:
            violations.append(f"cites claim_id {claim_id!r}, which is not currently admissible evidence")
    return violations


@dataclass(frozen=True)
class ExtractionOutcome:
    response: ExtractionResponse | None
    violations: tuple[str, ...]
    attempts: int
    recovered: bool


def extract_with_recovery(
    model: ExtractionModel,
    request: ExtractionRequest,
    all_dimension_evidence: DimensionEvidence,
    max_attempts: int = 2,
) -> ExtractionOutcome:
    """Task 10, item 2 -- the Computed-dimension analogue of
    classify_with_recovery(). Same guarantee: every attempt is validated
    identically via validate_extraction(), never relaxed."""
    violations: tuple[str, ...] = ()
    current_request = request
    for attempt in range(1, max_attempts + 1):
        response = model.extract(current_request)
        violations = tuple(validate_extraction(response, all_dimension_evidence))
        if not violations:
            return ExtractionOutcome(response=response, violations=(), attempts=attempt, recovered=attempt > 1)
        if attempt < max_attempts:
            current_request = ExtractionRequest(
                dimension=request.dimension,
                evidence_items=request.evidence_items,
                validation_feedback=violations,
            )
    return ExtractionOutcome(response=None, violations=violations, attempts=max_attempts, recovered=False)


# Concrete mock/adversarial ClassificationModel/ExtractionModel
# implementations live in pillars/product_technology.py (well-behaved
# defaults) and tests/test_adversarial_robustness.py (deliberately
# malicious ones) -- both conform to the Protocols above; no network
# access, no randomness, anywhere in this codebase.
