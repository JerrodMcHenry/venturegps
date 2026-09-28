"""
Beacon Analytics -- a FICTIONAL pre-seed startup, built for Task 18's
full-engine cohort evaluation specifically to exercise "pre-seed startup,
sparse evidence, most pillars honestly withheld." No real company; any
resemblance is coincidental. Never mixed with live_research/ real data.

Deliberately: exactly enough evidence for TWO dimensions (Product
Existence + Technical Depth) to clear Product & Technology's own two
gates, while every other pillar has at most ONE scored dimension (so the
minimum-distinct-dimension gate withholds it) or zero evidence at all.
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.models import Claim, SourceType, SupportStatus

COMPANY_REF = "beacon-analytics-fictional"
COMPANY_DISPLAY_NAMES = ("Beacon Analytics",)
RETRIEVED_AT = date(2026, 9, 28)

CLAIMS: list[Claim] = [
    # --- Stage signal: a recent founding date, no disclosed round type ---
    Claim(
        claim_id="beacon-stage-001",
        company_ref=COMPANY_REF,
        claim_text="Beacon Analytics' own about page states the company was founded in 2025.",
        subject_entity="Beacon Analytics",
        source_url="https://beacon-analytics.example/about",
        source_publisher="Beacon Analytics (company website)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Founded in 2025",
        assessment_criteria=["stage_signal"],
        independence_group_id="beacon-founding-year",
        structured_fact={"kind": "founding_year", "value": "2025"},
    ),
    # --- Product & Technology: exactly 2 scored dimensions ---
    Claim(
        claim_id="beacon-product-001",
        company_ref=COMPANY_REF,
        claim_text="Beacon Analytics' own website hosts a live product demo.",
        subject_entity="Beacon Analytics",
        source_url="https://beacon-analytics.example/demo",
        source_publisher="Beacon Analytics (company website)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="try the live demo",
        assessment_criteria=["product_existence_maturity"],
        independence_group_id="beacon-demo",
    ),
    Claim(
        claim_id="beacon-product-002",
        company_ref=COMPANY_REF,
        claim_text="Beacon Analytics' documentation names a Slack integration as a supported connection.",
        subject_entity="Beacon Analytics",
        source_url="https://beacon-analytics.example/docs/integrations",
        source_publisher="Beacon Analytics (developer documentation)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Connect Beacon to Slack",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="beacon-slack-integration",
    ),
    # --- Team & Leadership: exactly 1 scored dimension (gate 2 will withhold) ---
    Claim(
        claim_id="beacon-team-identity-001",
        company_ref=COMPANY_REF,
        claim_text="Beacon Analytics' own about page names Jordan Ellery as founder and CEO.",
        subject_entity="Jordan Ellery",
        source_url="https://beacon-analytics.example/about",
        source_publisher="Beacon Analytics (company website)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Jordan Ellery, Founder & CEO",
        assessment_criteria=["team_identity"],
        independence_group_id="beacon-team-identity-jordan",
        structured_fact={"kind": "team_identity", "person_id": "jordan_ellery", "named_entity": "Jordan Ellery", "role": "founder"},
    ),
    Claim(
        claim_id="beacon-team-experience-001",
        company_ref=COMPANY_REF,
        claim_text="Beacon Analytics' own about page states the founder previously worked as a data engineer at a named logistics company.",
        subject_entity="Jordan Ellery",
        source_url="https://beacon-analytics.example/about",
        source_publisher="Beacon Analytics (company website)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="previously a data engineer at RouteWorks Logistics",
        assessment_criteria=["founder_relevant_experience"],
        independence_group_id="beacon-team-experience-routeworks",
        structured_fact={"kind": "founder_experience", "value": "ADJACENT", "person_id": "jordan_ellery", "named_entity": "RouteWorks Logistics"},
    ),
    # --- Financial & Funding: exactly 1 scored dimension (gate 2 will withhold) ---
    Claim(
        claim_id="beacon-fin-round-001",
        company_ref=COMPANY_REF,
        claim_text="Beacon Analytics' own blog announces a $300,000 pre-seed round from angel investors, closed in June 2026.",
        subject_entity="Beacon Analytics",
        source_url="https://beacon-analytics.example/blog/pre-seed",
        source_publisher="Beacon Analytics (company blog)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2026, 6, 1),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="raised $300,000 in a pre-seed round from angel investors",
        assessment_criteria=["funding_history"],
        independence_group_id="beacon-preseed-round",
        structured_fact={
            "kind": "funding_round", "financing_type": "equity", "status": "completed",
            "amount": "300000", "currency": "USD", "round_date": "2026-06-01",
        },
    ),
    # Market Opportunity, Commercial Traction, and Execution & Momentum:
    # deliberately NO evidence at all -- a genuinely sparse pre-seed
    # company, honestly represented rather than padded out.
]
