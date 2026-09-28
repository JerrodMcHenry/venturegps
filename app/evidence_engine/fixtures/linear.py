"""
Offline fixture: Linear. See fixtures/__init__.py's disclaimer.

Designed to produce a PARTIALLY scorable Product & Technology pillar
(2 of 4 dimensions scorable, 2 correctly Unscored) -- deliberately thinner
public-disclosure footprint than Notion's fixture, to test that a real
coverage difference is reported honestly rather than either (a) forced
into an equally rich profile or (b) read as evidence of weaker
performance (spec Design Principle 5).
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.models import Claim, SourceType, SupportStatus

COMPANY_REF = "linear"

RETRIEVED_AT = date(2026, 9, 1)

CLAIMS: list[Claim] = [
    Claim(
        claim_id="linear-001",
        company_ref=COMPANY_REF,
        claim_text="Linear's product is available as a web application and a native desktop application.",
        subject_entity="Linear",
        source_url="https://linear.app",
        source_publisher="Linear (product website)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Linear is available via web browser and as a native desktop app.",
        assessment_criteria=["product_existence_maturity"],
        independence_group_id="linear-product-existence",
    ),
    # Differentiation: only the company's own product materials describe
    # its interface as fast/keyboard-driven -- no independent comparison is
    # on record in this fixture, so this dimension must resolve to
    # UNCORROBORATED / Unscored, not a low score.
    Claim(
        claim_id="linear-002",
        company_ref=COMPANY_REF,
        claim_text=(
            "Linear's own product materials describe its interface as designed for speed "
            "and keyboard-driven navigation, distinguishing it from more form-heavy issue "
            "trackers."
        ),
        subject_entity="Linear",
        source_publisher="Linear (product website)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Built for speed, with keyboard-first navigation throughout.",
        assessment_criteria=["differentiation_claim_corroboration"],
        independence_group_id="linear-differentiation-self",
    ),
    # Technical depth: exactly one named, independent fact -- below the
    # SUBSTANTIAL threshold, lands in SOME.
    Claim(
        claim_id="linear-003",
        company_ref=COMPANY_REF,
        claim_text="Linear integrates with GitHub for issue-to-commit linking.",
        subject_entity="Linear",
        source_publisher="an independent integration/reporting source",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Linear supports linking commits and pull requests to issues via a GitHub integration.",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="linear-integration-github",
    ),
    # Defensibility: no claim tagged for this dimension at all in this
    # fixture -- deliberately NONE_DISCLOSED, to test "no evidence" as a
    # distinct, honest outcome from a low score.
    Claim(
        claim_id="linear-stage-001",
        company_ref=COMPANY_REF,
        claim_text="Independent reporting states Linear has raised a Series B round.",
        subject_entity="Linear",
        source_publisher="a business/technology publication",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="...Linear raised a Series B round...",
        assessment_criteria=["stage_signal"],
        independence_group_id="linear-funding-series-b",
        structured_fact={"kind": "funding_round_type", "value": "Series B"},
    ),
]
