"""
Task 31 -- Evidence Engine v1's own API response model. Deliberately
separate from `app.models.startup.StartupAnalysisResponse` (legacy's own
response shape) -- forcing the Evidence v1 result into that model would
either drop information or imply fields (an overall 0-100 score, a
startup_scorecard) this methodology deliberately does not produce
(docs/architecture/EVIDENCE_ENGINE_PRODUCT_INTEGRATION.md).
"""

from __future__ import annotations

from pydantic import BaseModel


class EvidenceV1AnalysisResponse(BaseModel):
    analysis_id: str
    engine: str = "evidence_v1"
    methodology_version: str
    company_name: str
    canonical_website: str
    stage: str
    company_coverage_pct: float | None
    company_confidence: str | None
    company_publishable: bool
