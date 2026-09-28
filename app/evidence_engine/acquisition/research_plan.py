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
        ("{company} market size industry category", ("market_definition_size", "market_growth_signal")),
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
        ("{company} changelog product launch release", ("shipping_velocity",)),
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
