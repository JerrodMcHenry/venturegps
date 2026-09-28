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
    # --- Task 15 addition: Commercial Traction evidence, real live
    # research, 2026-09-28 retrieval. Notable real finding: Stripe's own
    # 2025 annual letter/press discloses total payment volume (TPV) --
    # $1.9T in 2025 -- prominently, but its actual REVENUE ($6.8B) is
    # available only via third-party reporting (The Information, via
    # Axios and SaaStr), never as a first-party figure. This is the exact
    # real-world "GMV vs revenue confusion" risk item 6 warns against:
    # TPV is ~280x larger than revenue for the same company in the same
    # year -- treating one as a stand-in for the other would be a severe,
    # concrete error. Retention/renewal and a named customer *count* are
    # both genuinely undisclosed -- Stripe is private and does not publish
    # either -- so both remain honestly Unscored (see the Commercial
    # Traction report's sanity-check section).
    Claim(
        claim_id="stripe-traction-revenue-2024",
        company_ref=COMPANY_REF,
        claim_text="Axios, citing The Information, reports Stripe's 2024 net revenue grew 28% to $5.1 billion, with $2.2 billion in free cash flow.",
        subject_entity="Stripe",
        source_url="https://www.axios.com/pro/fintech-deals/newsletters/2025/03/27/fintech-stripe-s-revenue-jump",
        source_publisher="Axios (citing The Information)",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2025, 3, 27),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Stripe grew revenue 28%, to $5.1 billion, last year, and doubled free-cash flow to $2.2 billion",
        assessment_criteria=["disclosed_scale", "growth_trajectory"],
        independence_group_id="stripe-traction-revenue-2024",
        structured_fact={
            "kind": "traction_metric", "metric": "revenue", "amount": "5100000000",
            "currency": "USD", "value_type": "actual", "period_date": "2024-12-31",
        },
    ),
    Claim(
        claim_id="stripe-traction-revenue-2025",
        company_ref=COMPANY_REF,
        claim_text="The Information, via SaaStr's coverage of Stripe's 2025 annual letter, reports 2025 revenue of $6.8 billion, up 33% year-over-year.",
        subject_entity="Stripe",
        source_url="https://www.saastr.com/5-interesting-learnings-from-stripe-at-6-8-billion-in-revenue-33-growth-47-free-cash-flow-margins-and-a-53b-bid-for-paypal/",
        source_publisher="SaaStr (citing The Information)",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 7, 22),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Stripe's 2025 revenue hit $6.8 billion, up roughly a third year-over-year, its fastest growth since 2021",
        assessment_criteria=["disclosed_scale", "growth_trajectory"],
        independence_group_id="stripe-traction-revenue-2025",
        structured_fact={
            "kind": "traction_metric", "metric": "revenue", "amount": "6800000000",
            "currency": "USD", "value_type": "actual", "period_date": "2025-12-31",
        },
    ),
    # Total payment volume (TPV) -- deliberately tagged metric="gmv" (a
    # pass-through transaction-value figure, not Stripe's own take-rate
    # revenue) and NOT tagged assessment_criteria including
    # "disclosed_scale" together with the revenue claims above in a way
    # that would let TRACTION_METRIC_PREFERENCE_ORDER's own revenue-first
    # ordering be the only thing preventing confusion -- it is included
    # specifically so the sanity check can show the engine choosing
    # revenue over TPV/GMV on the merits, not by omission.
    Claim(
        claim_id="stripe-traction-tpv-2025",
        company_ref=COMPANY_REF,
        claim_text="Stripe's own 2025 annual letter reports total payment volume of $1.9 trillion in 2025, up 34% year-over-year from $1.4 trillion in 2024.",
        subject_entity="Stripe",
        source_url="https://stripe.com/newsroom/news/stripe-2025-update",
        source_publisher="Stripe (company disclosure)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2026, 7, 21),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="total payment volume of $1.9T in 2025, up 34% year-over-year from $1.4T in 2024",
        assessment_criteria=["disclosed_scale"],
        independence_group_id="stripe-traction-tpv-2025",
        structured_fact={
            "kind": "traction_metric", "metric": "gmv", "amount": "1900000000000",
            "currency": "USD", "value_type": "actual", "period_date": "2025-12-31",
        },
    ),
    # Named enterprise commercial relationships -- Commercial Validation,
    # never Customer Base Breadth: a handful of named logos in one article
    # is not the same claim as a disclosed customer COUNT/band (item 5's
    # "existence vs. magnitude" -- Stripe discloses no overall customer
    # count, so Customer Base Breadth stays honestly Unscored below). Each
    # named company is its own distinct, separately-checkable fact (spec
    # Part 2.1's own independence_group_id semantics: a shared group id is
    # for restatements of the SAME event, not for multiple different facts
    # co-mentioned in one article) -- NOT collapsed into one claim, so the
    # real count of named relationships is what the dimension actually
    # counts, not an artificially deflated "one source, one fact."
    Claim(
        claim_id="stripe-traction-validation-openai",
        company_ref=COMPANY_REF,
        claim_text="Among the named AI labs billing on Stripe, The Information specifically calls out OpenAI's subscription products.",
        subject_entity="Stripe",
        source_url="https://www.saastr.com/5-interesting-learnings-from-stripe-at-6-8-billion-in-revenue-33-growth-47-free-cash-flow-margins-and-a-53b-bid-for-paypal/",
        source_publisher="SaaStr (citing The Information)",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 7, 22),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="OpenAI, Anthropic, Confluent, and NVIDIA (for billing services)",
        assessment_criteria=["commercial_validation"],
        independence_group_id="stripe-traction-openai-billing",
        structured_fact={"kind": "commercial_commitment", "named_entity": "OpenAI (Stripe Billing)"},
    ),
    Claim(
        claim_id="stripe-traction-validation-anthropic",
        company_ref=COMPANY_REF,
        claim_text="The Information reports Anthropic uses Stripe's billing infrastructure for its own subscription products.",
        subject_entity="Stripe",
        source_url="https://www.saastr.com/5-interesting-learnings-from-stripe-at-6-8-billion-in-revenue-33-growth-47-free-cash-flow-margins-and-a-53b-bid-for-paypal/",
        source_publisher="SaaStr (citing The Information)",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 7, 22),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="OpenAI, Anthropic, Confluent, and NVIDIA (for billing services)",
        assessment_criteria=["commercial_validation"],
        independence_group_id="stripe-traction-anthropic-billing",
        structured_fact={"kind": "commercial_commitment", "named_entity": "Anthropic (Stripe Billing)"},
    ),
    Claim(
        claim_id="stripe-traction-validation-orb",
        company_ref=COMPANY_REF,
        claim_text="The Information reports Vercel, Glean, Replit, and Supabase run usage-based billing on Stripe's Orb product.",
        subject_entity="Stripe",
        source_url="https://www.saastr.com/5-interesting-learnings-from-stripe-at-6-8-billion-in-revenue-33-growth-47-free-cash-flow-margins-and-a-53b-bid-for-paypal/",
        source_publisher="SaaStr (citing The Information)",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 7, 22),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Vercel, Glean, Replit, and Supabase (for Orb billing)",
        assessment_criteria=["commercial_validation"],
        independence_group_id="stripe-traction-orb-customers",
        structured_fact={"kind": "commercial_commitment", "named_entity": "Vercel, Glean, Replit, and Supabase (Orb billing)"},
    ),
    # Retention/renewal and an overall customer COUNT/band: deliberately
    # NOT added. Real research found neither disclosed anywhere for
    # Stripe -- both remain honestly Unscored, the expected, structurally
    # correct outcome for a private company's genuinely undisclosed
    # metrics (this pillar's own central rule).

    # --- Task 16 addition: Execution & Momentum evidence, real live
    # research, 2026-09-28 retrieval. Stripe's own "Everything we
    # announced at Sessions 2026" post (2026-04-29) explicitly and
    # cleanly distinguishes generally-available features from previewed/
    # roadmap ones -- a genuine real-world instance of exactly the
    # announced/launched distinction this pillar's own governing
    # principle requires. Several previewed (not GA) features from the
    # same event were found and deliberately NOT entered as
    # "launched" -- see the sanity-check report for the specific
    # previewed-but-excluded list.
    Claim(
        claim_id="stripe-exec-release-workflows",
        company_ref=COMPANY_REF,
        claim_text="Among the Sessions 2026 announcements, Stripe Workflows reached general availability, per Stripe's own recap.",
        subject_entity="Stripe",
        source_url="https://stripe.com/blog/everything-we-announced-at-sessions-2026",
        source_publisher="Stripe (company blog)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2026, 4, 29),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Stripe Workflows is now generally available",
        assessment_criteria=["shipping_velocity"],
        independence_group_id="stripe-exec-workflows-ga",
        structured_fact={"kind": "product_release", "status": "launched", "named_entity": "Stripe Workflows", "event_date": "2026-04-29"},
    ),
    Claim(
        claim_id="stripe-exec-release-managed-payments",
        company_ref=COMPANY_REF,
        claim_text="Stripe's own Sessions 2026 recap states Managed Payments is now available to all digital businesses.",
        subject_entity="Stripe",
        source_url="https://stripe.com/blog/everything-we-announced-at-sessions-2026",
        source_publisher="Stripe (company blog)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2026, 4, 29),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="All digital businesses can now use Managed Payments",
        assessment_criteria=["shipping_velocity"],
        independence_group_id="stripe-exec-managed-payments-ga",
        structured_fact={"kind": "product_release", "status": "launched", "named_entity": "Managed Payments", "event_date": "2026-04-29"},
    ),
    Claim(
        claim_id="stripe-exec-release-stablecoin-cards",
        company_ref=COMPANY_REF,
        claim_text="Stripe's own Sessions 2026 recap states stablecoin-backed cards can now be enabled in 30 countries.",
        subject_entity="Stripe",
        source_url="https://stripe.com/blog/everything-we-announced-at-sessions-2026",
        source_publisher="Stripe (company blog)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2026, 4, 29),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="You can now enable consumer or commercial stablecoin-backed cards in 30 countries",
        assessment_criteria=["shipping_velocity"],
        independence_group_id="stripe-exec-stablecoin-cards-ga",
        structured_fact={"kind": "product_release", "status": "launched", "named_entity": "Stablecoin-backed cards", "event_date": "2026-04-29"},
    ),
    # Deliberately NOT entered as launched (real, previewed-only per the
    # same source): Checkout Studio, Stripe Database, Stripe Console,
    # custom objects, Issuing for agents, custom Radar models -- all
    # explicitly "previewed"/"announced" with no GA date, per the same
    # article. Included here as a claim specifically to prove the
    # announced/preview distinction is preserved on REAL data.
    Claim(
        claim_id="stripe-exec-release-checkout-studio-preview",
        company_ref=COMPANY_REF,
        claim_text="Stripe's own Sessions 2026 recap states Checkout studio was previewed, not generally available.",
        subject_entity="Stripe",
        source_url="https://stripe.com/blog/everything-we-announced-at-sessions-2026",
        source_publisher="Stripe (company blog)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2026, 4, 29),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="We previewed Checkout studio, a new way for you to configure, analyze, and optimize",
        assessment_criteria=["shipping_velocity"],
        independence_group_id="stripe-exec-checkout-studio-preview",
        structured_fact={"kind": "product_release", "status": "announced", "named_entity": "Checkout Studio", "event_date": "2026-04-29"},
    ),
    # Go-to-Market Motion Evidence: a real, named distribution partnership
    # (Google/Gemini surfacing Stripe-powered agentic checkout to
    # consumers) -- a GTM channel fact, distinct from Commercial
    # Validation's own OpenAI/Anthropic paying-customer relationships
    # above (this is about REACHING customers, not about who already pays).
    Claim(
        claim_id="stripe-exec-gtm-google-partnership",
        company_ref=COMPANY_REF,
        claim_text="Stripe's own Sessions 2026 recap announces a partnership with Google enabling businesses to sell to consumers inside AI Mode and the Gemini app.",
        subject_entity="Stripe",
        source_url="https://www.investing.com/news/analyst-ratings/stripe-unveils-288-products-at-sessions-2026-focused-on-ai-commerce-93CH-4656455",
        source_publisher="Investing.com",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 4, 29),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="partnerships with Google that will allow businesses to sell to consumers inside AI Mode and the Gemini app",
        assessment_criteria=["gtm_motion_evidence"],
        independence_group_id="stripe-exec-google-gtm-partnership",
        structured_fact={"kind": "gtm_evidence", "gtm_type": "partnership", "named_entity": "Google (AI Mode / Gemini distribution)"},
    ),
    # Strategic Consistency: two real, dated public statements of
    # Stripe's own mission, ~5 years apart. Judgment call, documented
    # honestly: both frame Stripe as economic/growth infrastructure for
    # online commerce, applied to AI as the newest frontier in the more
    # recent statement -- read as a consistent evolution of the same
    # stated mission, not a contradiction. This research pass did not
    # find any genuine, real conflicting mission/strategy statement for
    # Stripe.
    Claim(
        claim_id="stripe-exec-strategy-2021",
        company_ref=COMPANY_REF,
        claim_text="Stripe co-founder and CEO Patrick Collison states publicly that Stripe's mission and strategy is to 'increase the GDP of the internet.'",
        subject_entity="Stripe",
        source_url="https://x.com/patrickc/status/1371506254359752708",
        source_publisher="Patrick Collison (via X/Twitter)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2021, 3, 15),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="\"Increase the GDP of the internet\" is our mission statement but also, importantly, our *strategy*",
        assessment_criteria=["strategic_consistency"],
        independence_group_id="stripe-exec-strategy-2021-gdp",
        structured_fact={"kind": "strategic_statement", "topic": "mission", "named_entity": "increase the GDP of the internet"},
    ),
    Claim(
        claim_id="stripe-exec-strategy-2026",
        company_ref=COMPANY_REF,
        claim_text="Stripe's own newsroom describes Sessions 2026 as building out the economic infrastructure for AI commerce.",
        subject_entity="Stripe",
        source_url="https://stripe.com/newsroom/news/sessions-2026",
        source_publisher="Stripe (company newsroom)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2026, 4, 29),
        retrieved_at=date(2026, 9, 28),
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Stripe builds out the economic infrastructure for AI with 288 launches",
        assessment_criteria=["strategic_consistency"],
        independence_group_id="stripe-exec-strategy-2026-ai-infra",
        structured_fact={"kind": "strategic_statement", "topic": "mission", "named_entity": "economic infrastructure for AI commerce"},
    ),
]
