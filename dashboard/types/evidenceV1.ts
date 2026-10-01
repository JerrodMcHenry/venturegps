// Task 31 -- Evidence Engine v1 product integration. Deliberately
// SEPARATE from StartupAnalysisResponse/SIEContext (types/analyze.ts,
// types/startup.ts) -- the two methodologies are different shapes with
// different meanings (no overall 0-100 score here; Coverage/Confidence
// are not the same concept as a legacy score), not two names for the
// same thing. Matches app/evidence_v1/api_models.py::
// EvidenceV1AnalysisResponse and app/evidence_v1/router.py's own
// response shapes exactly.

export interface EvidenceV1AnalysisResponse {
  analysis_id: string;
  engine: "evidence_v1";
  methodology_version: string;
  company_name: string;
  canonical_website: string;
  stage: string;
  company_coverage_pct: number | null;
  company_confidence: "Low" | "Medium" | "High" | null;
  company_publishable: boolean;
}

export interface EvidenceV1DimensionResult {
  dimension: string;
  category: "computed" | "classified";
  weight: number;
  score: number | null;
  availability: string;
  supporting_claim_ids: string[];
  confidence: "Low" | "Medium" | "High";
  rationale: string;
  classification_label: string | null;
}

export interface EvidenceV1PillarResult {
  pillar: string;
  strength: number | null;
  coverage_pct: number;
  confidence: "Low" | "Medium" | "High";
  publishable: boolean;
  withhold_reasons: string[];
  dimension_results: EvidenceV1DimensionResult[];
}

export interface EvidenceV1Claim {
  claim_id: string;
  claim_text: string;
  subject_entity: string;
  source_url: string | null;
  source_publisher: string;
  source_type: string;
  published_at: string | null;
  retrieved_at: string;
  support_status: string;
  excerpt: string | null;
  assessment_criteria: string[];
  independence_group_id: string;
  structured_fact: Record<string, string> | null;
}

// GET /evidence-v1/analyses/{analysis_id} -- the full, persisted,
// immutable result. `result`/`telemetry` mirror exactly what
// app/evidence_v1/persistence/repository.py wrote at submission time.
export interface EvidenceV1AnalysisDetail {
  analysis_id: string;
  engine: "evidence_v1";
  methodology_version: string;
  company_name: string;
  canonical_website: string;
  stage: string;
  run_status: "completed" | "failed";
  company_coverage_pct: number | null;
  company_confidence: "Low" | "Medium" | "High" | null;
  company_publishable: boolean;
  created_at: string;
  result: {
    company_ref: string;
    as_of: string;
    generated_at: string;
    total_claims_in_ledger: number;
    rejected_count: number;
    accepted_claims: EvidenceV1Claim[];
    pillar_results: EvidenceV1PillarResult[];
    company_withhold_reasons: string[];
    cross_pillar_audit: unknown[];
    wall_clock_seconds: number;
  };
  telemetry: Record<string, unknown> | null;
}

// GET /me/analyses/evidence-v1 -- one flat row per analysis.
export interface EvidenceV1MyAnalysisEntry {
  analysis_id: string;
  company_name: string;
  canonical_website: string;
  company_coverage_pct: number | null;
  company_confidence: "Low" | "Medium" | "High" | null;
  company_publishable: boolean;
  created_at: string;
}
