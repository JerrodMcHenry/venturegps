from pydantic import BaseModel, Field, field_validator
from typing import Literal

from app.models.scoring import StartupIntelligenceScore, PillarScoreBreakdown, EvidenceStatus
from app.models.evidence import Evidence
from app.models.analysis_context import AnalysisContext
from app.models.sps_v3 import SPSV3Assessment
from datetime import datetime


ConfidenceLevel = Literal["Low", "Medium", "High"]

# MVP hardening: bounds on oversized/empty input. Pydantic rejects a
# violating request with a 422 before the route body (and the real,
# multi-minute, paid pipeline call) ever runs. 50,000 characters is a
# generous ceiling for a company description -- comfortably above any
# real submission seen in testing (a few thousand characters) -- meant
# to stop a pathological paste (an entire scraped site, a whole PDF's
# raw text, etc.), not to constrain legitimate use. Pulled out to a
# constant (Unified Multi-Source Analyze Startup) so POST /analyze can
# reuse the exact same bound when validating its raw company_text form
# field via this same model, rather than duplicating the number.
MAX_COMPANY_TEXT_LENGTH = 50_000


class StartupAnalysisRequest(BaseModel):
    company_text: str = Field(min_length=1, max_length=MAX_COMPANY_TEXT_LENGTH)


class WebsiteAnalysisRequest(BaseModel):
    # Website / URL Ingestion: bounds obviously-invalid input with a fast
    # 422 before any network I/O -- the real security validation (scheme
    # allow-list, private-network rejection, DNS-rebinding-safe pinning,
    # bounded redirects/response size) happens in
    # app/website_scrapper.py, which is the one place that knowledge
    # should live. 2048 chars is a generous ceiling for a URL (well above
    # any real company website URL, including ones with query strings),
    # meant to reject a pathological paste, not to constrain real use.
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("url")
    @classmethod
    def _must_look_like_a_url(cls, value: str) -> str:
        trimmed = value.strip()

        if not trimmed.lower().startswith(("http://", "https://")):
            raise ValueError("Website URL must start with http:// or https://")

        return trimmed


