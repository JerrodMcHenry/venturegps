"""
Acquisition-time contradiction detection (Task 20 item 13). Pure,
deterministic, typed-fact comparison -- no LLM, no universal natural-
language contradiction solving (item 13's own explicit instruction).

**Why this runs BEFORE ledger construction, not only as a post-hoc audit
(unlike `cross_pillar_audit.py`'s own, different, cross-PILLAR duplicate-
extraction check, Task 18):** `ledger.py::resolve_dimension_evidence()`
already deduplicates claims sharing one `independence_group_id` down to
a single admissible representative (spec Part 2.3) -- correct and
desired for genuine restatements, but if two claims in the SAME group
actually DISAGREE (not merely repeat), silently picking one
representative would hide the disagreement rather than fail closed on
it. Marking the disagreeing claims `disputed`/`contradicts` BEFORE they
ever reach `resolve_dimension_evidence()` is what makes the ALREADY-
EXISTING, unmodified disputed-exclusion rule (spec Part 2.3, unchanged
since Task 9) the thing that actually fails the dimension closed --
this module invents no new exclusion mechanism, only correctly triggers
the one that already exists.

**Deliberately excludes `product_release`.** Two different `status`
values for the same named release (`announced` then later `launched`,
or `launched` then later revealed `delayed`) is normal evolution over
time, not a same-moment disagreement -- Execution & Momentum's own
named-release supersession rule (Task 16) already handles this
correctly by preferring the most recently dated claim. Marking both
`disputed` here would break that mechanism by removing the older claim
from admissibility entirely rather than letting supersession see it.
Item 13's own "product GA vs delayed for the same release" example is
therefore satisfied by the pillar's own existing, tested mechanism, not
by this module.
"""

from __future__ import annotations

from app.evidence_engine import parameters as P
from app.evidence_engine.models import Claim, SupportStatus

# Per-`structured_fact.kind`: (value field to compare, comparison mode).
# "numeric": parsed as float, conflict if the two values differ by more
# than CONTRADICTION_AMOUNT_TOLERANCE_PCT. "categorical": conflict if the
# raw string values simply differ. Any kind not listed here is never
# auto-flagged (module docstring's own product_release exclusion, and
# every kind with no natural "value" to disagree about -- team_identity,
# gtm_evidence, commercial_commitment presence, market/catalyst facts).
_COMPARABLE_KINDS: dict[str, tuple[str, str]] = {
    "traction_metric": ("amount", "numeric"),
    "funding_round": ("amount", "numeric"),
    "customer_band": ("value", "categorical"),
    "capital_efficiency_signal": ("value", "categorical"),
}


def _values_conflict(raw_values: list[tuple[Claim, str]], mode: str) -> list[str]:
    if mode == "numeric":
        parsed: list[tuple[Claim, float]] = []
        for claim, raw in raw_values:
            try:
                parsed.append((claim, float(raw)))
            except (TypeError, ValueError):
                continue
        if len(parsed) < 2:
            return []
        amounts = [a for _, a in parsed]
        lo, hi = min(amounts), max(amounts)
        if lo <= 0:
            return []
        pct_diff = ((hi - lo) / lo) * 100
        if pct_diff < P.CONTRADICTION_AMOUNT_TOLERANCE_PCT:
            return []
        return [c.claim_id for c, _ in parsed]

    if mode == "categorical":
        distinct = {raw for _, raw in raw_values}
        if len(distinct) < 2:
            return []
        return [c.claim_id for c, _ in raw_values]

    return []


def detect_contradictions(claims: tuple[Claim, ...]) -> tuple[Claim, ...]:
    """Groups already-finalized claims by `(company_ref,
    independence_group_id)` -- the canonical fact identity `claim_
    identity.py` already computed -- and, for kinds with a comparable
    value field, marks genuinely conflicting subsets `disputed` with
    `contradicts` populated pairwise. Claims outside any comparable kind,
    or whose group has fewer than 2 members, or whose values agree
    within tolerance, are returned completely unchanged (same object).
    Never mutates in place -- returns a new tuple; `Claim` is itself
    immutable (Pydantic, frozen by convention throughout this engine)."""
    by_group: dict[tuple[str, str], list[Claim]] = {}
    for c in claims:
        by_group.setdefault((c.company_ref, c.independence_group_id), []).append(c)

    conflicting_ids: set[str] = set()
    contradicts_map: dict[str, list[str]] = {}

    for group_claims in by_group.values():
        if len(group_claims) < 2:
            continue
        fact = group_claims[0].structured_fact or {}
        kind = fact.get("kind")
        rule = _COMPARABLE_KINDS.get(kind)
        if rule is None:
            continue
        field_name, mode = rule
        raw_values = [
            (c, (c.structured_fact or {}).get(field_name))
            for c in group_claims
            if (c.structured_fact or {}).get(field_name) is not None
        ]
        if len(raw_values) < 2:
            continue
        ids = _values_conflict(raw_values, mode)
        if not ids:
            continue
        for cid in ids:
            conflicting_ids.add(cid)
            contradicts_map[cid] = [other for other in ids if other != cid]

    if not conflicting_ids:
        return claims

    result: list[Claim] = []
    for c in claims:
        if c.claim_id in conflicting_ids:
            result.append(c.model_copy(update={
                "support_status": SupportStatus.DISPUTED,
                "contradicts": contradicts_map[c.claim_id],
                "excerpt": None,
            }))
        else:
            result.append(c)
    return tuple(result)
