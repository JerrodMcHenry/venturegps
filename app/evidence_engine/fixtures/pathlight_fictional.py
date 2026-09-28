"""
Offline fixture: "Pathlight" -- a wholly FICTIONAL, Pre-Seed-stage company
invented for this calibration pass. No real company by this name is
referenced or intended.

Designed to exercise:
  - The age-based stage-determination fallback (no disclosed funding round,
    only a founding year -- spec Part 4.1's second-priority signal).
  - Stage-sensitive scoring directly: Pathlight's one independently-
    corroborated differentiation claim should score HIGHER at its early
    stage than the identical CORROBORATED label scores for an established
    company (Notion) -- the same evidence, more remarkable at this stage.
  - A genuinely sparse-but-real evidence profile (2 of 4 dimensions
    scorable), distinct from Linear's own partial profile.
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.models import Claim, SourceType, SupportStatus

COMPANY_REF = "pathlight_fictional"

RETRIEVED_AT = date(2026, 9, 1)

CLAIMS: list[Claim] = [
    Claim(
        claim_id="pathlight-stage-001",
        company_ref=COMPANY_REF,
        claim_text="Pathlight was founded in 2024, per its own public materials.",
        subject_entity="Pathlight",
        source_publisher="Pathlight (public materials)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Founded in 2024.",
        assessment_criteria=["stage_signal"],
        independence_group_id="pathlight-founding-year",
        structured_fact={"kind": "founding_year", "value": "2024"},
    ),
    Claim(
        claim_id="pathlight-001",
        company_ref=COMPANY_REF,
        claim_text="Pathlight has a public landing page describing and demonstrating its product.",
        subject_entity="Pathlight",
        source_publisher="Pathlight (product website)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="A public product demo and description are available on Pathlight's site.",
        assessment_criteria=["product_existence_maturity"],
        independence_group_id="pathlight-product-existence",
    ),
    Claim(
        claim_id="pathlight-002",
        company_ref=COMPANY_REF,
        claim_text=(
            "An accelerator demo-day writeup independently describes Pathlight's approach as "
            "distinct from existing tools in its category."
        ),
        subject_entity="Pathlight",
        source_publisher="an accelerator/demo-day program writeup",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="...Pathlight's approach was noted as distinct from existing tools in the category...",
        assessment_criteria=["differentiation_claim_corroboration"],
        independence_group_id="pathlight-differentiation-demoday",
    ),
    Claim(
        claim_id="pathlight-003",
        company_ref=COMPANY_REF,
        claim_text="Pathlight integrates with one named third-party data provider.",
        subject_entity="Pathlight",
        source_publisher="an independent integration/reporting source",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Pathlight offers an integration with a named data provider.",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="pathlight-integration-dataprovider",
    ),
    # Defensibility: too early for any moat evidence to exist -- no claim
    # tagged, deliberately.
]
