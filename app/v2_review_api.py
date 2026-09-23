"""
VentureGPS V2 -- internal evidence review API (Increment 18.4). Every route requires a real, verified Clerk
session AND server-side admin authorization (app.auth.RequireAdmin, unchanged -- the same dependency already
gating /admin/analytics and the startup-claims admin endpoints). There is no unauthenticated route in this
module, including reads: candidate evidence and identity information are internal, not public.

ARCHITECTURE: this file lives on the LEGACY side (app/, not app/v2/) on purpose. V2's own ADR forbids
app/v2/** from importing legacy code (app.auth among it) -- and this module genuinely needs both `RequireAdmin`
and the verified `current_user.user_id` (to derive reviewer identity -- see _authority_for below). The
established, already-used direction is legacy importing V2, never the reverse (app/api.py already imports and
mounts app.v2.api's own router the same way); this file does the same for the human-review side. It calls only
existing, unmodified V2 services: app.v2.resolution.human_review, app.v2.financing_resolution.promotion,
app.v2.classification.service, and the read repositories -- it implements NO canonical business rule of its own.

SECURITY, restated concretely (see docs/v2/INTERNAL_REVIEW_SECURITY.md for the full write-up):
  - Every endpoint requires RequireAdmin. A missing/invalid token is 401; a valid, non-admin token is 403 --
    both from the SAME unmodified dependency every other admin endpoint in this codebase already uses.
  - Reviewer identity (the Authority recorded on every decision) is derived EXCLUSIVELY from
    current_user.user_id -- the verified JWT `sub` claim. No request body, query parameter, or header ever
    supplies an authority id; DecideCompanyRequest/DecideFinancingRequest/ClassifyRequest have no such field at
    all, so there is nothing for a client to forge.
  - Evidence shown to a reviewer is RE-VERIFIED against the exact stored payload bytes on every single read
    (app.v2.candidates.evidence.verify_proposal / app.v2.candidates.financing_evidence.verify_financing_proposal)
    -- never just trusted from the stored candidate row. If verification ever fails (e.g. the underlying payload
    were somehow corrupted), the read fails loudly (500) rather than silently showing unverifiable text.
  - Duplicate/replay decision submissions are refused by the SAME database-enforced uniqueness Increment 18.2
    already has (uq_resolution_decision_one_final / uq_frd_one_final) -- CandidateAlreadyResolvedError /
    FinancingCandidateAlreadyResolvedError map to a clean 409, never a silent no-op and never a second decision.
  - Financing decisions are only reachable once the candidate's company_id resolves to a real canonical Company
    (re-checked server-side on every read AND every decide call, never assumed from the candidate alone).
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import DBAPIError, OperationalError

from app.auth import AuthenticatedUser, RequireAdmin
from app.observability import capture_exception
from app.v2.candidates.evidence import verify_proposal
from app.v2.candidates.financing_evidence import verify_financing_proposal
from app.v2.classification.service import classify_company, list_classifications_for_company
from app.v2.config import ConfigurationError
from app.v2.db.engine import get_engine
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError, UnsupportedInputError
from app.v2.domain.financing import FinancingDateKind
from app.v2.domain.financing_resolution import FactSelection
from app.v2.domain.resolution import Authority, human_authority
from app.v2.domain.taxonomy import ClassificationRole
from app.v2.financing_resolution import promotion as financing_promotion
from app.v2.repositories.companies import (
    find_company_ids_by_identifier,
    get_candidate_resolution_state,
    get_company,
    list_company_identifiers,
    list_company_names,
    list_decisions_for_candidate,
    list_pending_company_candidates,
)
from app.v2.repositories.company_candidates import get_company_candidate
from app.v2.repositories.errors import ConflictError, NotFoundError
from app.v2.repositories.financing_event_candidates import get_financing_event_candidate
from app.v2.repositories.financing_events import (
    get_financing_candidate_resolution_state,
    list_decisions_for_financing_candidate,
    list_financing_events_for_company,
    list_pending_financing_candidates,
)
from app.v2.repositories.markets import list_markets, list_taxonomy_versions
from app.v2.repositories.observations import get_observation_by_id
from app.v2.repositories.processing_attempts import get_processing_attempt
from app.v2.repositories.raw_payloads import get_raw_payload
from app.v2.repositories.sources import get_source_by_id, get_source_by_key
from app.v2.resolution import human_review

router = APIRouter(prefix="/admin/v2-review", tags=["v2-internal-review"])

_SERVICE_UNAVAILABLE = "V2 review service is temporarily unavailable."
MAX_EVIDENCE_EXCERPT_BYTES = 4096  # matches app.v2.domain.candidate.MAX_EVIDENCE_SPAN_BYTES; nothing larger is ever shown


def _engine_or_503():
    try:
        return get_engine()
    except ConfigurationError:
        raise HTTPException(status_code=503, detail=_SERVICE_UNAVAILABLE) from None


def _run(fn, *args, **kwargs):
    """Every DB-touching call goes through here -- mirrors app.v2.api's own _run exactly (unreachable database ->
    generic 503; anything unexpected -> logged, generic 500; never a stack trace or connection string to the
    client)."""
    try:
        return fn(*args, **kwargs)
    except (OperationalError, DBAPIError):
        raise HTTPException(status_code=503, detail=_SERVICE_UNAVAILABLE) from None
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - the one deliberate catch-all, matching app.v2.api's own pattern
        capture_exception(exc)
        raise HTTPException(status_code=500, detail="An internal error occurred.") from None


def _authority_for(current_user: AuthenticatedUser) -> Authority:
    """The ONLY place a reviewer's Authority is constructed anywhere in this module -- from the verified session
    alone. Clerk's own user_id shape (e.g. "user_2abc...") does not itself match the human-actor "kind:name"
    shape app.v2.domain.resolution.Authority requires, so it is prefixed, never substituted for or accepted from
    the client. If this somehow still fails validation (it shouldn't, for a real Clerk id), that is a genuine
    server error, not a 400 -- the client supplied nothing here to get wrong."""
    try:
        return human_authority(f"admin:{current_user.user_id}")
    except InvalidInputError as exc:
        capture_exception(exc)
        raise HTTPException(status_code=500, detail="Could not derive a reviewer identity for this session.") from None


# ---------------------------------------------------------------- shared shapes

class EvidenceExcerpt(BaseModel):
    text: str
    byte_start: int
    byte_end: int


class SourceInfo(BaseModel):
    source_key: str
    name: str
    source_type: str
    collection_method: str


class ProvenanceInfo(BaseModel):
    observation_id: int
    source: SourceInfo
    source_record_identifier: str | None
    observed_time: str  # first-ever acquisition (Observation.observed_time), ISO 8601
    collector_id: str
    collection_version: str


def _provenance_for(engine, processing_attempt_id: int) -> ProvenanceInfo:
    """attempt -> observation -> source, all read-only. StoredObservation carries id/source_id on the OUTER
    object and the original Observation (source_key, observed_time, collector_id, ...) nested at .observation."""
    attempt = _run(get_processing_attempt, engine, processing_attempt_id)
    stored_observation = _run(get_observation_by_id, engine, attempt.observation_id)
    source = _run(get_source_by_id, engine, stored_observation.source_id)
    if source is None:
        source = _run(get_source_by_key, engine, stored_observation.observation.source_key)
    return ProvenanceInfo(
        observation_id=stored_observation.id,
        source=SourceInfo(source_key=source.source.source_key, name=source.source.name,
                          source_type=source.source.source_type.value, collection_method=source.source.collection_method.value),
        source_record_identifier=stored_observation.observation.source_record_identifier,
        observed_time=stored_observation.observation.observed_time.isoformat(),
        collector_id=stored_observation.observation.collector_id,
        collection_version=stored_observation.observation.collection_version,
    )


def _excerpt(payload_bytes: bytes, byte_start: int, byte_end: int) -> EvidenceExcerpt:
    return EvidenceExcerpt(text=payload_bytes[byte_start:byte_end].decode("utf-8", errors="replace"), byte_start=byte_start, byte_end=byte_end)


def _live_payload_and_media_type(engine, processing_attempt_id: int):
    """Re-fetch the CURRENT attempt -> observation -> RawPayload from the database (never a cached/stored copy),
    for the byte-exact re-verification every read and every decision requires."""
    attempt = _run(get_processing_attempt, engine, processing_attempt_id)
    observation = _run(get_observation_by_id, engine, attempt.observation_id)
    payload = _run(get_raw_payload, engine, observation.observation.content_hash, verify=True)
    return payload, observation.observation.sniffed_media_type


def _domain_detail(exc: DomainError) -> str:
    # A plain string, not a nested object: app/lib/api/client.ts's apiFetch only extracts a string `detail`
    # field (FastAPI's own default error shape), so a dict here would silently be dropped on the frontend.
    return f"{exc.code}: {exc.message}"


def _domain_call(fn, *args, **kwargs):
    """Every state-changing call (promotion, classification) goes through here instead of _run: it adds typed
    domain-error -> HTTP-status translation on top of _run's DB-unavailable/unexpected handling, using each
    error's own existing static `code`/`message` (chosen by the domain, never built from request or payload
    data, so it is always safe to return). NotFoundError -> 404. ConflictError and everything that subclasses it
    (CandidateAlreadyResolvedError, IdentifierConflictError, FinancingCandidateAlreadyResolvedError,
    WrongCompanyError, FactAlreadyAcceptedError, FactNotAvailableError, AlreadyClassifiedError,
    PrimaryAlreadyAssignedError) -> 409, which is what makes a duplicate/replayed decision submission a clean
    refusal rather than a second decision. InvalidInputError/UnsupportedInputError -> 400. InvariantViolationError
    -> 403 (an authority was not permitted to make this decision -- should not happen for our own server-derived
    HUMAN authority, but never silently allowed if it somehow did)."""
    try:
        return fn(*args, **kwargs)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=_domain_detail(exc)) from None
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=_domain_detail(exc)) from None
    except (InvalidInputError, UnsupportedInputError) as exc:
        raise HTTPException(status_code=400, detail=_domain_detail(exc)) from None
    except InvariantViolationError as exc:
        raise HTTPException(status_code=403, detail=_domain_detail(exc)) from None
    except DomainError as exc:  # any other/future domain error type: still safe to surface, never swallowed
        raise HTTPException(status_code=400, detail=_domain_detail(exc)) from None
    except HTTPException:
        raise
    except (OperationalError, DBAPIError):
        raise HTTPException(status_code=503, detail=_SERVICE_UNAVAILABLE) from None
    except Exception as exc:  # noqa: BLE001 - matches _run's own catch-all
        capture_exception(exc)
        raise HTTPException(status_code=500, detail="An internal error occurred.") from None


def _decision_out(d) -> "DecisionOut":
    return DecisionOut(
        id=d.id, decision_kind=d.decision_kind.value,
        company_id=str(getattr(d, "company_id", None)) if getattr(d, "company_id", None) else None,
        financing_event_id=str(getattr(d, "financing_event_id", None)) if getattr(d, "financing_event_id", None) else None,
        authority_kind=d.authority.kind.value, authority_id=d.authority.id,
        reason_code=d.reason_code, created_at=d.created_at.isoformat(),
    )


def _classification_out(c) -> "ClassificationOut":
    return ClassificationOut(id=c.id, company_id=str(c.company_id), market_id=str(c.market_id),
                             taxonomy_version=c.taxonomy_version, role=c.role.value,
                             authority_id=c.authority.id, created_at=c.created_at.isoformat())


# ---------------------------------------------------------------- company-candidate shapes

class CompanyCandidateSummary(BaseModel):
    id: int
    processing_attempt_id: int
    candidate_ordinal: int
    proposed_name: str
    created_at: str
    resolution_state: str


class ProposedIdentifierOut(BaseModel):
    identifier_type: str
    value: str
    evidence: EvidenceExcerpt


class DecisionOut(BaseModel):
    id: int
    decision_kind: str
    company_id: str | None = None
    financing_event_id: str | None = None
    authority_kind: str
    authority_id: str
    reason_code: str | None = None
    created_at: str


class IdentityMatch(BaseModel):
    """A proposed identifier and every canonical Company that already owns it -- shown so a reviewer can choose
    ATTACH over CREATE when one is found, instead of guessing. Company identifiers are unique by constraint, so
    this list has at most one entry per identifier, but is a list because the frontend must never assume that."""
    identifier_type: str
    value: str
    matching_company_ids: list[str]


class CompanyCandidateDetail(BaseModel):
    id: int
    processing_attempt_id: int
    candidate_ordinal: int
    created_at: str
    resolution_state: str
    proposed_name: str
    name_evidence: EvidenceExcerpt
    identifiers: list[ProposedIdentifierOut]
    provenance: ProvenanceInfo
    decisions: list[DecisionOut]
    identity_matches: list[IdentityMatch]


class DecideCompanyRequest(BaseModel):
    """No authority/reviewer field -- see _authority_for. `confirm` must be explicitly true: this is the UI's
    required confirmation step for a consequential decision, enforced server-side, not just by a frontend dialog."""
    action: Literal["create", "attach", "reject", "defer"]
    company_id: UUID | None = None
    reason_code: str | None = None
    confirm: bool = False

    @model_validator(mode="after")
    def _shape_matches_the_action(self) -> "DecideCompanyRequest":
        if self.action == "attach" and self.company_id is None:
            raise ValueError("company_id is required to attach a candidate to an existing company")
        if self.action != "attach" and self.company_id is not None:
            raise ValueError("company_id is only accepted for attach")
        if self.action in ("reject", "defer") and not self.reason_code:
            raise ValueError("reason_code is required to reject or defer a candidate")
        if not self.confirm:
            raise ValueError("confirm must be true to submit a review decision")
        return self


class DecisionResult(BaseModel):
    decision_id: int | None = None
    decision_kind: str
    company_id: str | None = None
    financing_event_id: str | None = None
    accepted_name: bool = False
    accepted_identifier_count: int = 0
    accepted_stage: bool = False
    accepted_financing_type: bool = False
    accepted_verified_round_amount: bool = False
    accepted_dates: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- financing-candidate shapes

class FinancingCandidateSummary(BaseModel):
    id: int
    processing_attempt_id: int
    candidate_ordinal: int
    company_id: str
    created_at: str
    resolution_state: str


class ProposedAmountOut(BaseModel):
    semantics: str
    currency_code: str
    minor_units: int
    evidence: EvidenceExcerpt


class ProposedDateOut(BaseModel):
    kind: str
    precision: str
    start: str
    evidence: EvidenceExcerpt


class FinancingCandidateDetail(BaseModel):
    id: int
    processing_attempt_id: int
    candidate_ordinal: int
    created_at: str
    resolution_state: str
    company_id: str
    company_is_canonical: bool
    event_evidence: EvidenceExcerpt
    stage: str | None = None
    stage_evidence: EvidenceExcerpt | None = None
    financing_type: str | None = None
    financing_type_evidence: EvidenceExcerpt | None = None
    amounts: list[ProposedAmountOut]
    dates: list[ProposedDateOut]
    provenance: ProvenanceInfo
    decisions: list[DecisionOut]
    existing_events: list[str]  # canonical FinancingEvent ids already open for this company (candidates for attach)


class FactSelectionIn(BaseModel):
    stage: bool = False
    financing_type: bool = False
    verified_round_amount: bool = False
    dates: list[Literal["first_sale_date", "filing_date", "announcement_date"]] = Field(default_factory=list)

    @property
    def is_empty_input(self) -> bool:
        return not (self.stage or self.financing_type or self.verified_round_amount or self.dates)


class DecideFinancingRequest(BaseModel):
    action: Literal["create_event", "attach_to_event", "reject", "defer"]
    event_id: UUID | None = None
    facts: FactSelectionIn = Field(default_factory=FactSelectionIn)
    reason_code: str | None = None
    confirm: bool = False

    @model_validator(mode="after")
    def _shape_matches_the_action(self) -> "DecideFinancingRequest":
        if self.action == "attach_to_event" and self.event_id is None:
            raise ValueError("event_id is required to attach a candidate to an existing financing event")
        if self.action != "attach_to_event" and self.event_id is not None:
            raise ValueError("event_id is only accepted for attach_to_event")
        if self.action in ("reject", "defer") and not self.reason_code:
            raise ValueError("reason_code is required to reject or defer a candidate")
        if self.action in ("reject", "defer") and not self.facts.is_empty_input:
            raise ValueError("facts cannot be selected on a reject or defer decision")
        if not self.confirm:
            raise ValueError("confirm must be true to submit a review decision")
        return self


# ---------------------------------------------------------------- company / classification shapes

class CompanyNameOut(BaseModel):
    name: str
    role: str


class CompanyIdentifierOut(BaseModel):
    identifier_type: str
    value: str


class ClassificationOut(BaseModel):
    id: int
    company_id: str
    market_id: str
    taxonomy_version: str
    role: str
    authority_id: str
    created_at: str


class CompanyDetail(BaseModel):
    id: str
    created_at: str
    names: list[CompanyNameOut]
    identifiers: list[CompanyIdentifierOut]
    classifications: list[ClassificationOut]


class MarketOut(BaseModel):
    id: str
    slug: str
    display_name: str


class ClassifyRequest(BaseModel):
    market_id: UUID
    taxonomy_version: str
    role: Literal["primary", "secondary"] = "primary"
    confirm: bool = False

    @model_validator(mode="after")
    def _confirmed(self) -> "ClassifyRequest":
        if not self.confirm:
            raise ValueError("confirm must be true to submit a classification decision")
        return self


# ================================================================== company candidates

@router.get("/company-candidates", response_model=list[CompanyCandidateSummary])
def list_company_candidates_endpoint(limit: int = 50, offset: int = 0, current_user: AuthenticatedUser = RequireAdmin):
    engine = _engine_or_503()
    candidates = _run(list_pending_company_candidates, engine, limit, offset)
    return [
        CompanyCandidateSummary(
            id=c.id, processing_attempt_id=c.processing_attempt_id, candidate_ordinal=c.candidate_ordinal,
            proposed_name=c.proposal.proposed_name, created_at=c.created_at.isoformat(),
            resolution_state=_run(get_candidate_resolution_state, engine, c.id).value,
        )
        for c in candidates
    ]


@router.get("/company-candidates/{candidate_id}", response_model=CompanyCandidateDetail)
def get_company_candidate_detail(candidate_id: int, current_user: AuthenticatedUser = RequireAdmin):
    engine = _engine_or_503()
    candidate = _run(get_company_candidate, engine, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidate not found")

    payload, media_type = _live_payload_and_media_type(engine, candidate.processing_attempt_id)
    # Re-verify the WHOLE proposal (name + every identifier) against the live payload bytes before showing or
    # trusting anything from the stored row -- catches evidence tampering rather than displaying unverifiable text.
    _run(verify_proposal, candidate.proposal, payload, media_type, ordinal=candidate.candidate_ordinal)
    data = payload.payload_bytes

    identifiers = [
        ProposedIdentifierOut(identifier_type=i.identifier_type.value, value=i.value,
                              evidence=_excerpt(data, i.evidence.byte_start, i.evidence.byte_end))
        for i in candidate.proposal.identifiers
    ]
    identity_matches = [
        IdentityMatch(identifier_type=i.identifier_type.value, value=i.value,
                     matching_company_ids=[str(cid) for cid in _run(find_company_ids_by_identifier, engine, i.identifier_type, i.value)])
        for i in candidate.proposal.identifiers
    ]
    decisions = [_decision_out(d) for d in _run(list_decisions_for_candidate, engine, candidate_id)]

    return CompanyCandidateDetail(
        id=candidate.id, processing_attempt_id=candidate.processing_attempt_id, candidate_ordinal=candidate.candidate_ordinal,
        created_at=candidate.created_at.isoformat(),
        resolution_state=_run(get_candidate_resolution_state, engine, candidate_id).value,
        proposed_name=candidate.proposal.proposed_name,
        name_evidence=_excerpt(data, candidate.proposal.name_evidence.byte_start, candidate.proposal.name_evidence.byte_end),
        identifiers=identifiers, provenance=_provenance_for(engine, candidate.processing_attempt_id),
        decisions=decisions, identity_matches=identity_matches,
    )


@router.post("/company-candidates/{candidate_id}/decide", response_model=DecisionResult)
def decide_company_candidate(candidate_id: int, body: DecideCompanyRequest, current_user: AuthenticatedUser = RequireAdmin):
    engine = _engine_or_503()
    authority = _authority_for(current_user)

    candidate = _run(get_company_candidate, engine, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    payload, media_type = _live_payload_and_media_type(engine, candidate.processing_attempt_id)
    # Re-verify again, right before acting on it: a decision is consequential, so it re-checks evidence
    # independently of whatever the reviewer last saw on the detail screen.
    _run(verify_proposal, candidate.proposal, payload, media_type, ordinal=candidate.candidate_ordinal)

    if body.action == "create":
        result = _domain_call(human_review.create_company_from_candidate, engine, candidate_id, authority)
    elif body.action == "attach":
        result = _domain_call(human_review.attach_candidate_to_company, engine, candidate_id, body.company_id, authority)
    elif body.action == "reject":
        result = _domain_call(human_review.reject_candidate, engine, candidate_id, authority, body.reason_code)
    else:
        result = _domain_call(human_review.defer_candidate, engine, candidate_id, authority, body.reason_code)

    return DecisionResult(
        decision_id=result.decision.id, decision_kind=result.decision.decision_kind.value,
        company_id=str(result.company_id) if result.company_id else None,
        accepted_name=result.accepted_name, accepted_identifier_count=result.accepted_identifier_count,
    )


# ================================================================== financing candidates

@router.get("/financing-candidates", response_model=list[FinancingCandidateSummary])
def list_financing_candidates_endpoint(limit: int = 50, offset: int = 0, current_user: AuthenticatedUser = RequireAdmin):
    engine = _engine_or_503()
    candidates = _run(list_pending_financing_candidates, engine, limit, offset)
    return [
        FinancingCandidateSummary(
            id=c.id, processing_attempt_id=c.processing_attempt_id, candidate_ordinal=c.candidate_ordinal,
            company_id=str(c.proposal.company_id), created_at=c.created_at.isoformat(),
            resolution_state=_run(get_financing_candidate_resolution_state, engine, c.id).value,
        )
        for c in candidates
    ]


@router.get("/financing-candidates/{candidate_id}", response_model=FinancingCandidateDetail)
def get_financing_candidate_detail(candidate_id: int, current_user: AuthenticatedUser = RequireAdmin):
    engine = _engine_or_503()
    candidate = _run(get_financing_event_candidate, engine, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidate not found")

    payload, media_type = _live_payload_and_media_type(engine, candidate.processing_attempt_id)
    _run(verify_financing_proposal, candidate.proposal, payload, media_type, ordinal=candidate.candidate_ordinal)
    data = payload.payload_bytes
    proposal = candidate.proposal

    # Never assumed from the candidate's structural requirement (a financing candidate can only ever have been
    # persisted against an id that WAS canonical at write time) -- re-checked fresh, right now, regardless.
    company = _run(get_company, engine, proposal.company_id)

    stage_out = stage_evidence = None
    if proposal.stage is not None:
        stage_out = proposal.stage.stage.value
        stage_evidence = _excerpt(data, proposal.stage.evidence.byte_start, proposal.stage.evidence.byte_end)
    type_out = type_evidence = None
    if proposal.financing_type is not None:
        type_out = proposal.financing_type.financing_type.value
        type_evidence = _excerpt(data, proposal.financing_type.evidence.byte_start, proposal.financing_type.evidence.byte_end)

    amounts = [
        ProposedAmountOut(semantics=a.semantics.value, currency_code=a.money.currency_code, minor_units=a.money.minor_units,
                          evidence=_excerpt(data, a.evidence.byte_start, a.evidence.byte_end))
        for a in proposal.amounts
    ]
    dates = [
        ProposedDateOut(kind=d.kind.value, precision=d.time.precision.value, start=d.time.start.isoformat(),
                        evidence=_excerpt(data, d.evidence.byte_start, d.evidence.byte_end))
        for d in proposal.dates
    ]
    decisions = [_decision_out(d) for d in _run(list_decisions_for_financing_candidate, engine, candidate_id)]
    existing_events = _run(list_financing_events_for_company, engine, proposal.company_id) if company is not None else []

    return FinancingCandidateDetail(
        id=candidate.id, processing_attempt_id=candidate.processing_attempt_id, candidate_ordinal=candidate.candidate_ordinal,
        created_at=candidate.created_at.isoformat(),
        resolution_state=_run(get_financing_candidate_resolution_state, engine, candidate_id).value,
        company_id=str(proposal.company_id), company_is_canonical=company is not None,
        event_evidence=_excerpt(data, proposal.event_evidence.byte_start, proposal.event_evidence.byte_end),
        stage=stage_out, stage_evidence=stage_evidence, financing_type=type_out, financing_type_evidence=type_evidence,
        amounts=amounts, dates=dates, provenance=_provenance_for(engine, candidate.processing_attempt_id),
        decisions=decisions, existing_events=[str(e.id) for e in existing_events],
    )


@router.post("/financing-candidates/{candidate_id}/decide", response_model=DecisionResult)
def decide_financing_candidate(candidate_id: int, body: DecideFinancingRequest, current_user: AuthenticatedUser = RequireAdmin):
    engine = _engine_or_503()
    authority = _authority_for(current_user)

    candidate = _run(get_financing_event_candidate, engine, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidate not found")

    # The server-side gate required by Increment 18.4 item 4: never take the frontend's word that the candidate's
    # company is canonical. Structurally it always is (persist_financing_event_candidates only ever accepts a
    # company_id already present in the canonical company table) -- this re-checks it fresh anyway, in front of
    # every decision, rather than only trusting that invariant.
    if _run(get_company, engine, candidate.proposal.company_id) is None:
        raise HTTPException(status_code=409, detail="the candidate's company is not canonical; it cannot be reviewed")

    payload, media_type = _live_payload_and_media_type(engine, candidate.processing_attempt_id)
    _run(verify_financing_proposal, candidate.proposal, payload, media_type, ordinal=candidate.candidate_ordinal)

    facts = FactSelection(stage=body.facts.stage, financing_type=body.facts.financing_type,
                          verified_round_amount=body.facts.verified_round_amount,
                          dates=tuple(FinancingDateKind(k) for k in body.facts.dates))

    if body.action == "create_event":
        result = _domain_call(financing_promotion.create_event_from_candidate, engine, candidate_id, authority, facts)
    elif body.action == "attach_to_event":
        result = _domain_call(financing_promotion.attach_candidate_to_event, engine, candidate_id, body.event_id, authority, facts)
    elif body.action == "reject":
        result = _domain_call(financing_promotion.reject_candidate, engine, candidate_id, authority, body.reason_code)
    else:
        result = _domain_call(financing_promotion.defer_candidate, engine, candidate_id, authority, body.reason_code)

    return DecisionResult(
        decision_id=result.decision.id if result.decision else None,
        decision_kind=result.decision.decision_kind.value if result.decision else body.action,
        financing_event_id=str(result.financing_event_id) if result.financing_event_id else None,
        accepted_stage=result.accepted_stage, accepted_financing_type=result.accepted_financing_type,
        accepted_verified_round_amount=result.accepted_verified_round_amount,
        accepted_dates=[k.value for k in result.accepted_dates],
    )


# ================================================================== companies / market classification

@router.get("/companies/{company_id}", response_model=CompanyDetail)
def get_company_detail(company_id: UUID, current_user: AuthenticatedUser = RequireAdmin):
    engine = _engine_or_503()
    company = _run(get_company, engine, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")
    names = [CompanyNameOut(name=n.name, role=n.name_role.value) for n in _run(list_company_names, engine, company_id)]
    identifiers = [CompanyIdentifierOut(identifier_type=i.identifier_type.value, value=i.identifier_value)
                   for i in _run(list_company_identifiers, engine, company_id)]
    classifications = [_classification_out(c) for c in _run(list_classifications_for_company, engine, company_id)]
    return CompanyDetail(id=str(company.id), created_at=company.created_at.isoformat(),
                         names=names, identifiers=identifiers, classifications=classifications)


@router.get("/markets", response_model=list[MarketOut])
def list_markets_endpoint(current_user: AuthenticatedUser = RequireAdmin):
    engine = _engine_or_503()
    return [MarketOut(id=str(m.id), slug=m.slug, display_name=m.display_name) for m in _run(list_markets, engine)]


@router.get("/taxonomy-versions", response_model=list[str])
def list_taxonomy_versions_endpoint(current_user: AuthenticatedUser = RequireAdmin):
    engine = _engine_or_503()
    return [t.taxonomy_version for t in _run(list_taxonomy_versions, engine)]


@router.post("/companies/{company_id}/classify", response_model=ClassificationOut)
def classify_company_endpoint(company_id: UUID, body: ClassifyRequest, current_user: AuthenticatedUser = RequireAdmin):
    engine = _engine_or_503()
    authority = _authority_for(current_user)
    result = _domain_call(classify_company, engine, company_id, body.market_id, body.taxonomy_version,
                          ClassificationRole(body.role), authority)
    return _classification_out(result.classification)
