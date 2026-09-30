"""
The canonical `fact_kind` extraction contract (Task 27, LIVE_EVALUATION_
COHORT_001.md remediation).

**The problem this closes.** The cohort's own central finding (Finding
S1): claims were increasingly grounded, correctly typed, and correctly
ROUTED (Task 25) to a legitimate dimension -- and still could not score,
because their `structured_fact`'s own field VALUES did not match the
exact vocabulary/shape each dimension's real classifier requires
(`value` populated with a free-text metric instead of a categorical
label; `financing_type` populated with a round LABEL like "Seed" instead
of the legal financing STRUCTURE `"equity"`; `metric` populated as
`"annual revenue"` instead of the recognized `"revenue"`; `value_type`
never populated at all). Task 25 fixed this for exactly the 3 kinds
LINEAR_002 evidenced a problem for (`funding_round`, `funding_round_
type`, `founding_year`); this module extends the SAME verified-sufficiency
concept to every kind-gated fact kind this engine has, derived directly
from re-reading every pillar's own classifier code (cited per entry, not
invented) -- the cohort's own explicit instruction: "Do not infer the
contracts from documentation alone. Read the actual classifier/evaluator
code."

**One canonical place, not seventeen scattered ones.** Every categorical
vocabulary a classifier checks by exact string equality is named here
ONCE, as a real `Enum`, and referenced by both the extraction schema
(`providers_live.py`, where practical -- see §"Schema-level vs.
deterministic-only enforcement" below) and the sufficiency checks
`routing.py::_APPLICABILITY_CHECKS` uses to decide whether a candidate's
own fields justify a route. This is a deliberate design choice over
adding one more small `*_fields_are_sufficient()` function to each of
five different pillar files (Task 25's own pattern, which fit its
narrower 3-kind scope) -- for the full 15-kind-gated vocabulary, one
well-organized module is more maintainable than five files each growing
a handful of new, related-but-scattered functions. Task 25's own three
functions (`pillars/financial_funding.py::funding_round_fields_are_
sufficient()`, `stage.py::funding_round_type_fields_are_sufficient()`/
`founding_year_fields_are_sufficient()`) are imported and reused here
directly, not re-derived, for the three kinds they already cover
correctly.

**Schema-level vs. deterministic-only enforcement.** Some fields mean
exactly one thing regardless of which fact kind carries them
(`financing_type`, `value_type`) -- these ARE enforced as real Pydantic/
OpenAI-structured-output enums in `providers_live.py::_StructuredFact
Schema`, so the model cannot even PROPOSE an out-of-vocabulary value for
them. Others (`value`, `metric`, `status`) are used by MULTIPLE kinds
with DIFFERENT, kind-specific vocabularies under the SAME field name
(`customer_band.value` means SMALL/MODERATE/LARGE; `founder_experience.
value` means ADJACENT/DIRECT; `capital_efficiency_signal.value` and
`retention_signal.value` both mean WEAK/MODERATE/STRONG but for
different dimensions) -- OpenAI's structured-output schema has no
built-in way to make one field's enum depend on a SIBLING field's own
value without a full discriminated-union schema per kind (a materially
larger, harder-to-maintain schema change this task judges not worth it
for a field-level distinction that this module's own DETERMINISTIC
check -- reading `kind` first, then validating the RIGHT vocabulary --
already enforces just as strictly, just one step later, exactly where
`routing.py`'s existing applicability mechanism (Task 25) already lives.
Documented here as the deliberate "smallest maintainable typed design"
tradeoff item 10 asks for, not an oversight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from app.evidence_engine.pillars.financial_funding import funding_round_fields_are_sufficient
from app.evidence_engine.stage import founding_year_fields_are_sufficient, funding_round_type_fields_are_sufficient


# =============================================================================
# Canonical categorical vocabularies -- one Enum per real classifier check,
# named exactly once. Every entry below cites the real classifier it mirrors.
# =============================================================================

class FinancingLegalType(str, Enum):
    """Item 4's own explicit distinction: the LEGAL STRUCTURE of a
    financing event -- NOT the round/stage label (that is `RoundLabel`
    below, a completely different field on a completely different kind,
    `funding_round_type`). `pillars/financial_funding.py::funding_
    round_fields_are_sufficient()` only ever counts `EQUITY` toward
    Funding History (`parameters.py::FUNDING_HISTORY_COUNTED_FINANCING_
    TYPES = {"equity"}`) -- the other values are real, legitimate
    financing types this engine's own `Claim` model can represent and
    retain, just never summed by this one dimension (unchanged Task 17
    methodology, restated here as an explicit vocabulary, not altered)."""

    EQUITY = "equity"
    DEBT = "debt"
    GRANT = "grant"
    SECONDARY = "secondary"
    TENDER_OFFER = "tender_offer"


class FundingRoundStatus(str, Enum):
    """`funding_round_fields_are_sufficient()`'s own `status != "completed"`
    check -- "announced" (not yet closed) financing is a real, distinct,
    legitimately-representable state that simply never counts toward a
    completed round's total (item 7's own "announced... is explicitly
    distinct")."""

    COMPLETED = "completed"
    ANNOUNCED = "announced"


