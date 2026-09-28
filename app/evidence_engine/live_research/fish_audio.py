"""
Fish Audio -- genuine live research gathered 2026-09-27 ("early-stage"
company for Task 11's roster: a real, seed-stage, press-covered startup).
See live_research/__init__.py's disclaimer.

No defensibility-signal evidence was found during real research for this
company -- left genuinely absent (Unscored, no claim fabricated to fill
the gap) rather than forced.
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.models import Claim, SourceType, SupportStatus

COMPANY_REF = "fish_audio"
COMPANY_DISPLAY_NAMES = ("Fish Audio",)
RETRIEVED_AT = date(2026, 9, 27)

CLAIMS: list[Claim] = [
    # --- Product Existence & Maturity (also a technical fact) ---
    Claim(
        claim_id="fishaudio-live-001",
        company_ref=COMPANY_REF,
        claim_text="Fish Audio's developer page describes a live API for speech, voice cloning, and transcription.",
        subject_entity="Fish Audio",
        source_url="https://fish.audio/developers/",
        source_publisher="Fish Audio (product website)",
        source_type=SourceType.PRODUCT_DOCUMENTATION,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="Ship lifelike speech, voice cloning, and transcription with one API",
        assessment_criteria=["product_existence_maturity", "technical_depth_signal"],
        independence_group_id="fishaudio-live-developer-api",
    ),
    # --- Technical Depth Signal (2nd distinct, independently-observable fact) ---
    Claim(
        claim_id="fishaudio-live-002",
        company_ref=COMPANY_REF,
        claim_text="Fish Audio's open-source TTS repository is independently, publicly visible with a real star count.",
        subject_entity="Fish Audio",
        source_url="https://github.com/fishaudio/fish-speech",
        source_publisher="GitHub (fishaudio/fish-speech repository)",
        source_type=SourceType.AGGREGATOR_OR_DIRECTORY,
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="SOTA Open Source TTS",
        assessment_criteria=["technical_depth_signal"],
        independence_group_id="fishaudio-live-github-repo",
    ),
    # --- Differentiation Claim Corroboration (independent) ---
    Claim(
        claim_id="fishaudio-live-003",
        company_ref=COMPANY_REF,
        claim_text="An independent comparison finds Fish Audio priced far below ElevenLabs for equivalent API usage.",
        subject_entity="Fish Audio",
        source_url="https://www.bland.ai/blog/fish-audio-vs-elevenlabs",
        source_publisher="Bland AI",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 9, 14),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="a 4x to 11x gap depending on which tier",
        assessment_criteria=["differentiation_claim_corroboration"],
        independence_group_id="fishaudio-live-blandai-comparison",
    ),
    # --- Stage signal ---
    Claim(
        claim_id="fishaudio-live-stage-001",
        company_ref=COMPANY_REF,
        claim_text="TechCrunch independently reports Fish Audio's $52M seed round led by Coreline Ventures and Capital Today.",
        subject_entity="Fish Audio",
        source_url="https://techcrunch.com/2026/07/28/fish-audio-raises-50m-seed-to-build-ai-voice-models-for-creators-and-enterprises/",
        source_publisher="TechCrunch",
        source_type=SourceType.INDEPENDENT_REPORTING,
        published_at=date(2026, 7, 28),
        retrieved_at=RETRIEVED_AT,
        support_status=SupportStatus.DIRECTLY_SUPPORTED,
        excerpt="$52 million in seed funding",
        assessment_criteria=["stage_signal"],
        independence_group_id="fishaudio-live-seed-techcrunch",
        structured_fact={"kind": "funding_round_type", "value": "Seed"},
    ),
    # No defensibility_signal-tagged claim: none was found during real
    # research for this company as of the retrieval date above.
]
