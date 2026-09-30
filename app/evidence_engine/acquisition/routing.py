"""
Deterministic assessment-criteria routing (Task 23, LINEAR_001 remediation
item 4).

**The problem this closes.** `LIVE_EVALUATION_LINEAR_001.md` found the
single highest-impact defect of the first live run was NOT grounding,
NOT source-type classification, NOT the deterministic pillar/gate math --
it was the extractor choosing the wrong `assessment_criteria` tag(s) for
evidence it otherwise extracted, grounded, and typed correctly (a real
$82M Series C / $1.25B valuation funding-round fact tagged only
`commercial_validation`/`growth_trajectory`, never `funding_history` or
`stage_signal`; a founder's Airbnb/Coinbase background tagged only
`leadership_composition`/`public_track_record`, never `founder_relevant_
experience`). Before Task 23, `assessment_criteria` was a pure LLM
proposal, checked only for "at least one dimension this methodology
defines" (`extraction.py::validate_candidate`'s `NO_RECOGNIZED_DIMENSION`
check, Task 20) -- never for whether THIS SPECIFIC fact could plausibly
belong to the tag(s) proposed.

**The fix.** Wherever `structured_fact.kind` already deterministically
implies which dimension(s) can legitimately consume it -- which this
module derives directly from the six pillar modules' OWN `kind ==`/`!=`
checks (grepped, not invented -- see the table below's own per-entry
citation), `assessment_criteria` is INTERSECTED against that allowed set.
Any proposed tag outside it is silently dropped from that one candidate
-- never causing the whole candidate to be rejected, and never adding a
tag the model didn't propose. This is exactly item 4's own "AI may
propose relevant criteria; deterministic software validates/intersects
against the allowed set; impossible cross-pillar routing is rejected or
corrected deterministically."

**Why this is not a second methodology.** Nothing here decides a score,
a label, or an availability status -- every entry in `FACT_KIND_ALLOWED_
CRITERIA` merely restates which dimension(s) the CORRESPONDING PILLAR
FILE ALREADY reads that kind for for. If a pillar file's own kind-check
ever changes, this table must change with it (each entry cites the exact
file/dimension it mirrors) -- it is a restatement of existing
methodology-owned routing, not a new, independent one.

**What this table does NOT cover.** A claim with NO `structured_fact` at
all (Task 23's own item 5 finding: 83% of LINEAR_001's claims had none)
has no kind to route by -- its `assessment_criteria` passes through
unrestricted by this module, governed only by the existing grounding/
vocabulary check plus (new this task) the relevance check in
`relevance.py`. Four dimensions (`product_existence_maturity`,
`differentiation_claim_corroboration`, `technical_depth_signal`,
`defensibility_signal` -- all Product & Technology, Tasks 8-9's own
original design) are themselves NEVER kind-gated by their own pillar
code (they read free-text, corroboration-count-based evidence) -- this
table cannot add a POSITIVE requirement for them, but see `_EXCLUSIVE_
OWNER_KINDS` below for the negative guard this task adds instead
(exactly item 10's own "funding round -> Product Quality... must fail or
be deterministically constrained" case).
"""

from __future__ import annotations

from app.evidence_engine.acquisition.models import ExtractedClaimCandidate

# One entry per structured_fact kind with a real, existing kind-gate in a
# pillar file (or stage.py) -- the dimension name(s) that gate legitimately
# consumes it. Every entry cites exactly where.
FACT_KIND_ALLOWED_CRITERIA: dict[str, frozenset[str]] = {
    # pillars/financial_funding.py::evaluate_funding_history -- the ONLY
    # dimension that ever reads `kind == "funding_round"`.
    "funding_round": frozenset({"funding_history"}),
    # stage.py::resolve_stage -- funding_round_type/founding_year are read
    # ONLY under the `stage_signal` pseudo-dimension; neither is ever read
    # by any pillar's own dimension evaluator.
    "funding_round_type": frozenset({"stage_signal"}),
    "founding_year": frozenset({"stage_signal"}),
    # pillars/financial_funding.py::evaluate_capital_efficiency.
    "capital_efficiency_signal": frozenset({"capital_efficiency"}),
    # pillars/team_leadership.py::evaluate_founder_relevant_experience --
    # also requires an identity-confirmed founder (person_id match), which
    # this module does not itself enforce (that stays the pillar's own
    # job); routing only says WHICH dimension this kind may ever reach.
    "founder_experience": frozenset({"founder_relevant_experience"}),
    # pillars/team_leadership.py::WellBehavedLeadershipCompositionClassifier.
    "leadership_hire": frozenset({"leadership_composition"}),
    "founders_only_confirmed": frozenset({"leadership_composition"}),
    # pillars/team_leadership.py::evaluate_public_track_record.
    "track_record": frozenset({"public_track_record"}),
    # pillars/execution_momentum.py::evaluate_shipping_velocity (via
    # `_resolve_current_release_status`'s own named-release supersession).
    "product_release": frozenset({"shipping_velocity"}),
    # pillars/execution_momentum.py::evaluate_gtm_motion_evidence.
    "gtm_evidence": frozenset({"gtm_motion_evidence"}),
    # pillars/market_opportunity.py::evaluate_market_definition_size.
    "market_size_usd": frozenset({"market_definition_size"}),
    # pillars/market_opportunity.py::evaluate_market_growth_signal.
    "category_growth_rate_pct": frozenset({"market_growth_signal"}),
    # pillars/market_opportunity.py::evaluate_timing_catalyst -- one of
    # several signals that dimension reads; still the only dimension this
    # kind ever legitimately reaches.
    "catalyst_name": frozenset({"timing_catalyst"}),
    # pillars/market_opportunity.py::WellBehavedCompetitiveLandscapeClassifier.
    "competitive_structure": frozenset({"competitive_landscape_position"}),
    # pillars/commercial_traction.py::evaluate_customer_base_breadth.
    "customer_band": frozenset({"customer_base_breadth"}),
    # pillars/commercial_traction.py::evaluate_commercial_validation.
    "commercial_commitment": frozenset({"commercial_validation"}),
    # pillars/commercial_traction.py::evaluate_retention_renewal_signal.
    "retention_signal": frozenset({"retention_renewal_signal"}),
    # pillars/commercial_traction.py::evaluate_disclosed_scale /
    # evaluate_growth_trajectory -- Commercial Traction OWNS this kind
    # (spec Part 3.1, Task 15). `revenue_disclosure` is deliberately NOT
    # in this set: Financial & Funding Signals may only ever reference a
    # revenue `traction_metric` claim through claim_identity.py::
    # finalize_claim()'s own existing, deterministic, metric=="revenue"
    # gated auto-tag rule (Task 17) -- never through a tag the LLM
    # proposes itself for this kind. Item 3's own "preserve the existing
    # canonical ownership rule... do not regress Task 17" is enforced
    # structurally here by simple omission, not by a new check: even if a
    # candidate proposes `revenue_disclosure` for a `traction_metric` fact,
    # `route_assessment_criteria()` below strips it, and `finalize_claim()`
    # re-adds it ONLY when its own real gate (metric == "revenue") passes.
    "traction_metric": frozenset({"disclosed_scale", "growth_trajectory"}),
}

