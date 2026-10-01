import Link from "next/link";
import { auth } from "@clerk/nextjs/server";

import { getEvidenceV1Analysis } from "@/lib/api";
import BaseCard from "@/components/ui/BaseCard";
import EvidenceV1Report from "@/components/evidence/EvidenceV1Report";

import type { EvidenceV1AnalysisDetail } from "@/types";

type Props = {
  params: Promise<{
    analysisId: string;
  }>;
};

function isNotFoundError(error: unknown): boolean {
  return error instanceof Error && /\(404\)/.test(error.message);
}

async function loadAnalysis(
  analysisId: string,
  token: string | null
): Promise<EvidenceV1AnalysisDetail | null> {
  try {
    return await getEvidenceV1Analysis(analysisId, token);
  } catch (error) {
    if (isNotFoundError(error)) {
      return null;
    }
    throw error;
  }
}

// Task 31 item 9/10 -- this page is reachable ONLY via a stable
// analysis_id the caller was given at submission time (or from their own
// My Analyses list) -- there is no company-name-keyed lookup anywhere on
// this route. GET /evidence-v1/analyses/{id} on the backend independently
// enforces authentication and ownership (app/evidence_v1/router.py) --
// this page-level auth.protect() is a UX-only layer on top of that real
// boundary, same convention as app/startup/[id]/page.tsx.
export default async function EvidenceV1AnalysisPage({ params }: Props) {
  await auth.protect();
  const { getToken } = await auth();
  const token = await getToken();

  const { analysisId } = await params;
  const analysis = await loadAnalysis(analysisId, token);

  if (!analysis) {
    return (
      <BaseCard variant="glass" className="p-10 text-center">
        <h1 className="text-2xl font-bold text-text-primary">Analysis not found</h1>
        <p className="mt-3 text-text-secondary">
          This analysis doesn&apos;t exist, or isn&apos;t one you have access to.
        </p>
        <Link
          href="/my-analyses"
          className="mt-6 inline-flex text-sm font-semibold text-primary hover:text-primary-hover"
        >
          Back to My Analyses →
        </Link>
      </BaseCard>
    );
  }

  return <EvidenceV1Report analysis={analysis} />;
}
