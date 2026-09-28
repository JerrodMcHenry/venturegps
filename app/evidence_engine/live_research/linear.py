"""
Linear -- genuine live research gathered 2026-09-27. See
live_research/__init__.py's disclaimer.

Includes a genuine near-duplicate pair for the stage signal (Linear's own
blog announcement vs. TechCrunch's independent report of the same Series
C) -- run through provenance verification for real rather than assumed;
see the evaluation report for what verify_independence() actually
concluded.
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.models import Claim, SourceType, SupportStatus

COMPANY_REF = "linear"
COMPANY_DISPLAY_NAMES = ("Linear",)
RETRIEVED_AT = date(2026, 9, 27)

CLAIMS: list[Claim] = [
    # --- Product Existence & Maturity (also serves as a technical fact) ---
    Claim(
        claim_id="linear-live-001",
        company_ref=COMPANY_REF,
        claim_text="Linear's own GitHub integration page describes linking issues to pull requests and automating status updates.",
        subject_entity="Linear",
        source_url="https://linear.app/integrations/github",
        source_publisher="Linear (product website)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="automate PR workflows, review code in Linear",
        assessment_criteria=["product_existence_maturity", "technical_depth_signal"],
        independence_group_id="linear-live-github-integration",
    ),
    # --- Differentiation Claim Corroboration (independent) ---
    Claim(
        claim_id="linear-live-002",
        company_ref=COMPANY_REF,
        claim_text="An independent comparison article quotes a user describing Linear's interface as superior to Jira's.",
        subject_entity="Linear",
        source_url="https://www.nuclino.com/solutions/linear-vs-jira",
        source_publisher="Nuclino",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 1, 14),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="I find the UI of Linear to be superior",
        assessment_criteria=["differentiation_claim_corroboration"],
        independence_group_id="linear-live-nuclino-review",
    ),
    # --- Technical Depth Signal (2 more distinct named facts) ---
    Claim(
        claim_id="linear-live-003",
        company_ref=COMPANY_REF,
        claim_text="Linear's Figma integration links design frames and pages directly to Linear issues.",
        subject_entity="Linear",
        source_url="https://linear.app/integrations/figma",
        source_publisher="Linear (product website)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="link individual frames, sections, and pages",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="linear-live-figma-integration",
    ),
    Claim(
        claim_id="linear-live-004",
        company_ref=COMPANY_REF,
        claim_text="Linear's Slack integration lets users create and view issues directly from Slack.",
        subject_entity="Linear",
        source_url="https://linear.app/docs/slack",
        source_publisher="Linear (documentation)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="create, update, and view new Linear issues",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="linear-live-slack-integration",
    ),
    # --- Defensibility Signal (independent) ---
    Claim(
        claim_id="linear-live-005",
        company_ref=COMPANY_REF,
        claim_text="An independent analysis of tool-switching friction cites Linear as an example of workflow/integration lock-in.",
        subject_entity="Linear",
        source_url="https://dev.to/theobrenner/migration-friction-is-the-real-cost-of-switching-tools-4cga",
        source_publisher="DEV Community (Theo Brenner)",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 7, 24),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Your team learned the tool's mental model",
        assessment_criteria=["defensibility_signal"],
        independence_group_id="linear-live-lockin-analysis",
    ),
    # --- Stage signal: company disclosure + independent reporting of the same round ---
    Claim(
        claim_id="linear-live-stage-001",
        company_ref=COMPANY_REF,
        claim_text="Linear's own blog post announces its Series C round.",
        subject_entity="Linear",
        source_url="https://linear.app/now/building-our-way",
        source_publisher="Linear (company blog)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Announcing our Series C",
        assessment_criteria=["stage_signal"],
        independence_group_id="linear-live-seriesc-own-post",
        structured_fact={"kind": "funding_round_type", "value": "Series C"},
    ),
    Claim(
        claim_id="linear-live-stage-002",
        company_ref=COMPANY_REF,
        claim_text="TechCrunch independently reports Linear's $82M Series C at a $1.25B valuation, led by Accel.",
        subject_entity="Linear",
        source_url="https://techcrunch.com/2025/06/10/atlassian-rival-linear-raises-82m-at-1-25b-valuation/",
        source_publisher="TechCrunch",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2025, 6, 10),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="$82 million in Series C funding led by Accel",
        assessment_criteria=["stage_signal"],
        independence_group_id="linear-live-seriesc-techcrunch",
        structured_fact={"kind": "funding_round_type", "value": "Series C"},
    ),
    # --- Task 13 addition: Market Opportunity evidence, real live
    # research, 2026-09-27 retrieval. About the issue-tracking-software
    # CATEGORY, never Linear's own adoption within it. Deliberately no
    # timing_catalyst claim was found in this evaluation's research
    # budget for Linear -- left genuinely absent, not invented.
    Claim(
        claim_id="linear-market-001",
        company_ref=COMPANY_REF,
        claim_text="An independent market report sizes the global issue tracking software market at $1.78B (2025), projected to $5.12B by 2035 at an 11.2% CAGR.",
        subject_entity="issue tracking software market",
        source_url="https://www.nextmsc.com/report/issue-tracking-software-market-ic4963",
        source_publisher="Next Move Strategy Consulting",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 7, 6),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="valued at USD 1.78 billion in 2025",
        assessment_criteria=["market_definition_size"],
        independence_group_id="linear-market-size-nextmsc",
        structured_fact={"kind": "market_size_usd", "value": "1780000000"},
    ),
    Claim(
        claim_id="linear-market-002",
        company_ref=COMPANY_REF,
        claim_text="The same report gives an 11.2% CAGR (2026-2035) for the issue tracking software category.",
        subject_entity="issue tracking software market",
        source_url="https://www.nextmsc.com/report/issue-tracking-software-market-ic4963",
        source_publisher="Next Move Strategy Consulting",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 7, 6),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="a CAGR of 11.2% from 2026 to 2035",
        assessment_criteria=["market_growth_signal"],
        independence_group_id="linear-market-growth-nextmsc",
        structured_fact={"kind": "category_growth_rate_pct", "value": "11.2"},
    ),
    Claim(
        claim_id="linear-market-003",
        company_ref=COMPANY_REF,
        claim_text="The same report names ten market participants (including Atlassian's Jira, ServiceNow, Microsoft, GitLab, Zendesk, Linear itself, and others) and states Jira 'dominates enterprise adoption.'",
        subject_entity="issue tracking software market",
        source_url="https://www.nextmsc.com/report/issue-tracking-software-market-ic4963",
        source_publisher="Next Move Strategy Consulting",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 7, 6),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Jira dominates enterprise adoption",
        assessment_criteria=["competitive_landscape_position"],
        independence_group_id="linear-market-competitive-nextmsc",
        structured_fact={"kind": "competitive_structure", "value": "concentrated"},
        limitations=["Ten named competitors exist (a fragmentation signal by count), but the source explicitly frames one (Jira) as dominant -- a real ambiguity the FRAGMENTED/CONCENTRATED binary does not cleanly resolve; classified CONCENTRATED here on the source's own explicit 'dominates' framing. See the sanity-check report."],
    ),
]
