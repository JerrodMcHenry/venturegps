"""
External I/O boundary Protocols (Task 20 item 20's own "keep external I/O
at the boundary" instruction, and item 1's own isolation-preserving
"reuse the pattern, not the legacy code"). Every network/model call in
this pipeline goes through exactly one of these three interfaces -- no
domain logic (`research_plan.py`, `extraction.py`, `claim_identity.py`,
`contradiction.py`, `pipeline.py`'s own orchestration) ever imports a
search/HTTP/model client directly, matching the same
`ClassificationModel`/`ExtractionModel` Protocol pattern every pillar's
own `classify_with_recovery()`/`extract_with_recovery()` already uses.

**No real (networked) provider is implemented in this task.** A live
run requires paid Tavily/OpenAI calls this task was explicitly told not
to make without approval (item 22). `NotConfiguredProvider` below is the
honest stand-in: it raises a clear, typed error the moment anything
tries to actually call it, so a caller can never accidentally believe a
real network call happened. `docs/architecture/EVIDENCE_ACQUISITION_
PIPELINE.md` §15 describes exactly what a real provider implementing
each Protocol would need to do; writing that (untested, since this
session makes no paid calls) implementation is deliberately left to the
task that receives explicit approval to do so.

Deterministic, offline, fully-tested fakes conforming to these same
three Protocols live in `acquisition/fakes.py` (item 20's own required
offline test mode) -- every test in `tests/test_acquisition_pipeline.py`
runs the real pipeline code against those fakes, never against this
module's own `NotConfiguredProvider`.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from app.evidence_engine.acquisition.models import (
    ExtractionRequest,
    ExtractionResponse,
    ResearchQuery,
    RetrievedSource,
    SearchResult,
)


class SearchProvider(Protocol):
    def search(self, query: ResearchQuery) -> tuple[SearchResult, ...]: ...


class SourceRetriever(Protocol):
    def retrieve(self, result: SearchResult, retrieved_at: date) -> RetrievedSource | None: ...


class EvidenceExtractor(Protocol):
    def extract(self, request: ExtractionRequest) -> ExtractionResponse: ...


class ProviderNotConfiguredError(RuntimeError):
    """Raised by `NotConfiguredProvider` -- the loud, structural failure
    mode that prevents this pipeline from ever silently proceeding as if
    a real network/model call had happened when none was wired in."""


class NotConfiguredProvider:
    """A single class implementing all three Protocols, each method
    raising immediately. Used as the pipeline's own default so that
    calling `run_acquisition_pipeline()` without explicitly supplying
    real providers fails loudly and immediately, rather than silently
    returning an empty analysis that looks like "no evidence was
    found" instead of "no provider was ever configured" -- two
    different failure modes this pipeline keeps structurally distinct."""

    def search(self, query: ResearchQuery) -> tuple[SearchResult, ...]:
        raise ProviderNotConfiguredError(
            "No SearchProvider configured. A live run requires an explicitly-approved, "
            "paid provider (Tavily) -- see EVIDENCE_ACQUISITION_PIPELINE.md §15. "
            "Tests must pass a deterministic fake from acquisition/fakes.py."
        )

    def retrieve(self, result: SearchResult, retrieved_at: date) -> RetrievedSource | None:
        raise ProviderNotConfiguredError(
            "No SourceRetriever configured. A live run requires an explicitly-approved "
            "website-fetch provider -- see EVIDENCE_ACQUISITION_PIPELINE.md §15. "
            "Tests must pass a deterministic fake from acquisition/fakes.py."
        )

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        raise ProviderNotConfiguredError(
            "No EvidenceExtractor configured. A live run requires an explicitly-approved, "
            "paid provider (OpenAI structured extraction) -- see "
            "EVIDENCE_ACQUISITION_PIPELINE.md §15. Tests must pass a deterministic fake "
            "from acquisition/fakes.py."
        )
