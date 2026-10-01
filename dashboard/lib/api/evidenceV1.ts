import type {
  EvidenceV1AnalysisDetail,
  EvidenceV1MyAnalysisEntry,
} from "@/types";

import { apiFetch } from "./client";

// Task 31 -- Evidence Engine v1 product integration. GET /evidence-v1/
// analyses/{analysis_id} is authenticated and ownership-scoped server-side
// (app/evidence_v1/router.py) -- a 404 here means either the id does not
// exist or it belongs to another user; this client never distinguishes
// the two, matching the backend's own non-leaking behavior.
export function getEvidenceV1Analysis(
  analysisId: string,
  token: string | null
): Promise<EvidenceV1AnalysisDetail> {
  return apiFetch<EvidenceV1AnalysisDetail>(
    `/evidence-v1/analyses/${encodeURIComponent(analysisId)}`,
    { token }
  );
}

// GET /me/analyses/evidence-v1 -- this caller's own Evidence-v1 analyses
// only, newest first. A separate list from legacy's getMyAnalyses() (the
// two engines' rows have different shapes) -- app/my-analyses/
// MyAnalysesView.tsx combines both for one unified view.
export function getMyEvidenceV1Analyses(
  token: string | null
): Promise<EvidenceV1MyAnalysisEntry[]> {
  return apiFetch<EvidenceV1MyAnalysisEntry[]>("/me/analyses/evidence-v1", { token });
}