class PillarAnalysis(BaseModel):
    score: float | None = None
    confidence: ConfidenceLevel = "Low"
    summary: str = ""
    evidence: list[Evidence | str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    score_breakdown: PillarScoreBreakdown = Field(default_factory=PillarScoreBreakdown)


class SIEContext(BaseModel):
    company_name: str = ""
    industry: str = ""
    business_model: str = ""
    company_stage: str = ""
    funding_stage: str = ""


class PartialStructuralCoverage(BaseModel):
    """
    SIE Methodology v2, Part 9 item 6 (Blocker 3 fix, post-implementation
    review): a purely additive, DISPLAY-ONLY label for whole-pillar evidence
    absence. Computed by
    app.ai.sie_v2_evidence_semantics.compute_partial_structural_coverage()
    from each pillar's already-existing final score (None == that pillar had
    zero scored dimensions). Never a math adjustment to SPS -- startup_
    intelligence_score is computed identically whether or not this field is
    populated. field is None (not this model's zero-value) on every analysis
    that predates this field, so historical JSONB records are never silently
    reinterpreted as "fully covered."
    """

    partial_structural_coverage: bool = False
    pillars_unavailable_entirely: list[str] = Field(default_factory=list)
    note: str = ""


class SIEMethodologyAnalysis(BaseModel):
    context: SIEContext = Field(default_factory=SIEContext)

    analysis_context: AnalysisContext | None = None

    market: PillarAnalysis = Field(default_factory=PillarAnalysis)
    team: PillarAnalysis = Field(default_factory=PillarAnalysis)
    product: PillarAnalysis = Field(default_factory=PillarAnalysis)
    execution: PillarAnalysis = Field(default_factory=PillarAnalysis)
    traction: PillarAnalysis = Field(default_factory=PillarAnalysis)
    financial_health: PillarAnalysis = Field(default_factory=PillarAnalysis)

    startup_intelligence_score: float = 0.0
    startup_scorecard: StartupIntelligenceScore = Field(default_factory=StartupIntelligenceScore)

    milestone_readiness_score: float = 0.0
    momentum_score: float = 0.0
    confidence_score: float = 0.0

    # None (not PartialStructuralCoverage()'s own zero-value) is the
    # backward-compatible default: a record stored before this field existed
    # decodes to None here, never to a fabricated "fully covered" reading.
    structural_coverage: PartialStructuralCoverage | None = None

    executive_coaching_summary: str = ""
    next_actions: list[str] = Field(default_factory=list)

    # Phase 10.9, Part 5: the SPS V3 assessment, additive alongside every
    # V2.1 field above (startup_intelligence_score, startup_scorecard,
    # etc.) -- none of which this touches or reinterprets. None on every
    # analysis produced before this field existed, and on every analysis
    # produced while the V3 feature flag is off (see
    # app/ai/sps_v3_adapter.py's SPS_V3_ENABLED) -- never backfilled,
    # never inferred from the V2.1 fields. A non-None value here is the
    # ONLY signal that this analysis has a V3 assessment at all.
    sps_v3: SPSV3Assessment | None = None



class StartupAnalysisResponse(BaseModel):
    context: SIEContext = Field(default_factory=SIEContext)
    startup_scorecard: StartupIntelligenceScore = Field(default_factory=StartupIntelligenceScore)
    methodology: SIEMethodologyAnalysis = Field(default_factory=SIEMethodologyAnalysis)


class UpdateAnalysisRequest(BaseModel):
    methodology: SIEMethodologyAnalysis

class StartupProfileResponse(BaseModel):
    id: int
    # Saved Startups (Watchlist Phase 1): the canonical Startup FK
    # (analyses.startup_id), additive alongside the existing analysis-id
    # `id` field above -- see get_startup_by_name()'s docstring. None only
    # for historical rows that predate both the write path and its
    # backfill; the frontend Save control hides itself when this is None
    # rather than guessing an id to save.
    startup_id: int | None = None
    # Phase 37E -- Company Lifecycle + Public Identity Convergence,
    # Section 6. The company's own canonical name -- always present, even
    # when has_analysis is False, so the honest "not yet evaluated" state
    # can still say whose page this is.
    canonical_name: str
    created_at: datetime
    # None exactly when has_analysis is False -- a company that exists
    # (a real `startups` row) but has never been analyzed. Never a
    # fabricated SPS/pillar breakdown; the frontend renders a distinct,
    # honest state for this case instead of treating it as "not found."
    methodology: SIEMethodologyAnalysis | None = None
    has_analysis: bool = True


class SavedStartupEntry(BaseModel):
    """
    Saved Startups (Watchlist Phase 1) list-row shape -- see
    get_saved_startups_for_user()'s docstring. Deliberately flat and
    minimal (mirrors RankingEntry's shape, not the full nested
    SIEMethodologyAnalysis) since this is a list view, not a second
    startup-details experience; every field here is read fresh from the
    startup's current latest canonical analysis on every request, never
    copied into saved_startups itself. industry/stage/overall_score/
    latest_analysis_at are None when the saved startup currently has no
    canonical analysis -- never fabricated.
    """
    startup_id: int
    company_name: str
    industry: str | None = None
    stage: str | None = None
    overall_score: float | None = None
    latest_analysis_at: datetime | None = None
    saved_at: datetime


class MyAnalysisEntry(BaseModel):
    """
    Portfolio Release Task 4 -- My Analyses list-row shape. See
    get_my_analyses()'s own docstring for why this is one row PER
    ANALYSIS (submitted_by_user_id = the caller), not one row per
    startup the way SavedStartupEntry above is -- two users (or the same
    user, twice) analyzing the same company_name are two separate rows
    here, each reopening its own submitter's own authorized report.
    startup_id/company_name are nullable only for the same defensive
    reason StartupProfileResponse's own startup_id is (a row whose
    startup somehow doesn't resolve) -- never expected in practice, since
    every write path that sets submitted_by_user_id also always resolves
    a real startup_id (see save_analysis()'s own docstring), but the
    frontend still guards against it rather than assuming.
    """
    analysis_id: int
    startup_id: int | None = None
    company_name: str | None = None
    overall_score: float | None = None
    created_at: datetime


class SavedStartupStatus(BaseModel):
    saved: bool


class DiscoveryResult(BaseModel):
    """
    Startup Discovery V1 row shape -- deliberately flat, mirroring
    SavedStartupEntry/RankingEntry (a list view, not a second
    startup-details experience). Every field is read fresh from that
    startup's current latest canonical analysis on every request -- see
    discover_startups()'s own docstring in app/database/db.py. Pillar
    fields are None when that pillar was Unavailable on the underlying
    analysis, never fabricated.
    """
    startup_id: int
    company_name: str
    industry: str | None = None
    stage: str | None = None
    business_model: str | None = None
    overall_score: float | None = None
    market_score: float | None = None
    team_score: float | None = None
    product_score: float | None = None
    execution_score: float | None = None
    traction_score: float | None = None
    financial_score: float | None = None
    created_at: datetime


class DiscoveryResponse(BaseModel):
    total: int
    results: list[DiscoveryResult]


class DiscoveryFilterOptions(BaseModel):
    """
    Startup Discovery V1, Part 4: option lists derived from the real
    canonical population -- see get_discovery_filter_options()'s own
    docstring. Never a hardcoded taxonomy.
    """
    industries: list[str]
    stages: list[str]
    business_models: list[str]


# ---------------------------------------------------------------------------
# Compare Startups V1. This is a deliberately slimmer, purpose-built set of
# models -- not a reuse of PillarAnalysis/SIEMethodologyAnalysis wholesale
# -- so the /compare payload carries only what a side-by-side comparison
# actually needs (no raw evidence quotes, no executive_coaching_summary,
# no momentum/confidence scores never populated by the backend). Every
# field here is read directly from the existing stored methodology JSONB;
# nothing is recomputed, re-scored, or re-summarized by an LLM.
# ---------------------------------------------------------------------------

class ComparisonSubscore(BaseModel):
    name: str
    # None means this dimension could not be responsibly scored --
    # preserved as None here too, never coerced to 0.
    score: float | None = None
    weight: float = 0.0
    confidence: ConfidenceLevel = "Low"
    evidence_status: EvidenceStatus = "Observed"
    rationale: str = ""
    recommendations: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class ComparisonPillar(BaseModel):
    pillar: str
    # None means no dimensions in this pillar were scorable -- i.e. this
    # pillar is Unavailable for this startup. Never defaulted to 0.
    score: float | None = None
    confidence: ConfidenceLevel = "Low"
    evidence_coverage: float = 0.0
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    subscores: list[ComparisonSubscore] = Field(default_factory=list)


class ComparisonStartup(BaseModel):
    startup_id: int
    company_name: str
    industry: str = ""
    company_stage: str = ""
    business_model: str = ""
    latest_analysis_at: datetime
    overall_score: float | None = None

    market: ComparisonPillar
    team: ComparisonPillar
    product: ComparisonPillar
    execution: ComparisonPillar
    traction: ComparisonPillar
    financial_health: ComparisonPillar

    # Phase 10.9, Part 21 -- additive passthrough only. None whenever this
    # startup's latest analysis has no sps_v3 (every historical analysis,
    # and every analysis produced while the V3 feature flag is off).
    # Compare never manufactures comparability between a V2.1-only
    # startup and a V3-assessed one -- see SPS_V3_PRODUCTION_INTEGRATION_10_9.md
    # Section 21 for the exact UI contract this enables.
    sps_v3: SPSV3Assessment | None = None


class ComparisonResponse(BaseModel):
    startups: list[ComparisonStartup]
    # Requested startup_ids that could not be resolved to a canonical
    # analysis -- an invalid/nonexistent id, or a real startup whose only
    # analyses predate Methodology v2. Never silently dropped without a
    # trace: the frontend surfaces this honestly rather than pretending
    # the request was fully satisfied.
    missing_startup_ids: list[int] = Field(default_factory=list)