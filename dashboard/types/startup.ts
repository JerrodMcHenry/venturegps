// Canonical Dashboard MVP: get_top_startups() now returns exactly
// get_rankings()'s rows (see app/database/db.py), which never include
// readiness_score -- that field was dropped, not just left unrendered
// (readiness_score has no defined numeric scale; see the P0 Product Trust
// Cleanup report).
export interface StartupRanking {
  company_name: string;
  industry: string;
  stage: string;
  overall_score: number;
}

export interface ImprovingStartup {
  company_name: string;
  first_score: number;
  latest_score: number;
  score_change: number;
}

export interface RankingEntry {
  id: number;
  company_name: string | null;
  industry: string | null;
  stage: string | null;
  business_model: string | null;
  overall_score: number | null;
  market_score: number | null;
  team_score: number | null;
  product_score: number | null;
  competition_score: number | null;
  traction_score: number | null;
  financial_score: number | null;
  recommendation: string | null;
  created_at: string;
}

export type ConfidenceLevel = "Low" | "Medium" | "High";

export type Evidence = {
  source?: string;
  text?: string;
  title?: string;
  url?: string;
};

export type Subscore = {
  name: string;
  score: number | null;
  weight: number;
  confidence?: ConfidenceLevel;
  evidence_status?: string;
  rationale?: string;
  evidence?: string[];
  recommendations?: string[];
  missing_information?: string[];
};

export type PillarScoreBreakdown = {
  pillar?: string;
  score?: number | null;
  confidence?: ConfidenceLevel;
  evidence_coverage?: number;
  scoring_summary?: string;
  subscores?: Subscore[];
};

export type PillarAnalysis = {
  score: number | null;
  confidence: ConfidenceLevel;
  summary: string;
  evidence: Array<Evidence | string>;
  strengths: string[];
  weaknesses: string[];
  recommendations: string[];
  score_breakdown: PillarScoreBreakdown;
};

export type SIEContext = {
  company_name: string;
  industry: string;
  business_model: string;
  company_stage: string;
  funding_stage: string;
};

// SIE Methodology v2, Part 9 item 6 (Blocker 3): a purely additive,
// display-only whole-pillar-coverage label -- never a math adjustment to
// startup_intelligence_score. Optional/nullable because analyses stored
// before this field existed have no key for it at all.
export type PartialStructuralCoverage = {
  partial_structural_coverage: boolean;
  pillars_unavailable_entirely: string[];
  note: string;
};

// Phase 10.9, Part 5: mirrors app/models/sps_v3.py's SPSV3Assessment /
// SPSV3PillarResult. Additive alongside every V2.1 field on
// SIEMethodologyAnalysis below -- undefined/null on any analysis that
// predates this field, or that was produced while the backend's V3
// feature flag was off. A non-null value here is the ONLY signal that
// this analysis has a V3 assessment at all -- see
// docs/methodology/SPS_V3_PRODUCTION_INTEGRATION_10_9.md.
export type SPSV3ConfidenceLevel = "Low" | "Medium" | "High";

export type SPSV3AssessmentState = "sufficient" | "limited" | "insufficient";

export type SPSV3PillarResult = {
  pillar: string;
  // null means this pillar itself did not clear its own coverage floor
  // -- never a fabricated/defaulted number.
  strength: number | null;
  coverage_pct: number;
  confidence: SPSV3ConfidenceLevel;
  publishable: boolean;
  withhold_reason: string | null;
};

export type SPSV3Assessment = {
  engine_version: string;
  scoring_version: string;
  // The published Startup Power Score under the V3 methodology. null is
  // a legitimate, common, EXPECTED value (assessment_state !==
  // "sufficient") -- it must never be read as, or rendered as, 0.
  overall_score: number | null;
  coverage_pct: number;
  confidence: SPSV3ConfidenceLevel;
  assessment_state: SPSV3AssessmentState;
  withhold_reason: string | null;
  pillars: Record<string, SPSV3PillarResult>;
  computed_at: string;
};

