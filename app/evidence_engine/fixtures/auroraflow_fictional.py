"""
Offline fixture: "Auroraflow" -- a wholly FICTIONAL company invented for
this vertical slice's own acceptance testing. No real company by this name
is referenced or intended; any resemblance to a real company is
coincidental and not the point of this fixture.

Designed to produce a fully UNSCORED, withheld Product & Technology
pillar (0 of 4 dimensions scorable, both publishability gates fail),
specifically exercising:
  - Unsupported/uncorroborated company self-disclosure not satisfying a
    dimension that requires independent evidence (spec Part 3.1's
    fabricated-claim resistance, calibration acceptance test 4.1).
  - Contradictory sources for the same fact, correctly excluded rather
    than tie-broken to whichever is more flattering (calibration
    acceptance test 4.2).
  - Genuinely insufficient evidence producing an honest, withheld pillar
    result rather than a fabricated or forced number (calibration
    acceptance test 4.4).
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.models import Claim, SourceType, SupportStatus

COMPANY_REF = "auroraflow_fictional"

RETRIEVED_AT = date(2026, 9, 1)

CLAIMS: list[Claim] = [
    # Product existence: only a bare, uncorroborated company assertion --
    # no independently observable artifact (no product-documentation URL,
    # no independent mention, no app-store/directory listing).
    Claim(
        claim_id="auroraflow-001",
        company_ref=COMPANY_REF,
        claim_text="Auroraflow states in its own materials that its platform is live and used by customers today.",
        subject_entity="Auroraflow",
        source_publisher="Auroraflow (self-published materials)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Our platform is live today and in active use by our customers.",
        assessment_criteria=["product_existence_maturity"],
        independence_group_id="auroraflow-product-claim",
    ),
    # Differentiation: only the company's own superlative self-description,
    # no independent comparison.
    Claim(
        claim_id="auroraflow-002",
        company_ref=COMPANY_REF,
        claim_text="Auroraflow's own website claims its technology is materially faster than any competitor.",
        subject_entity="Auroraflow",
        source_publisher="Auroraflow (product website)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="We are faster than any other solution on the market, full stop.",
        assessment_criteria=["differentiation_claim_corroboration"],
        independence_group_id="auroraflow-differentiation-self",
    ),
    # Technical depth: two independent sources directly contradicting each
    # other on the same fact (does Auroraflow hold patents or not) -- both
    # correctly marked disputed and excluded, never tie-broken to whichever
    # is more flattering. Source-type precedence does not break the tie
    # (both are independent_reporting) and recency does not apply (both
    # describe the current state, not two different reporting periods),
    # so this must remain an unresolved conflict per spec Part 2.3.
    Claim(
        claim_id="auroraflow-003",
        company_ref=COMPANY_REF,
        claim_text="A conference-talk description states Auroraflow has filed multiple patents for its core technology.",
        subject_entity="Auroraflow",
        source_publisher="a technology conference program description",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DISPUTED,
        excerpt=None,
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="auroraflow-patents-claim",
        contradicts=["auroraflow-004"],
    ),
    Claim(
        claim_id="auroraflow-004",
        company_ref=COMPANY_REF,
        claim_text=(
            "A separate technology-news article states Auroraflow has not filed any patents "
            "and its core technique is based on an openly published academic method."
        ),
        subject_entity="Auroraflow",
        source_publisher="a technology-news publication",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DISPUTED,
        excerpt=None,
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="auroraflow-patents-dispute",
        contradicts=["auroraflow-003"],
    ),
    # Defensibility: no claim tagged at all -- genuinely no evidence.
]