class TractionMetricType(str, Enum):
    """`pillars/commercial_traction.py::_parse_scale_point()`'s own
    `metric not in P.TRACTION_MONEY_METRICS and metric not in P.
    TRACTION_COUNT_METRICS` check -- the exact 6-value vocabulary that
    module's own `parameters.py::TRACTION_MONEY_METRICS`/`TRACTION_
    COUNT_METRICS` define, restated here as a real enum instead of a
    free-text field the model could paraphrase (the cohort's own
    repeated "annual revenue" vs. "revenue" mismatch)."""

    REVENUE = "revenue"
    ARR = "arr"
    GMV = "gmv"
    BOOKINGS = "bookings"
    ACTIVE_USERS = "active_users"
    PAYING_CUSTOMERS = "paying_customers"


class TractionValueType(str, Enum):
    """`_parse_scale_point()`'s own `fact.get("value_type") != "actual"`
    check -- never one confirmed-actual figure paired with a projection/
    guidance figure (spec Part 3.3's own instruction)."""

    ACTUAL = "actual"
    PROJECTION = "projection"


class CustomerBandSize(str, Enum):
    """`WellBehavedCustomerBaseBreadthClassifier`'s own `value in
    ("SMALL", "MODERATE", "LARGE")` check."""

    SMALL = "SMALL"
    MODERATE = "MODERATE"
    LARGE = "LARGE"


class FounderExperienceRelevance(str, Enum):
    """`WellBehavedFounderExperienceClassifier`'s own `value in
    ("ADJACENT", "DIRECT")` check."""

    ADJACENT = "ADJACENT"
    DIRECT = "DIRECT"


class TrackRecordType(str, Enum):
    """`WellBehavedPublicTrackRecordClassifier`'s own `value ==
    "PRIOR_EXIT"` / `value == "PRIOR_VENTURE_ROLE"` checks."""

    PRIOR_EXIT = "PRIOR_EXIT"
    PRIOR_VENTURE_ROLE = "PRIOR_VENTURE_ROLE"


class StrengthLabel(str, Enum):
    """`WellBehavedRetentionRenewalClassifier` (`retention_signal`) AND
    `WellBehavedCapitalEfficiencyClassifier` (`capital_efficiency_
    signal`) both check `value in ("WEAK", "MODERATE", "STRONG")` --
    the identical 3-tier vocabulary, reused as one Enum here since the
    STRINGS are identical, even though the two kinds feed two
    semantically independent dimensions (Commercial Traction's Retention
    vs. Financial & Funding's Capital Efficiency) -- never conflated
    downstream, since routing (Task 25) already keeps each kind's own
    eligible dimension separate."""

    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"


class CompetitiveStructureType(str, Enum):
    """`WellBehavedCompetitiveLandscapeClassifier`'s own `value ==
    "fragmented"` / `value == "concentrated"` checks."""

    FRAGMENTED = "fragmented"
    CONCENTRATED = "concentrated"


