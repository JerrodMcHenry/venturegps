"""
Task 29 items 6-11 -- deterministic semantic-fit validation.

**The problem this closes (Task 28 §5 / `LIVE_EVALUATION_CONTRACT_
VALIDATION_001.md` §5).** Task 27's own contract (`fact_contracts.py`)
answers "is this field present, and is its value one of the allowed
enum members?" -- structural/vocabulary correctness. It was never
designed to, and cannot, answer a different question: "does the
excerpt this claim cites actually SUPPORT the SPECIFIC value chosen, as
opposed to some other value in the same enum?" Task 28's live validation
found two confirmed, real instances where schema-valid was not
semantically valid: `retention_signal="STRONG"` assigned to a 90%-
multiplayer-usage ADOPTION statistic (not retention/renewal/churn
evidence at all), and `competitive_structure="fragmented"` inferred from
a bare, uncharacterized list of named competitors (which proves
competitors exist, not that the market is fragmented).

**This module is a THIRD, independent gate, deliberately kept separate
from the other two (item 6's own explicit instruction):**

    JSON/schema validation  -- Pydantic/OpenAI structured output (providers_live.py)
    grounding validation    -- excerpt genuinely supports claim_text (extraction.py::validate_candidate)
    classifier readiness    -- required fields present, values in vocabulary (fact_contracts.py)
    semantic fit (THIS)     -- does the excerpt support the SPECIFIC value chosen (this module)
    routing/applicability   -- does the dimension this fact could reach even exist for it (routing.py)

Each is a real, distinct question; none is a substitute for another.

**Deterministic, never probabilistic, by construction.** Every rule here
is a plain keyword/phrase match over the claim's own `claim_text`/
`excerpt` -- no model call (item 18's own "no OpenAI"), no heuristic
score, no threshold to tune. A rule either finds explicit, on-topic
vocabulary (`SUPPORTED`), finds none (`UNSUPPORTED`, fails closed -- an
absence of evidence is never treated as evidence), or the kind simply
has no rule defined at all (`NOT_APPLICABLE` -- a THIRD, distinct
outcome, never conflated with either of the other two; item 10's own
"avoid creating another opaque boolean").

**Item 9 -- generalized carefully, not into a rules engine.** Only two
rules are defined: `retention_signal` and `competitive_structure`, the
two kinds Task 28 found a CONFIRMED real mismatch for. Every other
categorical field was inspected and deliberately left `NOT_APPLICABLE`
-- see `docs/methodology/SEMANTIC_EVIDENCE_CONTRACT.md` §"Categorical
fields left to probabilistic judgment" for the full, per-field reasoning
(in short: a reliable, low-false-reject proxy rule could not be built for
them without either being trivially gameable or rejecting a large
fraction of genuinely legitimate evidence that simply never restates the
methodology's own exact vocabulary in the source text).

**Item 11 -- never inspects scoring.** No function in this module reads,
imports, or has any way to reach a `Strength`/`Coverage`/company-identity
value. The same evidence SHAPE (same kind, same value, same claim_text/
excerpt content) must, and does, receive the identical semantic-fit
decision regardless of which company or claim_id it belongs to --
`test_semantic_fit.py::test_semantic_fit_decision_is_company_name_
invariant` proves this directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from app.evidence_engine.acquisition.fact_contracts import check_classifier_readiness


class SemanticFitStatus(str, Enum):
    """A third, distinct value -- never collapsed into a boolean (item
    10's own explicit instruction). `NOT_APPLICABLE` is not a claim that
    the fact IS semantically fine; it means this module has no rule for
    this kind at all, and downstream code must treat it exactly as
    "unaffected by this gate," never as "passed" a check that was never
    actually run."""

    NOT_APPLICABLE = "not_applicable"
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class SemanticFitResult:
    status: SemanticFitStatus
    reason: str


def _text_for_check(claim_text: str | None, excerpt: str | None) -> str:
    return f"{claim_text or ''} {excerpt or ''}".lower()


# =============================================================================
# Retention rule (item 7).
# =============================================================================

# Explicit retention/renewal/churn/repeat-customer vocabulary only --
# never a proxy. A customer count, active-user figure, logo, testimonial,
# adoption statistic, longevity claim, growth figure, or popularity claim
# contains none of these words and is therefore correctly UNSUPPORTED,
# exactly item 7's own exclusion list.
_RETENTION_SUPPORT_PATTERNS = (
    r"\bretention\b",
    r"\brenew(?:al|als|ed|ing|s)?\b",
    r"\bchurn(?:ed|ing|s)?\b",
    r"\brepeat custom",
    r"\breturning custom",
    r"\brecurring custom",
    r"\bretain(?:ed|ing|s)?\b",
    r"\bcontinu(?:ed|ing) (?:subscri|custom)",
)
_RETENTION_SUPPORT_RE = re.compile("|".join(_RETENTION_SUPPORT_PATTERNS))


def _check_retention_signal(fact: dict[str, str], claim_text: str | None, excerpt: str | None) -> SemanticFitResult:
    text = _text_for_check(claim_text, excerpt)
    if _RETENTION_SUPPORT_RE.search(text):
        return SemanticFitResult(
            SemanticFitStatus.SUPPORTED,
            "claim_text/excerpt contains explicit retention/renewal/churn/repeat-customer vocabulary",
        )
    return SemanticFitResult(
        SemanticFitStatus.UNSUPPORTED,
        "no explicit retention/renewal/churn/repeat-customer vocabulary found -- a customer-count, "
        "active-user, logo, testimonial, adoption, longevity, growth, or popularity statistic is not "
        "retention evidence by itself (item 7's own exclusion list)",
    )


# =============================================================================
# Competitive-structure rule (item 8).
# =============================================================================

# A bare list of named competitors proves competitors exist -- it proves
# nothing about market STRUCTURE. Only explicit structural-characterization
# language counts, and only for the specific value it actually supports
# (fragmented-vocabulary never supports "concentrated" and vice versa).
_FRAGMENTED_STRUCTURE_PATTERNS = (
    r"\bfragmented\b",
    r"\bno (?:clear|dominant|single) (?:leader|player)\b",
    r"\bmany (?:players|competitors|vendors)\b",
    r"\bnumerous competitors\b",
    r"\bhighly competitive landscape\b",
    r"\bcrowded market\b",
    r"\bno single dominant\b",
)
_CONCENTRATED_STRUCTURE_PATTERNS = (
    r"\bconcentrated\b",
    r"\bdominated by\b",
    r"\bmarket leader\b",
    r"\bduopoly\b",
    r"\bmonopoly\b",
    r"\bfew (?:major )?players\b",
    r"\bconsolidated market\b",
)
_FRAGMENTED_RE = re.compile("|".join(_FRAGMENTED_STRUCTURE_PATTERNS))
_CONCENTRATED_RE = re.compile("|".join(_CONCENTRATED_STRUCTURE_PATTERNS))


def _check_competitive_structure(fact: dict[str, str], claim_text: str | None, excerpt: str | None) -> SemanticFitResult:
    text = _text_for_check(claim_text, excerpt)
    value = (fact.get("value") or "").strip().lower()
    if value == "fragmented" and _FRAGMENTED_RE.search(text):
        return SemanticFitResult(
            SemanticFitStatus.SUPPORTED,
            "claim_text/excerpt contains explicit fragmented-market structural vocabulary",
        )
    if value == "concentrated" and _CONCENTRATED_RE.search(text):
        return SemanticFitResult(
            SemanticFitStatus.SUPPORTED,
            "claim_text/excerpt contains explicit concentrated-market structural vocabulary",
        )
    return SemanticFitResult(
        SemanticFitStatus.UNSUPPORTED,
        "no explicit market-structure characterization found -- a bare list of named competitors does not, "
        "by itself, establish fragmented/concentrated structure (item 8's own exclusion)",
    )


# =============================================================================
# Dispatch.
# =============================================================================

_SEMANTIC_FIT_CHECKS: dict[str, Callable[[dict, str | None, str | None], SemanticFitResult]] = {
    "retention_signal": _check_retention_signal,
    "competitive_structure": _check_competitive_structure,
}


def check_semantic_fit(
    fact: dict[str, str] | None, claim_text: str | None, excerpt: str | None,
) -> SemanticFitResult:
    """The one public entry point. Fails closed to `NOT_APPLICABLE` (not
    `SUPPORTED`) for `None`/no-kind/any kind with no defined rule --
    "no rule exists" is never silently treated as "passed." Never
    inspects `fact` for anything beyond its own `kind`/`value` fields;
    never receives or reads a company name, Strength, or Coverage value
    (item 11)."""
    if not fact:
        return SemanticFitResult(SemanticFitStatus.NOT_APPLICABLE, "no structured_fact")
    kind = fact.get("kind")
    checker = _SEMANTIC_FIT_CHECKS.get(kind)
    if checker is None:
        return SemanticFitResult(SemanticFitStatus.NOT_APPLICABLE, f"no semantic-fit rule defined for kind {kind!r}")
    return checker(fact, claim_text, excerpt)


def check_methodology_readiness(
    fact: dict[str, str] | None, claim_text: str | None, excerpt: str | None,
) -> bool:
    """Item 15's own requested terminology, as one function:
    `structured -> classifier-compatible -> semantically-supported ->
    methodology-usable`. `classifier-compatible` is `fact_contracts.py::
    check_classifier_readiness()`, unchanged and unrenamed (so Task
    27/28's own tests and docs stay valid). `methodology-usable` is
    `True` only when the fact is BOTH classifier-compatible AND (no
    semantic-fit rule applies, or the rule that does apply finds it
    supported) -- the full boundary this task's own success criterion
    names: "grounded -> canonical -> structurally compatible ->
    semantically supported -> deterministically routed ->
    methodology-consumable." This function answers the first four of
    those six stages in one call; routing (`routing.py::route_
    candidate()`) is what actually performs the fifth, using this exact
    same logic."""
    if not check_classifier_readiness(fact):
        return False
    result = check_semantic_fit(fact, claim_text, excerpt)
    return result.status != SemanticFitStatus.UNSUPPORTED
