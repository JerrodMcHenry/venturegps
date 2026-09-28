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
    # --- Task 15 addition: Commercial Traction evidence, real live
    # research, 2026-09-28 retrieval. Notable real finding: Notion's ARR
    # is reported very inconsistently across secondary/aggregator sources
    # found during this pass ($300M/$500M/$600M/$610M/$865M all appear for
    # overlapping late-2025 periods across different low-quality SEO
    # aggregator sites) -- exactly the "conflicting metrics" risk this
    # pillar is designed to resist. Rather than manufacture a growth-
    # trajectory pair from that noise, only the single best-sourced figure
    # (CNBC, on the record, attributed to a named co-founder) is entered
    # as a ledger claim; the weaker aggregator figures are deliberately
    # NOT entered (a research-quality judgment made before the ledger, not
    # a disputed pair for the engine to resolve). Growth Trajectory,
    # Commercial Validation, and Retention/Renewal Signal are left
    # honestly Unscored for Notion in this small pass -- reflecting this
    # pass's own limited research scope, not a claim that no such evidence
    # exists in the wild (the same honest distinction Task 11 §5.4/Task 13
    # §7.3 already drew for their own scope-limited absences).
    Claim(
        claim_id="notion-traction-revenue-2025",
        company_ref=COMPANY_REF,
        claim_text="CNBC reports Notion crossed $500 million in annualized revenue in September 2025, confirmed on the record by co-founder Akshay Kothari.",
        subject_entity="Notion",
        source_url="https://www.cnbc.com/2025/09/18/notion-launches-ai-agent-as-it-crosses-500-million-in-annual-revenue.html",
        source_publisher="CNBC",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2025, 9, 18),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Notion rides AI boom to $500 million in annual revenue",
        assessment_criteria=["disclosed_scale"],
        independence_group_id="notion-traction-cnbc-revenue-2025",
        structured_fact={
            "kind": "traction_metric", "metric": "revenue", "amount": "500000000",
            "currency": "USD", "value_type": "actual", "period_date": "2025-09-18",
        },
    ),
    # Customer Base Breadth: 100M total registered USERS -- deliberately
    # NOT described as "paying customers" or "customer count" (item 13's
    # own explicit "user count vs paying-customer count" distinction).
    # Notion's own blog post does not disclose a paying-customer count at
    # all, so this claim honestly names what it actually establishes.
    Claim(
        claim_id="notion-traction-users-2024",
        company_ref=COMPANY_REF,
        claim_text="Notion's own blog announces the platform passed 100 million total registered users in August 2024.",
        subject_entity="Notion",
        source_url="https://www.notion.com/blog/100-million-of-you",
        source_publisher="Notion (company blog)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2024, 9, 3),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Last month, Notion passed 100M users!",
        assessment_criteria=["customer_base_breadth"],
        independence_group_id="notion-traction-100m-users",
        structured_fact={
            "kind": "customer_band", "value": "LARGE",
            "named_entity": "100 million total registered users (not specifically paying customers)",
        },
    ),
]
