"""
Offline fixture: Notion. See fixtures/__init__.py's disclaimer -- generic,
conservatively-phrased, widely-known public facts only, hand-authored for
this vertical slice, not the output of a real research pass.

Designed to produce a fully SCORABLE Product & Technology pillar: an
independently-observable product artifact, an independently-corroborated
differentiation claim, three distinct named technical facts (SUBSTANTIAL
band), and an independently-corroborated defensibility claim.
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.models import Claim, SourceType, SupportStatus

COMPANY_REF = "notion"

RETRIEVED_AT = date(2026, 9, 1)

CLAIMS: list[Claim] = [
    Claim(
        claim_id="notion-001",
        company_ref=COMPANY_REF,
        claim_text="Notion's product is available as a web application and as native desktop and mobile applications.",
        subject_entity="Notion",
        source_url="https://www.notion.so",
        source_publisher="Notion (product website)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Notion is available via web browser and as native desktop and mobile apps.",
        assessment_criteria=["product_existence_maturity"],
        independence_group_id="notion-product-existence",
    ),
    Claim(
        claim_id="notion-002",
        company_ref=COMPANY_REF,
        claim_text=(
            "Independent software-review coverage describes Notion as combining notes, "
            "documents, and project tracking in a single connected workspace, a combination "
            "frequently contrasted with single-purpose competitor tools."
        ),
        subject_entity="Notion",
        source_publisher="a technology/software-review publication",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="...combines notes, docs, wikis, and light project tracking into one connected workspace...",
        assessment_criteria=["differentiation_claim_corroboration"],
        independence_group_id="notion-differentiation-review",
    ),
    Claim(
        claim_id="notion-003",
        company_ref=COMPANY_REF,
        claim_text="Notion publishes a public API enabling third-party integrations.",
        subject_entity="Notion",
        source_publisher="Notion (developer documentation)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Notion offers a public API for building integrations.",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="notion-api",
    ),
    Claim(
        claim_id="notion-004",
        company_ref=COMPANY_REF,
        claim_text="Notion integrates with Slack.",
        subject_entity="Notion",
        source_publisher="an independent integration/reporting source",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Notion offers a Slack integration for sharing page updates.",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="notion-integration-slack",
    ),
    Claim(
        claim_id="notion-005",
        company_ref=COMPANY_REF,
        claim_text="Notion integrates with Google Drive.",
        subject_entity="Notion",
        source_publisher="an independent integration/reporting source",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Notion supports embedding and linking Google Drive files.",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="notion-integration-gdrive",
    ),
    Claim(
        claim_id="notion-stage-001",
        company_ref=COMPANY_REF,
        claim_text=(
            "Independent reporting describes Notion as a mature, growth-stage company with a "
            "multi-year funding and operating history."
        ),
        subject_entity="Notion",
        source_publisher="a business/technology publication",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="...described as a mature, growth-stage company...",
        assessment_criteria=["stage_signal"],
        independence_group_id="notion-stage-maturity",
        structured_fact={"kind": "funding_round_type", "value": "growth-stage financing"},
    ),
    Claim(
        claim_id="notion-006",
        company_ref=COMPANY_REF,
        claim_text=(
            "Independent reporting describes Notion's large, actively-contributing template "
            "and community ecosystem as a factor supporting retention within organizations "
            "already using it."
        ),
        subject_entity="Notion",
        source_publisher="a technology/business publication",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="...a large community of template creators and power users contributes to ongoing adoption within teams...",
        assessment_criteria=["defensibility_signal"],
        independence_group_id="notion-ecosystem-defensibility",
    ),
]