class ProductReleaseStatus(str, Enum):
    """`pillars/execution_momentum.py::_launched_releases()`'s own
    `(c.structured_fact or {}).get("status") == "launched"` check --
    ONLY "launched" ever scores; the other values are real, legitimately
    representable states (module docstring's own "preserve announced ->
    launched... never upgrade") this engine's own supersession logic
    (`_resolve_current_release_status()`) depends on being able to see,
    not merely a closed set the classifier itself enforces string-for-
    string beyond the one value that counts."""

    ANNOUNCED = "announced"
    LAUNCHED = "launched"
    BETA = "beta"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


# =============================================================================
# The canonical per-kind contract.
# =============================================================================

@dataclass(frozen=True)
class FactKindContract:
    kind: str
    consumer_dimensions: frozenset[str]
    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    categorical_fields: dict[str, tuple[str, ...]] = field(default_factory=dict)
    numeric_fields: tuple[str, ...] = ()
    date_fields: tuple[str, ...] = ()
    context_only: bool = False
    notes: str = ""


def _numeric_ok(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        float(raw)
    except (TypeError, ValueError):
        return False
    return True


def _int_ok(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        int(raw)
    except (TypeError, ValueError):
        return False
    return True


def _date_ok(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        date.fromisoformat(raw)
    except (TypeError, ValueError):
        return False
    return True


# --- Funding (item 4) --------------------------------------------------------

FUNDING_ROUND_CONTRACT = FactKindContract(
    kind="funding_round",
    consumer_dimensions=frozenset({"funding_history"}),
    required_fields=("financing_type", "status", "currency", "amount", "round_date"),
    optional_fields=("named_entity", "period_date"),
    categorical_fields={
        "financing_type": tuple(v.value for v in FinancingLegalType),
        "status": tuple(v.value for v in FundingRoundStatus),
        "currency": ("USD",),  # no FX normalization exists (Task 15's own documented limitation)
    },
    numeric_fields=("amount",),
    date_fields=("round_date",),
    notes=(
        "A FINANCING EVENT: the legal structure + amount raised. Only counted "
        "toward funding_history when financing_type == 'equity' AND status == "
        "'completed' (pillars/financial_funding.py::funding_round_fields_are_"
        "sufficient(), unchanged, reused directly here)."
    ),
)

FUNDING_ROUND_TYPE_CONTRACT = FactKindContract(
    kind="funding_round_type",
    consumer_dimensions=frozenset({"stage_signal"}),
    required_fields=("value",),
    optional_fields=("named_entity",),
    notes=(
        "A STAGE/ROUND LABEL signal for stage resolution -- deliberately a "
        "DIFFERENT kind from funding_round (item 4's own explicit 'do not "
        "allow financing_type, round label, and stage label to be "
        "interchangeable strings'). `value` is free text, keyword-matched by "
        "stage.py::map_round_type() (e.g. 'Series C', 'seed round') -- not a "
        "strict enum, since the real consumer itself is substring-based, not "
        "exact-match. If a source states BOTH an amount and a round label "
        "(e.g. '$52M Series B'), the extractor should propose TWO separate "
        "candidates from the same excerpt -- one funding_round (amount), one "
        "funding_round_type (label) -- never conflate the two into one kind's "
        "own fields (the cohort's own Fish Audio finding: financing_type "
        "populated with 'Seed', a round label, instead of 'equity')."
    ),
)

FOUNDING_YEAR_CONTRACT = FactKindContract(
    kind="founding_year",
    consumer_dimensions=frozenset({"stage_signal"}),
    required_fields=("value",),
    optional_fields=("named_entity",),
    notes="stage.py::resolve_stage() reads structured_fact['value'] specifically -- NOT 'amount'.",
)

CAPITAL_EFFICIENCY_SIGNAL_CONTRACT = FactKindContract(
    kind="capital_efficiency_signal",
    consumer_dimensions=frozenset({"capital_efficiency"}),
    required_fields=("value",),
    optional_fields=("metric",),  # "metric" here is a free-text identity-grouping field only (claim_identity.py), never vocabulary-constrained
    categorical_fields={"value": tuple(v.value for v in StrengthLabel)},
    notes="Never inferred from company age, funding amount, headcount, revenue, customer count, or valuation (item 9's own exclusion list, unchanged).",
)

# --- Team (item 6) ------------------------------------------------------------

TEAM_IDENTITY_CONTRACT = FactKindContract(
    kind="team_identity",
    consumer_dimensions=frozenset(),  # context-only, feeds identity resolution, never a scored dimension
    required_fields=("person_id", "role"),
    optional_fields=("named_entity",),
    context_only=True,
    notes=(
        "`role` gates `pillars/team_leadership.py::_confirmed_person_ids(role=...)` -- "
        "`evaluate_founder_relevant_experience()` calls it with role='founder' "
        "(an EXACT match against this field), `evaluate_public_track_record()` "
        "calls it with role=None (any role admits). A realistic extracted role "
        "string like 'Co-Founder and CEO' will NEVER exactly equal 'founder' -- "
        "a real, confirmed gap this contract documents (item 21's own 'remaining "
        "limitations') without silently normalizing it here, since doing so "
        "would be a methodology-adjacent change this task does not make."
    ),
)

FOUNDER_EXPERIENCE_CONTRACT = FactKindContract(
    kind="founder_experience",
    consumer_dimensions=frozenset({"founder_relevant_experience"}),
    required_fields=("person_id", "value", "named_entity"),
    categorical_fields={"value": tuple(v.value for v in FounderExperienceRelevance)},
    notes=(
        "value=DIRECT: the person's prior role was in the SAME domain/problem "
        "space as the current company. value=ADJACENT: a related but "
        "different domain. Never inferred from employer/school PRESTIGE alone "
        "(item 6's own explicit prohibition) -- named_entity records WHERE, "
        "value records WHETHER that experience is relevant, never a quality "
        "judgment of the institution itself."
    ),
)

LEADERSHIP_HIRE_CONTRACT = FactKindContract(
    kind="leadership_hire",
    consumer_dimensions=frozenset({"leadership_composition"}),
    required_fields=(),
    optional_fields=("named_entity", "role"),
    notes="Presence + independence-group counting only (WellBehavedLeadershipCompositionClassifier) -- kind alone is sufficient.",
)

FOUNDERS_ONLY_CONFIRMED_CONTRACT = FactKindContract(
    kind="founders_only_confirmed",
    consumer_dimensions=frozenset({"leadership_composition"}),
    notes="An explicit 'no hires beyond the founders' disclosure -- kind alone is sufficient.",
)

TRACK_RECORD_CONTRACT = FactKindContract(
    kind="track_record",
    consumer_dimensions=frozenset({"public_track_record"}),
    required_fields=("person_id", "value", "named_entity"),
    categorical_fields={"value": tuple(v.value for v in TrackRecordType)},
    notes="PRIOR_EXIT: a prior company that was acquired/IPO'd. PRIOR_VENTURE_ROLE: any other prior venture-backed role.",
)

# --- Execution/product (item 8) -----------------------------------------------

PRODUCT_RELEASE_CONTRACT = FactKindContract(
    kind="product_release",
    consumer_dimensions=frozenset({"shipping_velocity"}),
    required_fields=("named_entity", "status"),
    categorical_fields={"status": tuple(v.value for v in ProductReleaseStatus)},
    notes=(
        "Only status == 'launched' ever counts toward Shipping Velocity -- "
        "'announced'/'beta'/'delayed'/'cancelled' are real, representable, "
        "never-upgraded-to-launched states (unchanged Task 16 methodology). "
        "named_entity identifies WHICH release, for supersession grouping."
    ),
)

GTM_EVIDENCE_CONTRACT = FactKindContract(
    kind="gtm_evidence",
    consumer_dimensions=frozenset({"gtm_motion_evidence"}),
    optional_fields=("named_entity",),
    notes="Presence only (WellBehavedGTMMotionClassifier) -- a named channel/partnership/GTM hire, never general headcount.",
)

STRATEGIC_STATEMENT_CONTRACT = FactKindContract(
    kind="strategic_statement",
    consumer_dimensions=frozenset(),  # context-only; Strategic Consistency reads evidence.disputed directly (Task 16), never this kind's own fields
    optional_fields=("topic",),
    context_only=True,
    notes="Grouping/contradiction-detection identity only (claim_identity.py) -- never read directly by a classifier.",
)

# --- Market (item 9) -----------------------------------------------------------

MARKET_SIZE_USD_CONTRACT = FactKindContract(
    kind="market_size_usd",
    consumer_dimensions=frozenset({"market_definition_size"}),
    required_fields=("value",),
    numeric_fields=("value",),
    notes="A bare USD number (no currency field; only ever read from an INDEPENDENT source, self-published TAM never counts).",
)

CATEGORY_GROWTH_RATE_PCT_CONTRACT = FactKindContract(
    kind="category_growth_rate_pct",
    consumer_dimensions=frozenset({"market_growth_signal"}),
    required_fields=("value",),
    numeric_fields=("value",),
    notes="A bare percentage number, no '%' sign (only ever read from an INDEPENDENT source).",
)

CATALYST_NAME_CONTRACT = FactKindContract(
    kind="catalyst_name",
    consumer_dimensions=frozenset({"timing_catalyst"}),
    notes="Presence, from an independent source, is the entire signal -- a NAMED, specific, checkable catalyst, never generic hype language.",
)

COMPETITIVE_STRUCTURE_CONTRACT = FactKindContract(
    kind="competitive_structure",
    consumer_dimensions=frozenset({"competitive_landscape_position"}),
    required_fields=("value",),
    categorical_fields={"value": tuple(v.value for v in CompetitiveStructureType)},
    notes="An independent analyst's OWN structural read of the market -- never inferred from a bare list of named competitors.",
)

# --- Commercial Traction (item 5/7) --------------------------------------------

TRACTION_METRIC_CONTRACT = FactKindContract(
    kind="traction_metric",
    consumer_dimensions=frozenset({"disclosed_scale", "growth_trajectory"}),  # revenue_disclosure is NEVER directly proposable -- see claim_identity.py's own auto-tag rule, unchanged
    required_fields=("metric", "value_type", "amount", "period_date"),
    optional_fields=("named_entity", "currency"),
    categorical_fields={
        "metric": tuple(v.value for v in TractionMetricType),
        "value_type": tuple(v.value for v in TractionValueType),
    },
    numeric_fields=("amount",),
    date_fields=("period_date",),
    notes=(
        "`currency` is required and must equal 'USD' ONLY when `metric` is a "
        "money metric (revenue/arr/gmv/bookings) -- ignored for count metrics "
        "(active_users/paying_customers), mirroring `_parse_scale_point()`'s "
        "own exact branching."
    ),
)

CUSTOMER_BAND_CONTRACT = FactKindContract(
    kind="customer_band",
    consumer_dimensions=frozenset({"customer_base_breadth"}),
    required_fields=("value",),
    categorical_fields={"value": tuple(v.value for v in CustomerBandSize)},
    notes="A qualitative band, never a bare customer count (item 7's own 'customer logos/counts alone are weak evidence').",
)

COMMERCIAL_COMMITMENT_CONTRACT = FactKindContract(
    kind="commercial_commitment",
    consumer_dimensions=frozenset({"commercial_validation"}),
    optional_fields=("named_entity",),
    notes="Presence + independence-group counting only (WellBehavedCommercialValidationClassifier) -- kind alone is sufficient.",
)

RETENTION_SIGNAL_CONTRACT = FactKindContract(
    kind="retention_signal",
    consumer_dimensions=frozenset({"retention_renewal_signal"}),
    required_fields=("value",),
    categorical_fields={"value": tuple(v.value for v in StrengthLabel)},
    notes=(
        "item 7's own explicit exclusion list, unchanged: never inferred from "
        "customer logos, customer count, testimonials, generic adoption, or "
        "company longevity -- only a real, explicit retention/renewal/churn "
        "figure or statement."
    ),
)

FACT_CONTRACTS: dict[str, FactKindContract] = {
    c.kind: c for c in (
        FUNDING_ROUND_CONTRACT, FUNDING_ROUND_TYPE_CONTRACT, FOUNDING_YEAR_CONTRACT,
        CAPITAL_EFFICIENCY_SIGNAL_CONTRACT, TEAM_IDENTITY_CONTRACT, FOUNDER_EXPERIENCE_CONTRACT,
        LEADERSHIP_HIRE_CONTRACT, FOUNDERS_ONLY_CONFIRMED_CONTRACT, TRACK_RECORD_CONTRACT,
        PRODUCT_RELEASE_CONTRACT, GTM_EVIDENCE_CONTRACT, STRATEGIC_STATEMENT_CONTRACT,
        MARKET_SIZE_USD_CONTRACT, CATEGORY_GROWTH_RATE_PCT_CONTRACT, CATALYST_NAME_CONTRACT,
        COMPETITIVE_STRUCTURE_CONTRACT, TRACTION_METRIC_CONTRACT, CUSTOMER_BAND_CONTRACT,
        COMMERCIAL_COMMITMENT_CONTRACT, RETENTION_SIGNAL_CONTRACT,
    )
}


# =============================================================================
# The one classifier-readiness check every kind-gated kind now has (item 12's
# own central invariant).
# =============================================================================

def _generic_sufficiency_check(contract: FactKindContract, fact: dict[str, str]) -> bool:
    """Fields present + categorical values valid + numeric/date fields
    parseable -- exactly what each real classifier itself requires,
    generalized from the per-kind contract table above. Never invents or
    infers a missing value (item 11) -- a missing required field simply
    fails the check."""
    for f in contract.required_fields:
        if not fact.get(f):
            return False
    for f, allowed in contract.categorical_fields.items():
        value = fact.get(f)
        if f in contract.required_fields or value is not None:
            if value not in allowed:
                return False
    for f in contract.numeric_fields:
        if f in contract.required_fields and not _numeric_ok(fact.get(f)):
            return False
    for f in contract.date_fields:
        if f in contract.required_fields and not _date_ok(fact.get(f)):
            return False
    # traction_metric's own currency-conditional-on-metric branch (see
    # TRACTION_METRIC_CONTRACT's own notes) -- the one contract with a
    # cross-field condition this generic loop cannot express declaratively.
    if contract.kind == "traction_metric":
        metric = fact.get("metric")
        if metric in (TractionMetricType.REVENUE.value, TractionMetricType.ARR.value,
                      TractionMetricType.GMV.value, TractionMetricType.BOOKINGS.value):
            if fact.get("currency") != "USD":
                return False
    return True


# Kinds Task 25 already verified with their OWN reusable, pillar-owned
# functions -- reused directly here, never re-derived, so this module can
# never silently drift from the real consumer's own check.
_REUSED_TASK_25_CHECKS = {
    "funding_round": funding_round_fields_are_sufficient,
    "funding_round_type": funding_round_type_fields_are_sufficient,
    "founding_year": founding_year_fields_are_sufficient,
}


def check_classifier_readiness(fact: dict[str, str] | None) -> bool:
    """The one function `routing.py` now calls, for every kind-gated
    kind (item 12's own central invariant: "a schema-valid extraction
    object accepted for that fact kind can be consumed safely by its
    intended deterministic classifier"). `None`/no-kind/unrecognized-kind
    all return `False` -- fail closed, never assume readiness."""
    if not fact:
        return False
    kind = fact.get("kind")
    if kind is None:
        return False
    reused = _REUSED_TASK_25_CHECKS.get(kind)
    if reused is not None:
        return reused(fact)
    contract = FACT_CONTRACTS.get(kind)
    if contract is None or contract.context_only:
        return False
    return _generic_sufficiency_check(contract, fact)
