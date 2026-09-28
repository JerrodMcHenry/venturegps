"""
Meridian Ops -- a FICTIONAL growth-stage startup, built for Task 18's
full-engine cohort evaluation specifically to isolate two behaviors no
real-evidence fixture in this session happened to exercise:

1. A genuine CROSS-PILLAR duplicate-extraction risk (item 5/6/9): two
   SEPARATE claims (different claim_id, never tagged for each other, never
   marked disputed against each other) each independently report a revenue
   figure for the same company and a similar period -- one tagged only for
   Commercial Traction's Disclosed Scale ($2M, company disclosure), one
   tagged only for Financial & Funding's Revenue Disclosure ($5M,
   independent reporting). This is exactly the failure mode spec Part 3.1
   exists to prevent (two independently-extracted, competing "truths"
   about the same fact) -- deliberately constructed so the per-pillar
   mechanism alone cannot see it (each pillar only ever looks at its own
   claims) and only a genuine cross-pillar audit layer could.
2. A genuine, PROPERLY-tagged customer-adoption contradiction (item 9's
   own explicit example): a company self-disclosure claiming a large
   customer base directly conflicts with independent reporting describing
   weak traction, tagged `disputed`/`contradicts` the ordinary way, to
   confirm the existing fail-closed mechanism still works correctly at
   full-engine scale, not just within one pillar's own test suite.

No real company; any resemblance is coincidental. Never mixed with
live_research/ real data.
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.models import Claim, SourceType, SupportStatus

COMPANY_REF = "meridian-ops-fictional"
COMPANY_DISPLAY_NAMES = ("Meridian Ops",)
RETRIEVED_AT = date(2026, 9, 28)

CLAIMS: list[Claim] = [
    # --- Stage signal: a disclosed Series A round ---
    Claim(
        claim_id="meridian-stage-001",
        company_ref=COMPANY_REF,
        claim_text="An independent funding-database aggregator lists Meridian Ops' Series A round, closed in January 2026.",
        subject_entity="Meridian Ops",
        source_url="https://funding-tracker.example/meridian-ops",
        source_publisher="FundingTracker (aggregator)",
        source_type=SourceType.AGGREGATOR_OR_DIRECTORY,
        published_at=date(2026, 1, 15),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Series A, January 2026",
        assessment_criteria=["stage_signal"],
        independence_group_id="meridian-stage-series-a",
        structured_fact={"kind": "funding_round_type", "value": "Series A"},
    ),
    # --- Funding History: the same real round, its own dimension ---
    Claim(
        claim_id="meridian-fin-round-001",
        company_ref=COMPANY_REF,
        claim_text="The same aggregator lists the Series A round at $8 million, closed January 2026.",
        subject_entity="Meridian Ops",
        source_url="https://funding-tracker.example/meridian-ops",
        source_publisher="FundingTracker (aggregator)",
        source_type=SourceType.AGGREGATOR_OR_DIRECTORY,
        published_at=date(2026, 1, 15),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="$8,000,000 Series A",
        assessment_criteria=["funding_history"],
        independence_group_id="meridian-fin-series-a",
        structured_fact={
            "kind": "funding_round", "financing_type": "equity", "status": "completed",
            "amount": "8000000", "currency": "USD", "round_date": "2026-01-15",
        },
    ),
    # --- Team & Leadership: a minimal, real, named founder fact ---
    Claim(
        claim_id="meridian-team-identity-001",
        company_ref=COMPANY_REF,
        claim_text="Meridian Ops' own about page names Priya Raghunathan as co-founder and CEO.",
        subject_entity="Priya Raghunathan",
        source_url="https://meridian-ops.example/about",
        source_publisher="Meridian Ops (company website)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Priya Raghunathan, Co-Founder & CEO",
        assessment_criteria=["team_identity"],
        independence_group_id="meridian-team-identity-priya",
        structured_fact={"kind": "team_identity", "person_id": "priya_raghunathan", "named_entity": "Priya Raghunathan", "role": "founder"},
    ),
    Claim(
        claim_id="meridian-team-experience-001",
        company_ref=COMPANY_REF,
        claim_text="Independent reporting states Priya Raghunathan previously led operations at a named logistics startup before founding Meridian Ops.",
        subject_entity="Priya Raghunathan",
        source_url="https://foundersweekly.example/meridian-ops-profile",
        source_publisher="Founders Weekly",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="led operations at Cargoflow before founding Meridian Ops",
        assessment_criteria=["founder_relevant_experience"],
        independence_group_id="meridian-team-experience-cargoflow",
        structured_fact={"kind": "founder_experience", "value": "ADJACENT", "person_id": "priya_raghunathan", "named_entity": "Cargoflow"},
    ),
    # --- The deliberate cross-pillar duplicate-extraction scenario -----------
    # Two SEPARATE claims, different claim_id, NEVER cross-tagged, NEVER
    # marked disputed against each other -- each independently plausible
    # in isolation, but describing what is really the same underlying
    # fact (Meridian Ops' 2026 annual revenue) with materially different
    # numbers. See module docstring, item 1.
    Claim(
        claim_id="meridian-traction-revenue-001",
        company_ref=COMPANY_REF,
        claim_text="Meridian Ops' own investor update states 2026 annual revenue of $2 million.",
        subject_entity="Meridian Ops",
        source_url="https://meridian-ops.example/investor-update-2026",
        source_publisher="Meridian Ops (company disclosure)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2026, 8, 1),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="2026 annual revenue of $2 million",
        assessment_criteria=["disclosed_scale"],
        independence_group_id="meridian-revenue-company-disclosure",
        structured_fact={
            "kind": "traction_metric", "metric": "revenue", "amount": "2000000",
            "currency": "USD", "value_type": "actual", "period_date": "2026-06-30",
        },
    ),
    Claim(
        claim_id="meridian-fin-revenue-001",
        company_ref=COMPANY_REF,
        claim_text="Founders Weekly independently reports Meridian Ops' 2026 revenue run-rate at $5 million.",
        subject_entity="Meridian Ops",
        source_url="https://foundersweekly.example/meridian-ops-profile",
        source_publisher="Founders Weekly",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 8, 10),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="revenue run-rate of $5 million",
        # Deliberately tagged ONLY for revenue_disclosure, never also for
        # disclosed_scale -- simulating a real-world researcher who did
        # not notice this describes the same underlying fact as the
        # company-disclosure claim above, and never linked the two via
        # `contradicts` either. This is exactly the scenario a
        # cross-pillar audit layer, not any single pillar, must catch.
        assessment_criteria=["revenue_disclosure"],
        independence_group_id="meridian-revenue-independent-report",
        structured_fact={
            "kind": "traction_metric", "metric": "revenue", "amount": "5000000",
            "currency": "USD", "value_type": "actual", "period_date": "2026-06-30",
        },
    ),
    # --- The properly-tagged customer-adoption contradiction (item 9) --------
    Claim(
        claim_id="meridian-customers-001",
        company_ref=COMPANY_REF,
        claim_text="Meridian Ops' own website claims a customer base in the thousands.",
        subject_entity="Meridian Ops",
        source_url="https://meridian-ops.example/customers",
        source_publisher="Meridian Ops (company website)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2026, 7, 1),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DISPUTED,
        contradicts=["meridian-customers-002"],
        assessment_criteria=["customer_base_breadth"],
        independence_group_id="meridian-customers-self-claim",
        structured_fact={"kind": "customer_band", "value": "LARGE", "named_entity": "thousands of customers, per the company's own website"},
    ),
    Claim(
        claim_id="meridian-customers-002",
        company_ref=COMPANY_REF,
        claim_text="Founders Weekly independently reports Meridian Ops has struggled to gain traction, with fewer than 100 confirmed paying customers as of mid-2026.",
        subject_entity="Meridian Ops",
        source_url="https://foundersweekly.example/meridian-ops-profile",
        source_publisher="Founders Weekly",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 8, 10),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DISPUTED,
        contradicts=["meridian-customers-001"],
        assessment_criteria=["customer_base_breadth"],
        independence_group_id="meridian-customers-independent-report",
        structured_fact={"kind": "customer_band", "value": "SMALL", "named_entity": "fewer than 100 confirmed paying customers, per independent reporting"},
        limitations=["Materially conflicts with the company's own claim of a customer base in the thousands; both entries excluded from scoring pending resolution."],
    ),
    # Market Opportunity, Execution & Momentum, and Capital Efficiency:
    # deliberately NO evidence -- Meridian Ops' own distinctive
    # contribution to the cohort is the two contradiction scenarios
    # above, not exhaustive coverage of every dimension.
]
