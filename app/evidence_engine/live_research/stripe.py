"""
Stripe -- genuine live research gathered 2026-09-27. See
live_research/__init__.py's disclaimer.

Notable finding surfaced by real research (not anticipated in advance):
Stripe's most recent, most independently-reported stage signal is a
"tender offer" / secondary share sale, a term the stage-mapping keyword
list (app.evidence_engine.stage) does not recognize at all. See the
evaluation report for how this was handled and what it implies.
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.models import Claim, SourceType, SupportStatus

COMPANY_REF = "stripe"
COMPANY_DISPLAY_NAMES = ("Stripe",)
RETRIEVED_AT = date(2026, 9, 27)

CLAIMS: list[Claim] = [
    # --- Product Existence & Maturity (also a technical fact) ---
    Claim(
        claim_id="stripe-live-001",
        company_ref=COMPANY_REF,
        claim_text="Stripe's own Shopify case study describes Shopify Balance using Stripe Treasury and Stripe Issuing.",
        subject_entity="Stripe",
        source_url="https://stripe.com/customers/shopify",
        source_publisher="Stripe (product website)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Stripe Treasury for platforms and Stripe Issuing",
        assessment_criteria=["product_existence_maturity", "technical_depth_signal"],
        independence_group_id="stripe-live-shopify-case-study",
    ),
    # --- Differentiation Claim Corroboration (independent) ---
    Claim(
        claim_id="stripe-live-002",
        company_ref=COMPANY_REF,
        claim_text="An independent payments-industry comparison names Stripe's developer experience as the reference standard.",
        subject_entity="Stripe",
        source_url="https://www.fincoro.com/insights/stripe-vs-braintree-vs-adyen",
        source_publisher="Fincoro",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 5, 27),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="the reference standard for payment developer experience",
        assessment_criteria=["differentiation_claim_corroboration"],
        independence_group_id="stripe-live-fincoro-comparison",
    ),
    # --- Technical Depth Signal (2nd distinct named fact) ---
    Claim(
        claim_id="stripe-live-003",
        company_ref=COMPANY_REF,
        claim_text="An independent developer blog names Shopify, DoorDash, Lyft, and Airbnb as running on Stripe Connect.",
        subject_entity="Stripe",
        source_url="https://www.apideck.com/blog/introduction-to-the-stripe-api",
        source_publisher="Apideck",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Shopify, DoorDash, Lyft, and Airbnb run on Connect",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="stripe-live-connect-platforms",
    ),
    # --- Defensibility Signal (independent) ---
    Claim(
        claim_id="stripe-live-004",
        company_ref=COMPANY_REF,
        claim_text="An independent business-strategy analysis describes Stripe's layered product adoption as an infrastructure moat.",
        subject_entity="Stripe",
        source_url="https://fourweekmba.com/stripe-invisible-infrastructure-moat-bia/",
        source_publisher="FourWeekMBA (Gennaro Cuofano)",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 3, 3),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Every new product it launches makes it harder to leave",
        assessment_criteria=["defensibility_signal"],
        independence_group_id="stripe-live-fourweekmba-moat",
    ),
    # --- Stage signal: a genuine methodological finding, not a clean keyword match ---
    Claim(
        claim_id="stripe-live-stage-001",
        company_ref=COMPANY_REF,
        claim_text=(
            "CNBC independently reports Stripe was valued at $159B in a February 2026 tender offer providing "
            "liquidity to employees and shareholders."
        ),
        subject_entity="Stripe",
        source_url="https://www.cnbc.com/2026/02/24/stripe-value-stock-sale-tender-offer.html",
        source_publisher="CNBC",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 2, 24),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="valued at $159 billion after tender offer",
        assessment_criteria=["stage_signal"],
        independence_group_id="stripe-live-tender-offer",
        # Task 12, item 2: previously manually normalized to "late-stage
        # tender offer" because stage.py's keyword list did not recognize
        # the raw term "tender offer" at all (NEW_ENGINE_LIVE_EVALUATION.md
        # §3.3). That gap is now fixed (stage.py's keyword list recognizes
        # "tender offer" directly) -- this claim now carries the actual raw
        # disclosed term, unmodified, exactly as CNBC reported it.
        structured_fact={"kind": "funding_round_type", "value": "tender offer"},
    ),
    # --- Task 14 addition: Team & Leadership evidence, real live
    # research, 2026-09-27 retrieval. Deliberately includes a
    # prestigious-university-only claim carrying NO founder_experience
    # structured_fact, to directly demonstrate in the sanity check that
    # university prestige is not itself evidence for this pillar.
    Claim(
        claim_id="stripe-team-identity-001",
        company_ref=COMPANY_REF,
        claim_text="Public reporting identifies Patrick Collison as co-founder and CEO of Stripe.",
        subject_entity="Patrick Collison",
        source_url="https://en.wikipedia.org/wiki/John_Collison",
        source_publisher="Wikipedia",
        source_type=SourceType.AGGREGATOR_OR_DIRECTORY,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Patrick Collison, co-founder and CEO of Stripe",
        assessment_criteria=["team_identity"],
        independence_group_id="stripe-team-identity-patrick",
        structured_fact={"kind": "team_identity", "person_id": "patrick_collison", "role": "founder"},
    ),
    Claim(
        claim_id="stripe-team-experience-001",
        company_ref=COMPANY_REF,
        claim_text="Independent reporting describes the Collison brothers founding and selling Auctomatic, an e-commerce tools startup, before starting Stripe.",
        subject_entity="Patrick Collison",
        source_url="https://kitrum.com/blog/stripe-founders-the-story-of-collison-brothers/",
        source_publisher="Kitrum",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="designed, launched, and sold the business for $5 million",
        assessment_criteria=["founder_relevant_experience"],
        independence_group_id="stripe-team-auctomatic-experience",
        # Classified ADJACENT, not DIRECT: prior entrepreneurial/software
        # experience is real and checkable, but Auctomatic (eBay seller
        # tools) is not SPECIFICALLY payments/fintech -- the relevance
        # connection to Stripe's own domain is real but not squarely
        # on-point, a deliberately conservative reading per Task 14 item 5
        # ("do not invent relevance when the connection is unclear").
        structured_fact={"kind": "founder_experience", "value": "ADJACENT", "person_id": "patrick_collison", "named_entity": "Auctomatic"},
    ),
    Claim(
        claim_id="stripe-team-track-record-001",
        company_ref=COMPANY_REF,
        claim_text="Independent reporting confirms Auctomatic was acquired by Live Current Media for approximately $5 million in 2008.",
        subject_entity="Patrick Collison",
        source_url="https://kitrum.com/blog/stripe-founders-the-story-of-collison-brothers/",
        source_publisher="Kitrum",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="sold the business for $5 million",
        assessment_criteria=["public_track_record"],
        independence_group_id="stripe-team-auctomatic-exit",
        structured_fact={"kind": "track_record", "value": "PRIOR_EXIT", "person_id": "patrick_collison", "named_entity": "Auctomatic"},
    ),
    # Deliberately NOT founder_relevant_experience evidence -- carries no
    # structured_fact at all, exactly like the offline test case. Included
    # specifically to confirm real, famous-university prestige does not,
    # by itself, move this pillar's score.
    Claim(
        claim_id="stripe-team-university-001",
        company_ref=COMPANY_REF,
        claim_text="Independent reporting notes the Collison brothers attended MIT and Harvard before dropping out to build Stripe.",
        subject_entity="Patrick Collison",
        source_url="https://kitrum.com/blog/stripe-founders-the-story-of-collison-brothers/",
        source_publisher="Kitrum",
        source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="dropped out of their prestigious universities",
        assessment_criteria=["founder_relevant_experience"],
        independence_group_id="stripe-team-university",
        structured_fact=None,
    ),
]
