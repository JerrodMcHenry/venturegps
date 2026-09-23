import { apiFetch } from "../client";

// Increment 18.4 -- typed wrappers around the internal review API (app/v2_review_api.py, mounted at
// /admin/v2-review). Deliberately built on the top-level apiFetch (lib/api/client.ts), NOT lib/api/v2/client.ts's
// v2Fetch: v2Fetch is a purpose-built transport for the PUBLIC, unauthenticated Capital API and has no `token`
// support at all. Every function here requires a Clerk session token and every call maps to an admin-gated
// backend route -- a non-admin's own valid token still gets a real 403 from RequireAdmin, never a client-side
// guess. No function in this file accepts or sends a reviewer/authority identity: the backend derives it
// exclusively from the verified session (see app/v2_review_api.py's _authority_for).

const PREFIX = "/admin/v2-review";

export type EvidenceExcerpt = {
  text: string;
  byte_start: number;
  byte_end: number;
};

export type SourceInfo = {
  source_key: string;
  name: string;
  source_type: string;
  collection_method: string;
};

export type ProvenanceInfo = {
  observation_id: number;
  source: SourceInfo;
  source_record_identifier: string | null;
  observed_time: string;
  collector_id: string;
  collection_version: string;
};

export type DecisionRecord = {
  id: number;
  decision_kind: string;
  company_id: string | null;
  financing_event_id: string | null;
  authority_kind: string;
  authority_id: string;
  reason_code: string | null;
  created_at: string;
};

// ---------------------------------------------------------------- company candidates

export type CompanyCandidateSummary = {
  id: number;
  processing_attempt_id: number;
  candidate_ordinal: number;
  proposed_name: string;
  created_at: string;
  resolution_state: string;
};

export type ProposedIdentifierOut = {
  identifier_type: string;
  value: string;
  evidence: EvidenceExcerpt;
};

export type IdentityMatch = {
  identifier_type: string;
  value: string;
  matching_company_ids: string[];
};

export type CompanyCandidateDetail = CompanyCandidateSummary & {
  name_evidence: EvidenceExcerpt;
  identifiers: ProposedIdentifierOut[];
  provenance: ProvenanceInfo;
  decisions: DecisionRecord[];
  identity_matches: IdentityMatch[];
};

export type CompanyDecisionAction = "create" | "attach" | "reject" | "defer";

export type DecisionResult = {
  decision_id: number | null;
  decision_kind: string;
  company_id: string | null;
  financing_event_id: string | null;
  accepted_name: boolean;
  accepted_identifier_count: number;
  accepted_stage: boolean;
  accepted_financing_type: boolean;
  accepted_verified_round_amount: boolean;
  accepted_dates: string[];
};

export function listPendingCompanyCandidates(
  token: string,
  params?: { limit?: number; offset?: number }
): Promise<CompanyCandidateSummary[]> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  if (params?.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  return apiFetch<CompanyCandidateSummary[]>(
    `${PREFIX}/company-candidates${qs ? `?${qs}` : ""}`,
    { token }
  );
}

export function getCompanyCandidateDetail(
  token: string,
  candidateId: number
): Promise<CompanyCandidateDetail> {
  return apiFetch<CompanyCandidateDetail>(
    `${PREFIX}/company-candidates/${candidateId}`,
    { token }
  );
}

export function decideCompanyCandidate(
  token: string,
  candidateId: number,
  body: { action: CompanyDecisionAction; company_id?: string; reason_code?: string }
): Promise<DecisionResult> {
  return apiFetch<DecisionResult>(`${PREFIX}/company-candidates/${candidateId}/decide`, {
    method: "POST",
    token,
    body: { ...body, confirm: true },
  });
}

// ---------------------------------------------------------------- financing candidates

export type FinancingCandidateSummary = {
  id: number;
  processing_attempt_id: number;
  candidate_ordinal: number;
  company_id: string;
  created_at: string;
  resolution_state: string;
};

export type ProposedAmountOut = {
  semantics: string;
  currency_code: string;
  minor_units: number;
  evidence: EvidenceExcerpt;
};

export type ProposedDateOut = {
  kind: string;
  precision: string;
  start: string;
  evidence: EvidenceExcerpt;
};

export type FinancingCandidateDetail = FinancingCandidateSummary & {
  company_is_canonical: boolean;
  event_evidence: EvidenceExcerpt;
  stage: string | null;
  stage_evidence: EvidenceExcerpt | null;
  financing_type: string | null;
  financing_type_evidence: EvidenceExcerpt | null;
  amounts: ProposedAmountOut[];
  dates: ProposedDateOut[];
  provenance: ProvenanceInfo;
  decisions: DecisionRecord[];
  existing_events: string[];
};

export type FinancingDecisionAction = "create_event" | "attach_to_event" | "reject" | "defer";

export type FactSelectionInput = {
  stage?: boolean;
  financing_type?: boolean;
  verified_round_amount?: boolean;
  dates?: Array<"first_sale_date" | "filing_date" | "announcement_date">;
};

export function listPendingFinancingCandidates(
  token: string,
  params?: { limit?: number; offset?: number }
): Promise<FinancingCandidateSummary[]> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  if (params?.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  return apiFetch<FinancingCandidateSummary[]>(
    `${PREFIX}/financing-candidates${qs ? `?${qs}` : ""}`,
    { token }
  );
}

export function getFinancingCandidateDetail(
  token: string,
  candidateId: number
): Promise<FinancingCandidateDetail> {
  return apiFetch<FinancingCandidateDetail>(
    `${PREFIX}/financing-candidates/${candidateId}`,
    { token }
  );
}

export function decideFinancingCandidate(
  token: string,
  candidateId: number,
  body: {
    action: FinancingDecisionAction;
    event_id?: string;
    facts?: FactSelectionInput;
    reason_code?: string;
  }
): Promise<DecisionResult> {
  return apiFetch<DecisionResult>(`${PREFIX}/financing-candidates/${candidateId}/decide`, {
    method: "POST",
    token,
    body: { ...body, confirm: true },
  });
}

// ---------------------------------------------------------------- companies / market classification

export type CompanyNameOut = { name: string; role: string };
export type CompanyIdentifierOut = { identifier_type: string; value: string };

export type ClassificationOut = {
  id: number;
  company_id: string;
  market_id: string;
  taxonomy_version: string;
  role: string;
  authority_id: string;
  created_at: string;
};

export type CompanyDetail = {
  id: string;
  created_at: string;
  names: CompanyNameOut[];
  identifiers: CompanyIdentifierOut[];
  classifications: ClassificationOut[];
};

export type MarketOut = { id: string; slug: string; display_name: string };

export function getCompanyDetail(token: string, companyId: string): Promise<CompanyDetail> {
  return apiFetch<CompanyDetail>(`${PREFIX}/companies/${companyId}`, { token });
}

export function listReviewMarkets(token: string): Promise<MarketOut[]> {
  return apiFetch<MarketOut[]>(`${PREFIX}/markets`, { token });
}

export function listReviewTaxonomyVersions(token: string): Promise<string[]> {
  return apiFetch<string[]>(`${PREFIX}/taxonomy-versions`, { token });
}

export function classifyCompany(
  token: string,
  companyId: string,
  body: { market_id: string; taxonomy_version: string; role?: "primary" | "secondary" }
): Promise<ClassificationOut> {
  return apiFetch<ClassificationOut>(`${PREFIX}/companies/${companyId}/classify`, {
    method: "POST",
    token,
    body: { role: "primary", ...body, confirm: true },
  });
}
