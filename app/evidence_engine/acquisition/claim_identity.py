"""
Canonical claim identity (Task 20 item 11) and the deterministic
cross-pillar revenue-reuse rule (item 14). Both are pure functions over
an `ExtractedClaimCandidate` plus the `company_ref`/source it resolved
against -- no model call, no randomness.

**`claim_id` vs. `independence_group_id` -- two different identities,
per spec Part 2.1 (unchanged, not reinterpreted here):**

  - `claim_id` is inherently per-SOURCE ("a content hash of the
    normalized claim text + source URL," spec's own words) -- the SAME
    real-world fact reported by five different outlets legitimately
    produces five different `claim_id`s, one per outlet, because each
    is a genuinely separate ledger entry with its own provenance.
  - `independence_group_id` is what item 11 is actually asking this
    module to get right: a canonical key computed from the FACT itself
    (company + fact type + normalized identifying sub-fields), NEVER
    from the source URL (item 11's own explicit "do not use source URL
    alone as claim identity"). Five claims about one real funding round,
    from five different `claim_id`s/URLs, must all resolve to the SAME
    `independence_group_id` -- this is what makes the ALREADY-EXISTING,
    unmodified `ledger.py::resolve_dimension_evidence()` (declared-group
    dedup) and `provenance.py::verify_independence()` (content-based
    safety net) work correctly on freshly-acquired evidence without any
    new deduplication code (item 12's own "reuse the existing
    provenance/independence logic rather than inventing a parallel
    system").
"""

from __future__ import annotations

import hashlib
import re
from datetime import date

from app.evidence_engine.acquisition.models import ExtractedClaimCandidate, RetrievedSource
from app.evidence_engine.acquisition.person_identity import normalize_person_name_to_id
from app.evidence_engine.models import Claim

_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9\s]")


def _normalize_text(text: str) -> str:
    lowered = text.lower()
    stripped = _NON_ALNUM.sub("", lowered)
    return _WHITESPACE.sub(" ", stripped).strip()


def _hash(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def compute_claim_id(claim_text: str, source_url: str) -> str:
    """Spec Part 2.1's own definition, literally: a content hash of the
    normalized claim text + source URL. Re-running acquisition against an
    unchanged source and an unchanged extracted fact reproduces the exact
    same `claim_id`, never a new duplicate row."""
    return _hash(_normalize_text(claim_text), source_url)


# Per-`structured_fact.kind` identity key extractors -- each returns the
# tuple of sub-fields that, together with company_ref and kind, uniquely
# identify the underlying FACT (not the source). Deliberately explicit,
# per-kind, rather than one generic "hash the whole dict" rule -- a
# generic hash would treat two claims differing only in `amount` (the
# actual point of disagreement a contradiction check needs to compare) as
# different facts entirely, defeating both deduplication and contradiction
# detection. Extending this table is the correct way to add a new kind,
# not a fallback path.
IDENTITY_KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "traction_metric": ("metric", "period_date"),
    "funding_round": ("round_date", "financing_type"),
    "product_release": ("named_entity",),
    # Deliberately NO named_entity sub-field: unlike a release or a named
    # commercial commitment (genuinely different facts per distinct
    # name), a company generally has only ONE "current customer base
    # characterization" at a time -- two disclosures with DIFFERENT
    # free-text named_entity values (e.g. "thousands of customers" vs.
    # "fewer than 100 confirmed customers") must still land in the SAME
    # group so `contradiction.py` can compare them; keying on the
    # free-text field itself would let two directly conflicting
    # disclosures silently avoid ever being compared.
    "customer_band": (),
    "commercial_commitment": ("named_entity",),
    "capital_efficiency_signal": ("metric",),
    "team_identity": ("person_id",),
    "founder_experience": ("person_id", "named_entity"),
    "track_record": ("person_id", "named_entity"),
    "gtm_evidence": ("named_entity",),
    "market_size_usd": (),
    "category_growth_rate_pct": (),
    "catalyst_name": (),
    "competitive_structure": (),
    "strategic_statement": ("topic",),
    "funding_round_type": (),
    "founding_year": (),
    # Task 23 (LINEAR_001 remediation, item 5's own "inspect why structured-
    # fact population is low"): these three kinds were already read by
    # `pillars/team_leadership.py`/`pillars/commercial_traction.py` --
    # `leadership_hire`/`founders_only_confirmed` gate Leadership
    # Composition, `retention_signal` gates Retention/Renewal Signal --
    # but were missing from this table. Since `extraction.py::KNOWN_
    # FACT_KINDS` is built directly from this table's own keys (Task 21),
    # this gap meant a real, legitimately-typed candidate of one of these
    # three kinds would have been rejected outright by `validate_
    # candidate()`'s `INVALID_FACT_KIND` check -- a genuine bug, not a
    # hypothetical one, caught by re-deriving this table from the pillars'
    # own actual `kind ==`/`!=` checks rather than trusting it was already
    # complete.
    "leadership_hire": ("named_entity",),
    "founders_only_confirmed": (),
    "retention_signal": (),
}


