"""
Task 31 item 5 -- the Analysis Service: the one orchestrator between the
thin API route and the Evidence Engine v1 adapter/persistence.

    Route -> Analysis Service (this module) -> Engine Adapter -> Persistence

Responsible for: validating Evidence-v1 input (item 7 -- website only,
first integration), invoking the adapter, translating its result into a
persisted row, and mapping every failure mode to one of a small, fixed
set of typed outcomes the route can turn into the right HTTP response --
never a raw exception, never a leaked provider/database detail (item 15).
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from enum import Enum

from app.evidence_v1.adapter import EvidenceV1AdapterError, EvidenceV1RunResult, run_evidence_v1_analysis
from app.evidence_v1.config import EVIDENCE_V1_METHODOLOGY_VERSION
from app.evidence_v1.persistence.repository import (
    EvidenceV1AnalysisRow,
    get_evidence_v1_analysis,
    list_evidence_v1_analyses_for_user,
    save_evidence_v1_analysis,
)


class EvidenceV1FailureReason(str, Enum):
    UNSUPPORTED_INPUT = "unsupported_input"           # e.g. no website_url supplied
    NOT_CONFIGURED = "not_configured"                   # missing provider credentials
    ACQUISITION_FAILED = "acquisition_failed"            # provider/pipeline exception
    PERSISTENCE_FAILED = "persistence_failed"            # the run succeeded but saving it did not


class EvidenceV1ServiceError(Exception):
    """Carries a typed reason (never a raw exception message) the route
    maps to a specific HTTP status/user-facing copy -- same discipline
    `app/api.py`'s own analyze_unified() already applies for the legacy
    path, applied here for Evidence v1."""

    def __init__(self, reason: EvidenceV1FailureReason, user_message: str):
        super().__init__(user_message)
        self.reason = reason
        self.user_message = user_message


@dataclass(frozen=True)
class EvidenceV1SubmissionResult:
    analysis_id: str
    company_name: str
    canonical_website: str
    methodology_version: str
    stage: str
    company_coverage_pct: float | None
    company_confidence: str | None
    company_publishable: bool


def submit_evidence_v1_analysis(
    owner_user_id: str, company_name: str | None, website_url: str | None,
) -> EvidenceV1SubmissionResult:
    """item 7: Evidence v1 supports exactly one input shape this task --
    a company name plus a website URL. Anything else (no website, a
    pitch deck, free-form company text alone) fails CLEARLY here, before
    any pipeline work, rather than silently falling back to a different
    behavior or ignoring the unsupported input (item 7's own explicit
    instruction)."""
    company_name = (company_name or "").strip()
    website_url = (website_url or "").strip()

    if not website_url:
        raise EvidenceV1ServiceError(
            EvidenceV1FailureReason.UNSUPPORTED_INPUT,
            "Evidence Engine v1 currently supports company-website analysis only. "
            "Please provide a website URL.",
        )
    if not company_name:
        raise EvidenceV1ServiceError(
            EvidenceV1FailureReason.UNSUPPORTED_INPUT,
            "Evidence Engine v1 requires a company name in addition to the website URL.",
        )

    try:
        run_result: EvidenceV1RunResult = run_evidence_v1_analysis(company_name, website_url)
    except EvidenceV1AdapterError as exc:
        raise EvidenceV1ServiceError(EvidenceV1FailureReason.NOT_CONFIGURED, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 -- provider/pipeline failure, never leaked raw to the client
        traceback.print_exc()
        raise EvidenceV1ServiceError(
            EvidenceV1FailureReason.ACQUISITION_FAILED,
            "The Evidence Engine analysis could not be completed. This can happen if a research "
            "or AI provider is temporarily unavailable. Please try again.",
        ) from exc

    try:
        analysis_id = save_evidence_v1_analysis(owner_user_id, company_name, website_url, run_result)
    except Exception as exc:  # noqa: BLE001 -- the run succeeded; only persistence failed
        traceback.print_exc()
        raise EvidenceV1ServiceError(
            EvidenceV1FailureReason.PERSISTENCE_FAILED,
            "The analysis completed but could not be saved. Please try again.",
        ) from exc

    return EvidenceV1SubmissionResult(
        analysis_id=analysis_id,
        company_name=company_name,
        canonical_website=website_url,
        methodology_version=EVIDENCE_V1_METHODOLOGY_VERSION,
        stage=run_result.stage,
        company_coverage_pct=run_result.company_coverage_pct,
        company_confidence=run_result.company_confidence,
        company_publishable=run_result.company_publishable,
    )


def get_owned_evidence_v1_analysis(analysis_id: str, viewer_user_id: str) -> EvidenceV1AnalysisRow | None:
    """item 10/20: looked up by id, then OWNERSHIP is checked here --
    against the verified, authenticated caller's own user_id, never a
    company name, never a client-supplied owner field. Returns `None`
    both when the id does not exist AND when it exists but belongs to a
    different user -- the caller (the route) turns both into the SAME
    404, exactly `app/auth.py::require_startup_member()`'s own
    'never distinguish not-found from not-yours' discipline, so probing
    ids can never be used to enumerate which analyses exist."""
    row = get_evidence_v1_analysis(analysis_id)
    if row is None or row.owner_user_id != viewer_user_id:
        return None
    return row


def list_my_evidence_v1_analyses(owner_user_id: str) -> list[dict]:
    return list_evidence_v1_analyses_for_user(owner_user_id)
