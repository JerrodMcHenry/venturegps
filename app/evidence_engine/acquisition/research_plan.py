"""
Deterministic research planning (Task 20 item 4). A plain Python lookup
table maps each `ResearchTopic` to a fixed set of query TEMPLATES and the
dimensions that topic's evidence is meant to support -- no LLM call
decides what the methodology needs; the methodology's own six pillars
already define that (spec Part 3.3), and this module is a direct,
reviewable restatement of it as a bounded query plan, never an
open-ended "tell me everything about Company X" search.

**Grouped by pillar, not by dimension (item 4's own "do not require every
dimension to generate a search... group related research where
efficient").** One topic can and does surface evidence for several
dimensions at once (e.g. a single company-blog query commonly discovers
both a product launch and a named integration) -- `target_dimensions` on
each `ResearchQuery` documents which dimensions that query is INTENDED
to support, purely for observability; it is not itself an extraction
constraint (a real extraction call may still tag a claim for a dimension
its own topic did not explicitly target, matching the source content
actually found there).
"""

from __future__ import annotations

from app.evidence_engine.acquisition.models import (
    AcquisitionBudget,
    CompanyAnalysisInput,
    ResearchPlan,
    ResearchQuery,
    ResearchTopic,
)

# One entry per ResearchTopic -- (query template, target dimensions).
# Query templates use {company} as the only substitution point,
# deliberately: a bounded, reviewable plan, never an LLM-authored query
# string (item 4's own "do not let an LLM arbitrarily redefine what the
# methodology needs").
_TOPIC_QUERY_TEMPLATES: dict[ResearchTopic, tuple[tuple[str, tuple[str, ...]], ...]] = {
    ResearchTopic.PRODUCT_AND_TECHNOLOGY: (
        ("{company} product features integrations", ("product_existence_maturity", "technical_depth_signal")),
        ("{company} review comparison independent", ("differentiation_claim_corroboration", "defensibility_signal")),
    ),
    ResearchTopic.MARKET_AND_COMPETITION: (
        # Task 23 (LINEAR_001 remediation item 8): replaces the original
        # "{company} market size industry category" wording -- unchanged
        # query COUNT (still 1 of this topic's 2 queries), a text-only
        # refinement. LINEAR_001's actual run used the original wording
        # verbatim and surfaced competitor-comparison pages (ramp.com,
        # seeto.ai) rather than an independent market-sizing report, even
        # though one demonstrably exists and is publicly indexed (the
        # prior manually-curated fixture found one via different search
        # terms). "Report"/"analysis" bias the query toward the CONTENT
        # TYPE an analyst market-sizing report actually is, rather than
        # toward general competitor/category pages -- a wording change
        # that generalizes to any company's own market (no category or
        # domain is named), not a Linear-specific fix. Whether this
        # actually improves recall is explicitly NOT claimed here (item
        # 14's own "do not claim Market will publish" without a live
        # re-run) -- see LINEAR_001_REMEDIATION.md for the same caveat.
        ("{company} total addressable market size report analysis", ("market_definition_size", "market_growth_signal")),
        ("{company} competitors competitive landscape", ("competitive_landscape_position", "timing_catalyst")),
    ),
    ResearchTopic.TEAM_AND_LEADERSHIP: (
        ("{company} founder co-founder background", ("team_identity", "founder_relevant_experience")),
        ("{company} executive team leadership hires", ("leadership_composition", "public_track_record")),
    ),
    ResearchTopic.TRACTION_AND_CUSTOMERS: (
        ("{company} customers revenue users", ("disclosed_scale", "customer_base_breadth")),
        ("{company} growth retention case study", ("growth_trajectory", "retention_renewal_signal", "commercial_validation")),
    ),
    ResearchTopic.EXECUTION_AND_SHIPPING: (
        # Task 23 (LINEAR_001 remediation item 7): replaces the original
        # "{company} changelog product launch release" wording -- same
        # query COUNT (still 1 of this topic's 2), a text-only
        # refinement. LINEAR_001 ran the original wording verbatim and
        # never retrieved the company's own real, public, crawlable
        # changelog, even though the prior manually-curated fixture used
        # exactly that page directly. "Official changelog release notes
        # product updates" names the three standard first-party page
        # types companies actually use for this (changelog / release
        # notes / product updates / newsroom-blog, per item 7's own
        # list) -- a wording change that generalizes to any company
        # (no domain or company-specific path is named), not a
        # Linear-specific fix. A domain-biased search using the
        # company's own already-known website (still generic, not
        # Linear-specific) would likely help further but is a deeper
        # architecture change (passing `website_url` into `SearchProvider.
        # search()`) this task did not make -- named as follow-up work in
        # LINEAR_001_REMEDIATION.md, not attempted here. Whether this
        # wording change actually improves recall is explicitly NOT
        # claimed without a live re-run (item 14).
        ("{company} official changelog release notes product updates", ("shipping_velocity",)),
        ("{company} partnership sales go-to-market", ("gtm_motion_evidence", "strategic_consistency")),
    ),
    ResearchTopic.FUNDING_AND_FINANCIALS: (
        ("{company} funding round investors raised", ("funding_history", "stage_signal")),
        ("{company} valuation financials margin", ("capital_efficiency",)),
        # Deliberately NO separate "{company} revenue" query here -- spec
        # Part 3.1's own revenue-reuse rule (Task 17) means Financial &
        # Funding Signals' Revenue Disclosure never independently
        # re-researches revenue; it reuses whatever Traction & Customers'
        # own query above already discovered (item 14, enforced in
        # `extraction.py::tag_cross_pillar_reuse`).
    ),
}


def build_research_plan(
    input: CompanyAnalysisInput, budget: AcquisitionBudget | None = None,
) -> ResearchPlan:
    """Deterministic: identical input + budget always produces an
    identical plan. `budget.max_queries_per_topic`/`max_topics` bound the
    plan size explicitly (item 5) -- this function never emits more
    queries than the budget allows, truncating topics/queries in the
    same fixed order every time (never randomly sampled)."""
    budget = budget or AcquisitionBudget()
    topics = list(ResearchTopic)[: budget.max_topics]

    queries: list[ResearchQuery] = []
    for topic in topics:
        templates = _TOPIC_QUERY_TEMPLATES.get(topic, ())[: budget.max_queries_per_topic]
        for template, target_dimensions in templates:
            queries.append(ResearchQuery(
                topic=topic,
                query_text=template.format(company=input.company_name),
                target_dimensions=target_dimensions,
            ))

    return ResearchPlan(company_name=input.company_name, queries=tuple(queries))