def compute_independence_group_id(candidate: ExtractedClaimCandidate, company_ref: str) -> str:
    """The canonical fact-identity key (module docstring). Falls back to
    a normalized-text key only when no `structured_fact` exists at all
    (a genuinely free-form claim) -- this fallback is deliberately the
    LEAST preferred path, since text-based matching is exactly what
    `provenance.py`'s own content-similarity safety net already exists to
    catch; a real `structured_fact` gives an exact, not approximate,
    match whenever one is available."""
    fact = candidate.structured_fact or {}
    kind = fact.get("kind")
    if kind and kind in IDENTITY_KEY_FIELDS:
        key_fields = IDENTITY_KEY_FIELDS[kind]
        sub_values = tuple(_normalize_text(fact.get(f, "")) for f in key_fields)
        return _hash(company_ref, kind, *sub_values)
    return _hash(company_ref, "text", _normalize_text(candidate.claim_text))


_PERSON_IDENTITY_RELEVANT_KINDS: frozenset[str] = frozenset({
    "team_identity", "founder_experience", "track_record", "leadership_hire",
})


def backfill_person_id(fact: dict[str, str]) -> dict[str, str]:
    """Task 23, LINEAR_001 remediation item 6: `person_id` is never
    something the extractor is trusted to invent (`person_identity.py`'s
    own module docstring) -- when a person-identity-relevant fact
    carries a `named_entity` (the person's own name, which the
    extractor already reliably supplies) but no `person_id`, this
    deterministically derives one from that name and backfills it,
    NEVER overwriting a `person_id` the model did supply. Returns the
    SAME dict, unchanged, when no backfill applies (no kind match, no
    named_entity, already has a person_id, or the name is too vague to
    safely resolve -- `normalize_person_name_to_id()` returning `None`
    is the fail-closed outcome for that last case, left as-is rather
    than injecting a `None`/empty value).

    Made public (Task 29 item 2/3): `acquisition/canonicalization.py`
    calls this directly, reusing the exact same derivation, so a
    person-identity-relevant candidate's `structured_fact` is already
    canonical BEFORE `routing.py::route_candidate()`'s own applicability
    check runs -- fixing the `LIVE_EVALUATION_FISH_AUDIO_002.md` §5
    ordering defect (routing ran on the pre-backfill fact, permanently
    stripping a dimension a moments-later-backfilled fact would have
    kept). This function's own behavior and signature are unchanged;
    only its name is now public, and `finalize_claim()` below still
    calls it -- now a safe, idempotent no-op in the normal, routed path,
    and still the only backfill path for any candidate that reaches
    `finalize_claim()` without having gone through the acquisition
    pipeline's own sanitization step first (e.g. a hand-built fixture)."""
    if fact.get("kind") not in _PERSON_IDENTITY_RELEVANT_KINDS:
        return fact
    if fact.get("person_id"):
        return fact
    named_entity = fact.get("named_entity")
    if not named_entity:
        return fact
    person_id = normalize_person_name_to_id(named_entity)
    if person_id is None:
        return fact
    return {**fact, "person_id": person_id}


def finalize_claim(
    candidate: ExtractedClaimCandidate, source: RetrievedSource, company_ref: str,
) -> Claim:
    """Builds the real, canonical `Claim` from an already-grounding-
    validated candidate (`extraction.py::validate_candidate` must have
    already accepted it -- this function does not re-validate). Applies
    two deterministic, additive rules before construction:

    1. (Task 17, spec Part 3.1, unchanged) a specifically-revenue
       `traction_metric` claim tagged for Commercial Traction's own
       dimensions is ALSO tagged `revenue_disclosure`, so Financial &
       Funding Signals' Revenue Disclosure references, rather than
       re-extracts, the exact same claim.
    2. (Task 23 item 6) `backfill_person_id()` above -- applied BEFORE
       `compute_independence_group_id()` runs, so a backfilled
       `person_id` actually participates in identity-group assignment,
       and persisted onto the final `Claim.structured_fact` so `pillars/
       team_leadership.py::_confirmed_person_ids()` can read it back."""
    assessment_criteria = list(candidate.assessment_criteria)
    fact = backfill_person_id(candidate.structured_fact or {}) if candidate.structured_fact else None
    if candidate.structured_fact is not None:
        candidate = candidate.model_copy(update={"structured_fact": fact})
    if (
        fact
        and fact.get("kind") == "traction_metric"
        and fact.get("metric") == "revenue"
        and "revenue_disclosure" not in assessment_criteria
    ):
        assessment_criteria.append("revenue_disclosure")

    claim_id = compute_claim_id(candidate.claim_text, source.url)
    independence_group_id = compute_independence_group_id(candidate, company_ref)

    return Claim(
        claim_id=claim_id,
        company_ref=company_ref,
        claim_text=candidate.claim_text,
        subject_entity=candidate.subject_entity,
        source_url=source.url,
        source_publisher=source.publisher,
        source_type=source.source_type,
        published_at=source.published_at,
        retrieved_at=source.retrieved_at,
        support_status=candidate.support_status,
        excerpt=candidate.excerpt,
        assessment_criteria=assessment_criteria,
        independence_group_id=independence_group_id,
        structured_fact=candidate.structured_fact,
    )