# Item 4's own "impossible cross-pillar routing" guard for the FOUR
# dimensions that have NO positive kind-gate of their own (Product &
# Technology's original, free-text/corroboration-count design, Tasks
# 8-9 -- unchanged, not touched by this task). These dimensions cannot
# be POSITIVELY required to see a specific kind, but a claim whose kind
# is DEFINITELY, deterministically owned by a DIFFERENT dimension family
# (i.e. is a key in `FACT_KIND_ALLOWED_CRITERIA` above) must never ALSO
# be allowed to count toward one of these -- this is exactly item 10's
# adversarial case ("funding round -> Product Quality... must fail or be
# deterministically constrained"), which no POSITIVE kind-gate could ever
# catch since these dimensions read free text by design.
KIND_AGNOSTIC_DIMENSIONS_NEVER_REACHABLE_BY_A_TYPED_FACT: frozenset[str] = frozenset({
    "product_existence_maturity",
    "differentiation_claim_corroboration",
    "technical_depth_signal",
    "defensibility_signal",
})


def route_assessment_criteria(candidate: ExtractedClaimCandidate) -> list[str]:
    """The one function `extraction.py` calls on every accepted
    candidate, AFTER grounding/vocabulary validation, BEFORE it becomes
    a `Claim`. Returns a (possibly narrower, never wider) `assessment_
    criteria` list:

    - No `structured_fact`, or a `kind` not in `FACT_KIND_ALLOWED_
      CRITERIA` (including `team_identity`/`strategic_statement`, which
      have no positive dimension gate of their own): unchanged, except
      the negative Product & Technology guard below never applies either
      (there is no kind to compare against).
    - A recognized, kind-gated `kind`: every proposed tag is kept ONLY if
      it is in that kind's own allowed set.

    Never adds a tag the model did not propose; never rejects the whole
    candidate (a candidate that loses every one of its tags this way
    still exists -- `extraction.py`'s own downstream check, unchanged,
    is what would eventually treat a criteria-less candidate as
    unusable, exactly the same way a candidate with zero recognized
    dimensions from the start already was)."""
    criteria = list(candidate.assessment_criteria)
    fact = candidate.structured_fact or {}
    kind = fact.get("kind")

    allowed = FACT_KIND_ALLOWED_CRITERIA.get(kind)
    if allowed is not None:
        return [c for c in criteria if c in allowed]

    # No positive gate for this kind (or no kind at all) -- still apply
    # the negative guard: a kind DEFINITELY owned by another dimension
    # family (i.e. present as a key above, just not this specific kind
    # because we already returned above when it matched) never applies
    # here since `allowed is None` means `kind` itself is not one of the
    # recognized, gated kinds at all -- so nothing further to strip.
    return criteria


def strip_kind_agnostic_dimensions_for_owned_kind(criteria: list[str], kind: str | None) -> list[str]:
    """A second, explicit negative pass -- kept separate from `route_
    assessment_criteria()` above for clarity, though in practice a
    `kind` that IS a key in `FACT_KIND_ALLOWED_CRITERIA` has ALREADY had
    every non-allowed tag (including any of the four kind-agnostic
    dimensions) stripped by the intersection above. This function exists
    so the guard is stated once, explicitly, by name, rather than only
    implied by the intersection -- and so a future kind added to `FACT_
    KIND_ALLOWED_CRITERIA` with an accidentally-too-permissive allowed
    set still cannot leak into one of the four kind-agnostic dimensions."""
    if kind is None or kind not in FACT_KIND_ALLOWED_CRITERIA:
        return criteria
    return [c for c in criteria if c not in KIND_AGNOSTIC_DIMENSIONS_NEVER_REACHABLE_BY_A_TYPED_FACT]
