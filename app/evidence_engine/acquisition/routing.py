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

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from app.evidence_engine.acquisition.models import ExtractedClaimCandidate
from app.evidence_engine.pillars.financial_funding import funding_round_fields_are_sufficient
from app.evidence_engine.stage import founding_year_fields_are_sufficient, funding_round_type_fields_are_sufficient

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


# =============================================================================
# Task 25 (LINEAR_002 remediation): eligibility vs. applicability, and an
# explicit, observable routing outcome per candidate.
#
# **Eligibility vs. applicability -- two different questions, item 2's own
# explicit instruction not to conflate them.** `FACT_KIND_ALLOWED_CRITERIA`
# above answers ELIGIBILITY: which dimension(s) MAY LEGALLY ever consume a
# given fact kind, a property of the KIND alone. It says nothing about
# whether ONE SPECIFIC fact -- this exact set of field values -- actually
# has enough real structure to be USED by that dimension's own evidence
# contract. That second question is APPLICABILITY, and `LIVE_EVALUATION_
# LINEAR_002.md` found the concrete cost of never asking it: a `funding_
# round` fact with no `financing_type`/`round_date` (a mislabeled valuation,
# not a real round) and a `founding_year` fact using `"amount"` instead of
# the `"value"` field `stage.py::resolve_stage()` actually reads BOTH had
# proposed criteria that Task 23's own eligibility-only intersection
# correctly stripped as illegitimate -- and nothing then checked whether
# the RESULT was still usable, so both silently reached the ledger with
# `assessment_criteria == []`, permanently un-citable by anything.
#
# **`_APPLICABILITY_CHECKS`.** One entry per kind where LINEAR_002 actually
# found (or this task's own code-reading found) a real gap between "kind
# matches" and "the specific fact's fields are sufficient." Each check
# reuses the EXACT validation the real consumer already performs --
# `pillars/financial_funding.py::funding_round_fields_are_sufficient()`
# and `stage.py::funding_round_type_fields_are_sufficient()`/`founding_
# year_fields_are_sufficient()` were themselves split out of (respectively)
# `parse_funding_round()` and `resolve_stage()` specifically so this module
# could call the SAME check rather than a second, driftable one. A kind
# with NO entry here defaults to "fully applicable to everything it is
# eligible for" -- Task 23's own original assumption, left unchanged for
# the 15 kinds this task found no evidence of a real problem with; this is
# a deliberately narrow, evidence-driven extension, not an attempt to
# harden every kind speculatively.
_APPLICABILITY_CHECKS: dict[str, Callable[[dict], bool]] = {
    "funding_round": funding_round_fields_are_sufficient,
    "funding_round_type": funding_round_type_fields_are_sufficient,
    "founding_year": founding_year_fields_are_sufficient,
}


def _applicable_criteria(kind: str, fact: dict[str, str], eligible: frozenset[str]) -> frozenset[str]:
    check = _APPLICABILITY_CHECKS.get(kind)
    if check is None or check(fact):
        return eligible
    return frozenset()


# Recognized kinds (real entries in `claim_identity.py::IDENTITY_KEY_
# FIELDS`, so `extraction.py`'s own `INVALID_FACT_KIND` check already
# accepts them) that have NO scored-dimension consumer BY DESIGN, not by
# omission -- `team_identity` feeds `pillars/team_leadership.py::_
# confirmed_person_ids()`'s own identity-resolution gate (never a scored
# dimension itself); `strategic_statement` feeds `claim_identity.py`'s own
# grouping/dedup for Strategic Consistency, which reads `evidence.disputed`
# directly (Task 16) rather than this kind's own fields. Neither is ever
# read by a `WellBehaved*Classifier`'s own kind check -- confirmed by the
# same grep-derived process `FACT_KIND_ALLOWED_CRITERIA` itself came from,
# not assumed.
CONTEXT_ONLY_KINDS: frozenset[str] = frozenset({"team_identity", "strategic_statement"})


class RoutingStatus(str, Enum):
    """The routing OUTCOME for one candidate, item 6's own required
    vocabulary. Never affects scoring by itself -- this is an
    observability/audit concept (item 9), read by `pipeline.py`/a future
    live-run report, never by any pillar evaluator."""

    ROUTED = "routed"
    CONTEXT_ONLY = "context_only"
    UNROUTED_INSUFFICIENT_STRUCTURE = "unrouted_insufficient_structure"
    UNROUTED_NO_METHODOLOGY_CONSUMER = "unrouted_no_methodology_consumer"
    REJECTED_INVALID_ROUTING = "rejected_invalid_routing"


@dataclass(frozen=True)
class RoutingResult:
    status: RoutingStatus
    reason: str
    fact_kind: str | None
    proposed_criteria: tuple[str, ...]
    eligible_criteria: tuple[str, ...]
    final_criteria: tuple[str, ...]
    removed_criteria: tuple[str, ...]
    added_criteria: tuple[str, ...]


