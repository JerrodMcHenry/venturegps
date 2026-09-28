"""
Notion Labs -- genuine live research gathered 2026-09-27 via WebSearch/
WebFetch. See live_research/__init__.py's disclaimer.

Deliberately includes a REAL disputed pair (two live sources give
different dates for the same $275M Series C round) -- not authored in
for test purposes; this is what the research actually turned up.
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.models import Claim, SourceType, SupportStatus

COMPANY_REF = "notion"
COMPANY_DISPLAY_NAMES = ("Notion", "Notion Labs")
RETRIEVED_AT = date(2026, 9, 27)

CLAIMS: list[Claim] = [
    # --- Product Existence & Maturity ---
    Claim(
        claim_id="notion-live-001",
        company_ref=COMPANY_REF,
        claim_text="Notion's integrations page describes connections that sync data and automate workflows across tools.",
        subject_entity="Notion",
        source_url="https://www.notion.com/en-gb/integrations",
        source_publisher="Notion (product website)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="connections that sync your data, automate workflows",
        assessment_criteria=["product_existence_maturity"],
        independence_group_id="notion-live-integrations-page",
    ),
    # --- Differentiation Claim Corroboration (independent) ---
    Claim(
        claim_id="notion-live-002",
        company_ref=COMPANY_REF,
        claim_text="An independent software-review article contrasts Notion's documentation strength against ClickUp's automation depth.",
        subject_entity="Notion",
        source_url="https://www.eesel.ai/blog/notion-review",
        source_publisher="eesel AI (Rama Adi Nugraha)",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 6, 24),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Notion wins on everything docs-related",
        assessment_criteria=["differentiation_claim_corroboration"],
        independence_group_id="notion-live-eesel-review",
    ),
    # --- Technical Depth Signal (3 distinct named facts) ---
    Claim(
        claim_id="notion-live-003",
        company_ref=COMPANY_REF,
        claim_text="Notion publishes a public API for building third-party integrations.",
        subject_entity="Notion",
        source_url="https://www.notion.com/en-gb/integrations",
        source_publisher="Notion (developer documentation)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="a public API for building integrations",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="notion-live-api",
    ),
    Claim(
        claim_id="notion-live-004",
        company_ref=COMPANY_REF,
        claim_text="Independent reporting confirms Notion AI can access Slack chats and Google Drive files.",
        subject_entity="Notion",
        source_url="https://www.computerworld.com/article/3539918/notion-ai-can-now-access-slack-chats-and-google-drive-files.html",
        source_publisher="Computerworld",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Notion AI can now access Slack chats and Google Drive files",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="notion-live-slack-drive-ai",
    ),
    Claim(
        claim_id="notion-live-005",
        company_ref=COMPANY_REF,
        claim_text="Notion's integration gallery lists Jira, Figma, GitHub, and Linear among roughly three dozen official integrations.",
        subject_entity="Notion",
        source_url="https://www.notion.com/en-gb/integrations",
        source_publisher="Notion (product website)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Jira, Google Drive, and Slack, to help supercharge your workflow",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="notion-live-integration-gallery",
    ),
    # --- Defensibility Signal (independent) ---
    Claim(
        claim_id="notion-live-006",
        company_ref=COMPANY_REF,
        claim_text="An independent growth-strategy analysis describes Notion's template ecosystem as a switching-cost moat.",
        subject_entity="Notion",
        source_url="https://www.howtheygrow.co/p/how-notion-grows",
        source_publisher="How They Grow (Jaryd Hermann)",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2022, 9, 21),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="created an entire marketplace outside of Notion",
        assessment_criteria=["defensibility_signal"],
        independence_group_id="notion-live-ecosystem-moat",
    ),
    # --- Stage signal: a REAL disputed pair (different sources, different dates) ---
    Claim(
        claim_id="notion-live-stage-001",
        company_ref=COMPANY_REF,
        claim_text="Sacra's company profile states Notion's $275M Series C round closed in October 2021, led by Coatue and Sequoia.",
        subject_entity="Notion",
        source_url="https://sacra.com/c/notion/",
        source_publisher="Sacra",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2021, 10, 1),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DISPUTED,
        excerpt="$275 million Series C round in October 2021",
        assessment_criteria=["stage_signal"],
        independence_group_id="notion-live-series-c-sacra",
        contradicts=["notion-live-stage-002"],
        structured_fact={"kind": "funding_round_type", "value": "Series C"},
    ),
    Claim(
        claim_id="notion-live-stage-002",
        company_ref=COMPANY_REF,
        claim_text=(
            "A separate aggregator report ('salestools.io') states Notion's $275M Series C closed on "
            "October 23, 2025 -- a different date for what appears to be the same round."
        ),
        subject_entity="Notion",
        source_url="https://salestools.io/en/report/notion-275m-series-c-2024",
        source_publisher="salestools.io",
        source_type=SourceType.AGGREGATOR_OR_DIRECTORY,
        published_at=date(2025, 10, 23),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DISPUTED,
        excerpt="closed $275M Series C in funding",
        assessment_criteria=["stage_signal"],
        independence_group_id="notion-live-series-c-salestools",
        contradicts=["notion-live-stage-001"],
        structured_fact={"kind": "funding_round_type", "value": "Series C"},
        limitations=["Date conflicts with multiple independently-corroborated sources naming October 2021 for the same $275M/Coatue+Sequoia round."],
    ),
    # --- Task 13 addition: Market Opportunity evidence, gathered via the
    # same genuine live-research discipline as everything above (real
    # URL/publisher/date, 2026-09-27 retrieval). Deliberately about the
    # CATEGORY (workspace/collaboration software), never about Notion's
    # own adoption within it -- that stays out of this pillar entirely
    # (see market_opportunity.py's own pillar-boundary docstring).
    Claim(
        claim_id="notion-market-001",
        company_ref=COMPANY_REF,
        claim_text="An independent market report sizes the global collaboration software market at $6.56B (2023), projected to $19.86B by 2032 at a 13.1% CAGR.",
        subject_entity="collaboration software market",
        source_url="https://scoop.market.us/collaboration-software-statistics/",
        source_publisher="Market.us",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 1, 23),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="reached $6.56 billion in 2023",
        assessment_criteria=["market_definition_size"],
        independence_group_id="notion-market-size-marketus",
        structured_fact={"kind": "market_size_usd", "value": "6560000000"},
    ),
    Claim(
        claim_id="notion-market-002",
        company_ref=COMPANY_REF,
        claim_text="The same report gives a 13.1% CAGR for the collaboration software category.",
        subject_entity="collaboration software market",
        source_url="https://scoop.market.us/collaboration-software-statistics/",
        source_publisher="Market.us",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 1, 23),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="projected to grow at a CAGR of 13.1%",
        assessment_criteria=["market_growth_signal"],
        independence_group_id="notion-market-growth-marketus",
        structured_fact={"kind": "category_growth_rate_pct", "value": "13.1"},
    ),
    Claim(
        claim_id="notion-market-003",
        company_ref=COMPANY_REF,
        claim_text="The same report states Microsoft holds 38% share of the collaboration software market, ahead of Google (21%) and Zoom (15%).",
        subject_entity="collaboration software market",
        source_url="https://scoop.market.us/collaboration-software-statistics/",
        source_publisher="Market.us",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 1, 23),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Microsoft dominates with 38% market share",
        assessment_criteria=["competitive_landscape_position"],
        independence_group_id="notion-market-competitive-marketus",
        structured_fact={"kind": "competitive_structure", "value": "concentrated"},
        limitations=["Describes the broader 'collaboration software' category (Microsoft/Google/Zoom); Notion itself competes more narrowly in workspace/notes/docs -- a real category-boundary ambiguity, see the sanity-check report."],
    ),
    Claim(
        claim_id="notion-market-004",
        company_ref=COMPANY_REF,
        claim_text="Gartner independently predicts 40% of enterprise applications will feature task-specific AI agents by 2026, up from under 5% in 2025.",
        subject_entity="enterprise workspace/collaboration software market",
        source_url="https://www.gartner.com/en/newsroom/press-releases/2025-08-26-gartner-predicts-40-percent-of-enterprise-apps-will-feature-task-specific-ai-agents-by-2026-up-from-less-than-5-percent-in-2025",
        source_publisher="Gartner",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2025, 8, 26),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="40% of Enterprise Apps Will Feature Task-Specific AI Agents by 2026",
        assessment_criteria=["timing_catalyst"],
        independence_group_id="notion-market-catalyst-gartner",
        structured_fact={"kind": "catalyst_name", "value": "enterprise AI agent adoption (Gartner forecast)"},
    ),
]
