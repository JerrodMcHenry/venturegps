"""
Bullet (YC S26) -- genuine live research gathered 2026-09-27 ("pre-seed"
company for Task 11's roster: a real Y Combinator Summer 2026 batch
company, launched publicly on Hacker News 2026-08-18). See
live_research/__init__.py's disclaimer.

Includes a REAL disputed claim found in the wild: the founders' own
benchmark claim, directly challenged by an independent Hacker News
commenter in the same public thread -- not authored in for test purposes.
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.models import Claim, SourceType, SupportStatus

COMPANY_REF = "bullet"
COMPANY_DISPLAY_NAMES = ("Bullet",)
RETRIEVED_AT = date(2026, 9, 27)

_LAUNCH_URL = "https://news.ycombinator.com/item?id=49283063"

CLAIMS: list[Claim] = [
    # --- Product Existence & Maturity (independent user account, not the founders' own claim) ---
    Claim(
        claim_id="bullet-live-001",
        company_ref=COMPANY_REF,
        claim_text="An independent Hacker News commenter reports switching to using Bullet for real projects.",
        subject_entity="Bullet",
        source_url=_LAUNCH_URL,
        source_publisher="Hacker News (independent commenter, Launch HN thread)",
        # Task 12, item 3: previously INDEPENDENT_REPORTING with a
        # `limitations` note explaining this was really a weaker, anonymous
        # kind of independence. Now its own SourceType, with its own
        # (lower) reliability weight -- the note is no longer needed
        # because the distinction is now structural, not just annotated.
        source_type=SourceType.COMMUNITY_COMMENTARY,
        published_at=date(2026, 8, 18),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="switched over to using primarily Bullet for my projects",
        assessment_criteria=["product_existence_maturity"],
        independence_group_id="bullet-live-hn-user-account",
    ),
    # --- Differentiation: a REAL disputed pair from the same public thread ---
    Claim(
        claim_id="bullet-live-002",
        company_ref=COMPANY_REF,
        claim_text="The founders' own launch post claims a 95.8% SWE-bench Verified resolve rate in one attempt.",
        subject_entity="Bullet",
        source_url=_LAUNCH_URL,
        source_publisher="Bullet (founders' own Launch HN post)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2026, 8, 18),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DISPUTED,
        excerpt="resolved 479/500 (95.8%) in one attempt",
        assessment_criteria=["differentiation_claim_corroboration"],
        independence_group_id="bullet-live-founders-benchmark",
        contradicts=["bullet-live-003"],
    ),
    Claim(
        claim_id="bullet-live-003",
        company_ref=COMPANY_REF,
        claim_text="An independent commenter in the same thread directly disputes the benchmark claim's meaningfulness.",
        subject_entity="Bullet",
        source_url=_LAUNCH_URL,
        source_publisher="Hacker News (independent commenter, Launch HN thread)",
        source_type=SourceType.COMMUNITY_COMMENTARY,
        published_at=date(2026, 8, 18),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DISPUTED,
        excerpt="An intellectually honest way to tell if this thing really works",
        assessment_criteria=["differentiation_claim_corroboration"],
        independence_group_id="bullet-live-commenter-rebuttal",
        contradicts=["bullet-live-002"],
        limitations=["Disputes the founders' benchmark claim's validity/comparability, not a factual date/amount conflict -- a qualitative dispute rather than a data conflict (see evaluation report)."],
    ),
    # --- Technical Depth Signal (company disclosure only -- 1 fact, below SUBSTANTIAL regardless) ---
    Claim(
        claim_id="bullet-live-004",
        company_ref=COMPANY_REF,
        claim_text="The founders' launch post names supported model-provider integrations.",
        subject_entity="Bullet",
        source_url=_LAUNCH_URL,
        source_publisher="Bullet (founders' own Launch HN post)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2026, 8, 18),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="OpenAI, Anthropic Claude, and Grok via subscriptions",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="bullet-live-provider-integrations",
    ),
    # --- Stage signal ---
    Claim(
        claim_id="bullet-live-stage-001",
        company_ref=COMPANY_REF,
        claim_text="Bullet's own launch post identifies it as a Y Combinator Summer 2026 batch company.",
        subject_entity="Bullet",
        source_url=_LAUNCH_URL,
        source_publisher="Bullet (founders' own Launch HN post)",
        source_type=SourceType.COMPANY_DISCLOSURE,
        published_at=date(2026, 8, 18),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Bullet (YC S26)",
        assessment_criteria=["stage_signal"],
        independence_group_id="bullet-live-yc-batch",
        # Task 12, item 2: previously manually normalized to "Pre-Seed (YC
        # S26 standard deal)" because stage.py's keyword list did not
        # recognize "YC S26" at all (NEW_ENGINE_LIVE_EVALUATION.md §3.3).
        # That gap is now fixed (stage.py recognizes "yc s"/"yc w"/"y
        # combinator" directly) -- this claim now carries the actual raw
        # disclosed term, unmodified, exactly as the launch post states it.
        structured_fact={"kind": "funding_round_type", "value": "YC S26"},
    ),
    # No defensibility_signal-tagged claim: none was found during real
    # research for a company 40 days old at retrieval time.
]