// Task 5 -- Unified Visual Design (AI transparency addendum). Mirrors
// app/models/analysis_context.py::AnalysisContext -- every field is
// optional/defaulted there too ("Populated only for analyses run after
// this field set was added... loading an older stored methodology JSONB
// -- which never had these keys -- leaves them blank rather than
// pretending that analysis carried provenance it never actually
// recorded"). Replaces the previous `analysis_context?: unknown` so the
// new "How this analysis was generated" section can read these fields
// safely, typed -- this is a frontend typing addition only, not a
// backend contract change; the JSON shape was already exactly this.
export type SIEAnalysisContext = {
  analysis_type?: string;
  evidence_sources?: string[];
  missing_information?: string[];
  methodology_version?: string;
  anchor_registry_version?: string;
  scoring_version?: string;
  model_identifier?: string;
  prompt_version?: string;
  company_text_hash?: string;
  search_query?: string;
  research_brief_snapshot?: string;
  source_snapshot?: Array<{ title?: string; url?: string }>;
  analyzed_at?: string;
};

export type SIEMethodologyAnalysis = {
  context: SIEContext;

  market: PillarAnalysis;
  team: PillarAnalysis;
  product: PillarAnalysis;
  execution: PillarAnalysis;
  traction: PillarAnalysis;
  financial_health: PillarAnalysis;

  startup_intelligence_score: number;
  milestone_readiness_score: number;
  momentum_score: number;
  confidence_score: number;

  executive_coaching_summary: string;
  next_actions: string[];

  structural_coverage?: PartialStructuralCoverage | null;

  startup_scorecard?: unknown;
  analysis_context?: SIEAnalysisContext;

  sps_v3?: SPSV3Assessment | null;
};

export type StartupProfileResponse = {
  id: number;
  // Saved Startups (Watchlist Phase 1): the canonical Startup FK, additive
  // alongside `id` (which is the analysis id, not the startup id -- see
  // the backend's get_startup_by_name() docstring). null only for
  // historical rows that predate the write path; the Save control hides
  // itself rather than guessing an id to save.
  startup_id: number | null;
  // Phase 37E: always present, even when has_analysis is false.
  canonical_name: string;
  created_at: string;
  // Phase 37E -- Company Lifecycle + Public Identity Convergence,
  // Section 6: null exactly when has_analysis is false -- a company that
  // exists but hasn't been analyzed yet. Never fabricated.
  methodology: SIEMethodologyAnalysis | null;
  has_analysis: boolean;
};

// Saved Startups (Watchlist Phase 1): GET /me/saved-startups row shape.
// Deliberately flat, mirroring RankingEntry -- every field is read fresh
// from the startup's current latest canonical analysis on every request,
// never a snapshot copied in at save time. industry/stage/overall_score/
// latest_analysis_at are null when the saved startup currently has no
// canonical analysis -- never fabricated.
export type SavedStartupEntry = {
  startup_id: number;
  company_name: string;
  industry: string | null;
  stage: string | null;
  overall_score: number | null;
  latest_analysis_at: string | null;
  saved_at: string;
};

export type SavedStartupStatus = {
  saved: boolean;
};

// Portfolio Release Task 4 -- My Analyses: GET /me/analyses row shape.
// One row PER ANALYSIS (submitted_by_user_id = the caller), not per
// startup -- see app/models/startup.py::MyAnalysisEntry's own docstring
// for why this differs from SavedStartupEntry above. startup_id/
// company_name are nullable only defensively; every real write path
// that sets submitted_by_user_id also resolves a real startup_id.
export type MyAnalysisEntry = {
  analysis_id: number;
  startup_id: number | null;
  company_name: string | null;
  overall_score: number | null;
  created_at: string;
};

// One point per canonical (methodology-bearing) analysis, sourced from
// GET /startup/{company_name}/sps-history. Chronological order.
export type SPSHistoryPoint = {
  analysis_id: number;
  created_at: string;
  startup_intelligence_score: number;
};
