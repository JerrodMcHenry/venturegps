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

export type CompanyCandidatePage = {
  items: CompanyCandidateSummary[];
  total: number;
  limit: number;
  offset: number;
};

// Increment 18.5: status/search/include_test_sources are shared by both candidate list endpoints.
export type ReviewQueueFilters = {
  status?: "pending" | "resolved" | "all";
  search?: string;
  includeTestSources?: boolean;
  limit?: number;
  offset?: number;
};

function queryStringFor(filters?: ReviewQueueFilters): string {
  const query = new URLSearchParams();
  if (filters?.status !== undefined) query.set("status", filters.status);
  if (filters?.search) query.set("search", filters.search);
  if (filters?.includeTestSources) query.set("include_test_sources", "true");
  if (filters?.limit !== undefined) query.set("limit", String(filters.limit));
  if (filters?.offset !== undefined) query.set("offset", String(filters.offset));
  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

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

export function listCompanyCandidates(
  token: string,
  filters?: ReviewQueueFilters
): Promise<CompanyCandidatePage> {
  return apiFetch<CompanyCandidatePage>(`${PREFIX}/company-candidates${queryStringFor(filters)}`, { token });
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

export type FinancingCandidatePage = {
  items: FinancingCandidateSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type FinancingDecisionAction = "create_event" | "attach_to_event" | "reject" | "defer";

export type FactSelectionInput = {
  stage?: boolean;
  financing_type?: boolean;
  verified_round_amount?: boolean;
  dates?: Array<"first_sale_date" | "filing_date" | "announcement_date">;
};

export function listFinancingCandidates(
  token: string,
  filters?: ReviewQueueFilters
): Promise<FinancingCandidatePage> {
  return apiFetch<FinancingCandidatePage>(`${PREFIX}/financing-candidates${queryStringFor(filters)}`, { token });
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

// ---------------------------------------------------------------- lifecycle candidates (Increment 18.7)

export type LifecycleCandidateSummary = {
  id: number;
  processing_attempt_id: number;
  candidate_ordinal: number;
  company_id: string;
  fact_kinds: string[];
  created_at: string;
  resolution_state: string;
};

export type LifecycleCandidatePage = {
  items: LifecycleCandidateSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type ProposedNameChangeOut = { new_name: string; effective: string | null; evidence: EvidenceExcerpt };
export type ProposedOperatingStatusOut = { status: string; as_of: string | null; evidence: EvidenceExcerpt };
export type ProposedAcquisitionOut = {
  acquirer_name: string;
  acquirer_company_id: string | null;
  transaction_date: string | null;
  evidence: EvidenceExcerpt;
};
export type ProposedSuccessorOut = {
  related_entity_name: string;
  relationship_kind: string;
  related_company_id: string | null;
  evidence: EvidenceExcerpt;
};

// What the company's CURRENT accepted lifecycle facts already say, wherever this candidate proposes something
// of the same fact kind -- the exact consequence of accepting, shown before the reviewer acts. Never blocking.
export type LifecycleConflict = { kind: string; description: string };

export type LifecycleCandidateDetail = LifecycleCandidateSummary & {
  company_is_canonical: boolean;
  existing_company_name: string | null;
  existing_current_legal_name: string | null;
  existing_current_operating_status: string | null;
  event_evidence: EvidenceExcerpt;
  name_change: ProposedNameChangeOut | null;
  operating_status: ProposedOperatingStatusOut | null;
  acquisition: ProposedAcquisitionOut | null;
  successor: ProposedSuccessorOut | null;
  provenance: ProvenanceInfo;
  decisions: DecisionRecord[];
  conflicts: LifecycleConflict[];
};

export type LifecycleDecisionAction = "accept" | "reject" | "defer";

export type LifecycleFactSelectionInput = {
  name_change?: boolean;
  operating_status?: boolean;
  acquisition?: boolean;
  successor?: boolean;
};

export type LifecycleDecisionResult = {
  decision_id: number | null;
  decision_kind: string;
  company_id: string | null;
  accepted_name_change: boolean;
  accepted_operating_status: boolean;
  accepted_acquisition: boolean;
  accepted_successor: boolean;
};

export function listLifecycleCandidates(
  token: string,
  filters?: ReviewQueueFilters
): Promise<LifecycleCandidatePage> {
  return apiFetch<LifecycleCandidatePage>(`${PREFIX}/lifecycle-candidates${queryStringFor(filters)}`, { token });
}

export function getLifecycleCandidateDetail(
  token: string,
  candidateId: number
): Promise<LifecycleCandidateDetail> {
  return apiFetch<LifecycleCandidateDetail>(`${PREFIX}/lifecycle-candidates/${candidateId}`, { token });
}

export function decideLifecycleCandidate(
  token: string,
  candidateId: number,
  body: { action: LifecycleDecisionAction; facts?: LifecycleFactSelectionInput; reason_code?: string }
): Promise<LifecycleDecisionResult> {
  return apiFetch<LifecycleDecisionResult>(`${PREFIX}/lifecycle-candidates/${candidateId}/decide`, {
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

// ---------------------------------------------------------------- collection operations (Increment 18.5)

export type CollectionRunOut = {
  id: number;
  job_name: string;
  trigger_type: string;
  triggered_by: string;
  status: "running" | "succeeded" | "failed" | "partial" | "interrupted";
  query: string;
  max_filings: number;
  started_at: string;
  completed_at: string | null;
  discovered_count: number;
  collected_count: number;
  duplicate_count: number;
  failed_count: number;
  candidate_count: number;
  failure_detail: string | null;
};

export type CollectionOperationsSummary = {
  pending_company_candidates: number;
  pending_financing_candidates: number;
  recent_runs: CollectionRunOut[];
};

export function listCollectionRuns(
  token: string,
  params?: { jobName?: string; limit?: number }
): Promise<CollectionRunOut[]> {
  const query = new URLSearchParams();
  if (params?.jobName) query.set("job_name", params.jobName);
  if (params?.limit !== undefined) query.set("limit", String(params.limit));
  const qs = query.toString();
  return apiFetch<CollectionRunOut[]>(`${PREFIX}/collection-runs${qs ? `?${qs}` : ""}`, { token });
}

export function getCollectionSummary(token: string): Promise<CollectionOperationsSummary> {
  return apiFetch<CollectionOperationsSummary>(`${PREFIX}/collection-summary`, { token });
}

// A manual trigger runs the real, bounded (<=25 filing) SEC collection pipeline synchronously within the
// request -- there is no background job queue (Increment 18.5's own decision: no Celery/Redis). It can
// legitimately take longer than a normal API call, so this gets a generous timeout rather than the default.
const TRIGGER_TIMEOUT_MS = 120_000;

export function triggerCollection(
  token: string,
  body: { query: string; max_filings?: number; job_name?: string }
): Promise<CollectionRunOut> {
  return apiFetch<CollectionRunOut>(`${PREFIX}/collection-runs/trigger`, {
    method: "POST",
    token,
    timeoutMs: TRIGGER_TIMEOUT_MS,
    body: { ...body, confirm: true },
  });
}