def route_candidate(candidate: ExtractedClaimCandidate) -> RoutingResult:
    """The full, observable routing decision for one candidate (item
    3/9's own combined ask). Preserves every invariant item 11 lists:

    - **Invalid model routing cannot broaden evidence** -- `final_
      criteria` is always a subset of `applicable` (itself a subset of
      `eligible`); a proposal naming a dimension outside `eligible` can
      never appear in `final_criteria`, regardless of this function's
      own deterministic-fallback branch.
    - **A bad/empty proposal does not destroy deterministically
      applicable evidence** -- when the model's own proposal has zero
      overlap with what the fact's fields actually support, but the
      fact IS sufficiently structured, this function still returns
      `status=ROUTED` with `final_criteria=applicable` (the deterministic-
      fallback branch, `added_criteria` non-empty) -- exactly item 3's
      "AI proposes, deterministic software decides applicability" and
      item 10's authority-boundary requirement, together.
    - **Context remains context** -- `team_identity`/`strategic_
      statement` never enter the eligibility/applicability machinery at
      all; `status=CONTEXT_ONLY`, criteria pass through unchanged, no
      scoring implication whatsoever.
    - **Missing structure remains missing** -- `_applicable_criteria()`
      never invents a field; a fact missing what its own real consumer
      requires is `UNROUTED_INSUFFICIENT_STRUCTURE`, full stop, exactly
      LINEAR_002's own two actual claims.

    Never mutates `candidate`; `extraction.py` applies `final_criteria`
    itself."""
    proposed = tuple(candidate.assessment_criteria)
    fact = candidate.structured_fact

    if not fact:
        return RoutingResult(
            status=RoutingStatus.ROUTED,
            reason="no structured_fact -- kind-based routing does not apply; criteria pass through as proposed",
            fact_kind=None, proposed_criteria=proposed, eligible_criteria=(),
            final_criteria=proposed, removed_criteria=(), added_criteria=(),
        )

    kind = fact.get("kind")
    if kind not in FACT_KIND_ALLOWED_CRITERIA:
        if kind in CONTEXT_ONLY_KINDS:
            return RoutingResult(
                status=RoutingStatus.CONTEXT_ONLY,
                reason=f"kind={kind!r} is identity/context data by design, never a scored dimension",
                fact_kind=kind, proposed_criteria=proposed, eligible_criteria=(),
                final_criteria=proposed, removed_criteria=(), added_criteria=(),
            )
        return RoutingResult(
            status=RoutingStatus.UNROUTED_NO_METHODOLOGY_CONSUMER,
            reason=f"no pillar or stage resolver in this methodology reads kind={kind!r}",
            fact_kind=kind, proposed_criteria=proposed, eligible_criteria=(),
            final_criteria=(), removed_criteria=proposed, added_criteria=(),
        )

    eligible = FACT_KIND_ALLOWED_CRITERIA[kind]
    applicable = _applicable_criteria(kind, fact, eligible)

    from_proposal = tuple(c for c in proposed if c in applicable)
    if from_proposal:
        removed = tuple(c for c in proposed if c not in from_proposal)
        return RoutingResult(
            status=RoutingStatus.ROUTED,
            reason=f"kind={kind!r}: the model's own proposal already named an applicable dimension",
            fact_kind=kind, proposed_criteria=proposed, eligible_criteria=tuple(sorted(eligible)),
            final_criteria=from_proposal, removed_criteria=removed, added_criteria=(),
        )

    # The deterministic FALLBACK (adding a tag the model never proposed
    # at all) is deliberately restricted to kinds with an EXPLICIT,
    # evidence-verified entry in `_APPLICABILITY_CHECKS` -- item 3's own
    # "route to those criteria only when justified." For the other 15
    # recognized kinds, `applicable` defaults to `eligible` so a
    # CORRECTLY-proposed tag still routes normally (the branch above),
    # but this function does not invent a NEW tag this task never
    # verified real sufficiency for -- e.g. a `founder_experience` fact
    # with the right `kind` but no `value` field would otherwise be
    # "routed" to `founder_relevant_experience` even though that
    # dimension's own classifier would then find nothing usable in it,
    # a misleading (if harmless) routing_decision this restriction avoids.
    if applicable and kind in _APPLICABILITY_CHECKS:
        final = tuple(sorted(applicable))
        return RoutingResult(
            status=RoutingStatus.ROUTED,
            reason=(
                f"kind={kind!r}: the model's proposal {list(proposed)!r} named no applicable dimension, "
                f"but the fact's own fields are verified-sufficient -- routed deterministically to {list(final)!r}"
            ),
            fact_kind=kind, proposed_criteria=proposed, eligible_criteria=tuple(sorted(eligible)),
            final_criteria=final, removed_criteria=proposed, added_criteria=final,
        )

    if set(proposed) & eligible:
        status = RoutingStatus.UNROUTED_INSUFFICIENT_STRUCTURE
        reason = (
            f"kind={kind!r}: proposal {list(proposed)!r} named an eligible dimension, but the fact's own "
            f"fields do not meet that dimension's evidence contract"
        )
    else:
        status = RoutingStatus.REJECTED_INVALID_ROUTING
        reason = (
            f"kind={kind!r}: proposal {list(proposed)!r} named no dimension this kind can ever reach "
            f"(eligible: {sorted(eligible)!r}), and the fact's own fields are also insufficient"
        )
    return RoutingResult(
        status=status, reason=reason, fact_kind=kind, proposed_criteria=proposed,
        eligible_criteria=tuple(sorted(eligible)), final_criteria=(), removed_criteria=proposed, added_criteria=(),
    )
