"""
Bounded relevance validation (Task 23, LINEAR_001 remediation item 9).

**The problem this closes.** `LIVE_EVALUATION_LINEAR_001.md`'s own
evidence-quality review flagged one accepted claim as "relevance-
questionable despite literal grounding": a personal dev.to blog post
about a THIRD-PARTY hobbyist's own tool that merely USES Linear's ticket
data as one input, extracted as evidence for Linear's own
`differentiation_claim_corroboration`. The excerpt was genuinely,
verbatim present in the source (grounding, unchanged, correctly passed
it) -- but grounding answers "did this source say it," never "is this
fact materially about the company being analyzed." Those are different
questions, and this engine had no mechanism for the second one before
this task.

**The fix -- a small, typed, validated vocabulary, not a second LLM
judgment call left unchecked.** `ExtractedClaimCandidate` (Task 20)
gains one new, OPTIONAL field, `subject_relationship`, populated by the
extractor's OWN system prompt (see `providers_live.py`) with exactly one
of four values:

- `"primary"` -- the claim is directly about the target company itself.
- `"product_integration"` -- an official integration/partnership the
  target company's own product participates in.
- `"customer_or_partner"` -- a customer or business-partner relationship
  involving the target company.
- `"unrelated_third_party"` -- a third party's own project/product that
  merely mentions or uses the target company, not evidence about the
  target company's own capabilities.

`validate_candidate()` (extraction.py) validates this field is one of
the four values or absent -- an out-of-vocabulary value is dropped back
to "unknown" (treated exactly like absent, per this module's own
`UNKNOWN_SUBJECT_RELATIONSHIP` sentinel), never a reason to reject an
otherwise-grounded candidate outright (item 5's "missing remains
preferable to invented," extended here to this field). `strip_
unrelated_third_party_dimensions()` (called from `extraction.py`
alongside `routing.py`'s own kind-based stripping) then removes ONLY the
four kind-agnostic, company-quality-claiming dimensions (`routing.py`'s
own `KIND_AGNOSTIC_DIMENSIONS_NEVER_REACHABLE_BY_A_TYPED_FACT` set --
the exact dimensions with no positive kind-gate of their own, Tasks 8-9)
from a candidate explicitly marked `unrelated_third_party` -- item 9's
own explicit "do not reject legitimate ecosystem/partner evidence simply
because another company is involved": `product_integration`/`customer_
or_partner` are NEVER stripped by this rule, only the fourth, genuinely
tangential category is.

**Absent/unknown is the permissive default, by design.** A candidate
that never sets this field (every existing test/fixture from Tasks
20-21A, and any future extractor that simply doesn't populate it)
behaves EXACTLY as before this task -- this is an additive, narrowing-
only control, never a new requirement placed on every claim.
"""

from __future__ import annotations

from enum import Enum

from app.evidence_engine.acquisition.routing import KIND_AGNOSTIC_DIMENSIONS_NEVER_REACHABLE_BY_A_TYPED_FACT

SUBJECT_RELATIONSHIP_PRIMARY = "primary"
SUBJECT_RELATIONSHIP_PRODUCT_INTEGRATION = "product_integration"
SUBJECT_RELATIONSHIP_CUSTOMER_OR_PARTNER = "customer_or_partner"
SUBJECT_RELATIONSHIP_UNRELATED_THIRD_PARTY = "unrelated_third_party"

ALLOWED_SUBJECT_RELATIONSHIPS: frozenset[str] = frozenset({
    SUBJECT_RELATIONSHIP_PRIMARY,
    SUBJECT_RELATIONSHIP_PRODUCT_INTEGRATION,
    SUBJECT_RELATIONSHIP_CUSTOMER_OR_PARTNER,
    SUBJECT_RELATIONSHIP_UNRELATED_THIRD_PARTY,
})


class SubjectRelationship(str, Enum):
    """Same four values as `ALLOWED_SUBJECT_RELATIONSHIPS` above, as a
    real Enum -- used only for `providers_live.py`'s own structured-
    output schema (`_CandidateSchema`), so the OpenAI API's own strict
    JSON-schema enum constraint enforces the vocabulary client-side, in
    addition to (never instead of) `sanitize_subject_relationship()`'s
    own deterministic check below."""

    PRIMARY = SUBJECT_RELATIONSHIP_PRIMARY
    PRODUCT_INTEGRATION = SUBJECT_RELATIONSHIP_PRODUCT_INTEGRATION
    CUSTOMER_OR_PARTNER = SUBJECT_RELATIONSHIP_CUSTOMER_OR_PARTNER
    UNRELATED_THIRD_PARTY = SUBJECT_RELATIONSHIP_UNRELATED_THIRD_PARTY


def sanitize_subject_relationship(value: str | None) -> str | None:
    """An out-of-vocabulary value is dropped to `None` (treated as
    unknown/absent), never a rejection reason -- mirrors item 5's own
    "missing remains preferable to invented" philosophy for this field."""
    if value in ALLOWED_SUBJECT_RELATIONSHIPS:
        return value
    return None


def strip_unrelated_third_party_dimensions(criteria: list[str], subject_relationship: str | None) -> list[str]:
    """Only `unrelated_third_party` narrows anything -- every other
    value (including absent/unknown) passes `criteria` through
    unchanged."""
    if subject_relationship != SUBJECT_RELATIONSHIP_UNRELATED_THIRD_PARTY:
        return criteria
    return [c for c in criteria if c not in KIND_AGNOSTIC_DIMENSIONS_NEVER_REACHABLE_BY_A_TYPED_FACT]
