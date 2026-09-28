"""
Offline fixture: "DupliCo" -- a wholly FICTIONAL, Series A-stage company
invented for this calibration pass. No real company by this name is
referenced or intended.

Designed to exercise duplicated-evidence robustness directly: Technical
Depth Signal has FIVE raw claims, but all five describe the SAME single
underlying integration, restated by five different publishers (a common
real-world pattern -- one press release or blog post gets syndicated/
restated widely). All five share one `independence_group_id`. The
expected, correct outcome is SOME (1 distinct fact), never SUBSTANTIAL --
proving neither the ledger's deduplication nor the classifier's own
distinct-fact counting is fooled by raw claim count.
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.models import Claim, SourceType, SupportStatus

COMPANY_REF = "duplico_fictional"

RETRIEVED_AT = date(2026, 9, 1)

_SHARED_GROUP = "duplico-single-integration-restated-widely"

CLAIMS: list[Claim] = [
    Claim(
        claim_id="duplico-stage-001",
        company_ref=COMPANY_REF,
        claim_text="Independent reporting states DupliCo has raised a Series A round.",
        subject_entity="DupliCo",
        source_publisher="a business/technology publication",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="...DupliCo raised a Series A round...",
        assessment_criteria=["stage_signal"],
        independence_group_id="duplico-funding-series-a",
        structured_fact={"kind": "funding_round_type", "value": "Series A"},
    ),
    Claim(
        claim_id="duplico-001",
        company_ref=COMPANY_REF,
        claim_text="DupliCo has a public web application.",
        subject_entity="DupliCo",
        source_publisher="DupliCo (product website)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="DupliCo's product is available as a web application.",
        assessment_criteria=["product_existence_maturity"],
        independence_group_id="duplico-product-existence",
    ),
] + [
    Claim(
        claim_id=f"duplico-techdepth-{i:03d}",
        company_ref=COMPANY_REF,
        claim_text="DupliCo integrates with one specific named workflow tool.",
        subject_entity="DupliCo",
        source_publisher=publisher,
        source_type=source_type,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="DupliCo now integrates with [the named workflow tool].",
        assessment_criteria=["technical_depth_signal"],
        # Deliberately the SAME group for all five -- one real underlying
        # fact (one integration announcement), restated five times.
        independence_group_id=_SHARED_GROUP,
    )
    for i, (publisher, source_type) in enumerate(
        [
            ("an independent technology-news outlet (restatement 1)", SourceType.INDEPENDENT_REPORTING),
            ("an independent technology-news outlet (restatement 2)", SourceType.INDEPENDENT_REPORTING),
            ("a funding/integration aggregator directory (restatement 3)", SourceType.AGGREGATOR_OR_DIRECTORY),
            ("a funding/integration aggregator directory (restatement 4)", SourceType.AGGREGATOR_OR_DIRECTORY),
            ("a funding/integration aggregator directory (restatement 5)", SourceType.AGGREGATOR_OR_DIRECTORY),
        ],
        start=1,
    )
]
# Differentiation and Defensibility: no claims tagged -- deliberately, to
# keep this fixture's focus on the duplicated-evidence question alone.
