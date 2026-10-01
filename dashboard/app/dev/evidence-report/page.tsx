import { notFound } from "next/navigation";

import EvidenceV1Report from "@/components/evidence/EvidenceV1Report";
import fixture from "@/tests/fixtures/evidenceV1NotionOffline.json";

import type { EvidenceV1AnalysisDetail } from "@/types";

// Dev-only preview of the Evidence-v1 report, gated out of production
// exactly like /dev/design-system. The fixture is NOT a live analysis: it
// is app/evidence_engine/fixtures/notion.py run offline through the real
// assemble_full_analysis() and serialized with app/evidence_v1/adapter.py's
// own dict functions -- no network, no AI, no database, no paid call.
export default function EvidenceReportPreviewPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return <EvidenceV1Report analysis={fixture as EvidenceV1AnalysisDetail} />;
}
