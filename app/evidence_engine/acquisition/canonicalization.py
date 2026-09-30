"""
Task 29 items 2/4/5 -- deterministic field canonicalization, applied
BEFORE routing's applicability check.

**The defect this closes (Task 28 §10, `LIVE_EVALUATION_FISH_AUDIO_002.md`
§5).** `extraction.py`'s routing/applicability step
(`_sanitize_assessment_criteria()` -> `routing.py::route_candidate()` ->
`fact_contracts.py::check_classifier_readiness()`) ran on the candidate's
RAW, just-extracted `structured_fact` -- before `claim_identity.py::
finalize_claim()`'s own `person_id` backfill, and before any
representation-level cleanup of a numeric amount or an explicit-but-
non-ISO date. A fact that is genuinely, deterministically completable
from what the model already grounded (a real person's name; "$52M"; an
explicit "Aug 5, 2026") was judged "insufficient structure" at routing
time and permanently stripped of its dimension, even though the SAME
fact becomes genuinely classifier-ready moments later.

**The fix -- canonicalize before applicability, not instead of it.** This
module provides ONE function, `canonicalize_structured_fact()`, called by
`extraction.py::_sanitize_assessment_criteria()` immediately before
`route_candidate()` runs (the smallest architectural change that
satisfies item 2's own "fields deterministically derivable from grounded
evidence are present before routing checks that depend on them" --
deliberately NOT a general pipeline reorder). Conceptually:

    extract -> ground -> canonicalize identity/fields -> validate
    semantic structure -> determine routing applicability -> finalize claim

Everything this module does is a REPRESENTATION conversion, never
evidence creation: the canonical form must be mathematically/
structurally equivalent to what the source already, unambiguously
states. Nothing here:

  - invents a `person_id` from anything but an explicit, already-
    extracted `named_entity` (reuses `claim_identity.py::backfill_
    person_id()` directly -- the exact same deterministic derivation
    `finalize_claim()` has always used, never re-implemented);
  - infers a currency, converts between currencies, estimates a range,
    or turns a vague quantifier ("tens of millions") into a precise
    number;
  - infers a date from a bare year, a partial year-month, a vague
    quarter, or the source's own publication date.

Each canonicalizer returns the ORIGINAL value, completely unchanged,
whenever the input does not unambiguously match its narrow, explicit
pattern -- "ambiguous amounts fail closed" (item 19.4) is the default,
not a special case; `check_classifier_readiness()` then correctly
continues to return `False` for anything this module declines to
canonicalize, exactly as it did before this module existed.
`finalize_claim()`'s own, still-unchanged call to `backfill_person_id()`
remains a safe, idempotent no-op once this module has already run (its
own `if fact.get("person_id"): return fact` early return).
"""

from __future__ import annotations

import re
from datetime import date as _date

from app.evidence_engine.acquisition.claim_identity import backfill_person_id
from app.evidence_engine.acquisition.fact_contracts import FACT_CONTRACTS

# =============================================================================
# Numeric amount canonicalization (item 4).
# =============================================================================

_NUMERIC_SCALE_SUFFIXES: dict[str, int] = {
    "k": 1_000, "thousand": 1_000,
    "m": 1_000_000, "million": 1_000_000,
    "b": 1_000_000_000, "billion": 1_000_000_000,
}

# Anchored (fullmatch) on purpose: a range ("$50-60M"), a vague
# quantifier ("tens of millions", "over $50M", "approximately $50M"), or
# anything with a second number/word simply does not match this pattern
# at all, and is left completely unchanged -- this is what makes "fail
# closed on ambiguity" the structural default rather than a rule this
# code has to remember to apply.
_CANONICAL_NUMERIC_PATTERN = re.compile(
    r"^\$?\s*([\d,]+(?:\.\d+)?)\s*(thousand|million|billion|k|m|b)?$",
    re.IGNORECASE,
)


def canonicalize_numeric_amount(raw: str | None) -> str | None:
    """A bare, already-`float()`-parseable string is returned unchanged
    (nothing to do). `"$52M"` / `"52M"` / `"52 million"` / `"1,250,000"`
    each unambiguously denote one real number -- `$`, thousands
    separators, and one of the six scale words/letters above are
    stripped/applied deterministically. Anything else -- a range, a
    vague quantifier, a second number, any text this pattern does not
    fullmatch -- is returned exactly as given, never guessed at."""
    if raw is None:
        return None
    try:
        float(raw)
        return raw
    except (TypeError, ValueError):
        pass

    stripped = raw.strip()
    match = _CANONICAL_NUMERIC_PATTERN.fullmatch(stripped)
    if not match:
        return raw

    number_text, suffix = match.group(1), match.group(2)
    number_text = number_text.replace(",", "")
    try:
        number = float(number_text)
    except ValueError:
        return raw

    multiplier = _NUMERIC_SCALE_SUFFIXES.get(suffix.lower(), 1) if suffix else 1
    canonical_value = number * multiplier
    if canonical_value == int(canonical_value):
        return str(int(canonical_value))
    return str(canonical_value)


# =============================================================================
# Explicit-date canonicalization (item 5).
# =============================================================================

_MONTH_NAMES: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTH_ABBR: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# A FULLY explicit month-name date only ("August 5, 2026" / "Aug 5 2026")
# -- day, month, AND year all stated. Deliberately does NOT match a bare
# year ("2026"), a year-month ("2026-07"), a quarter ("Q3 2026"), or a
# vague season/half ("early 2026", "H1 2026") -- normalizing any of
# those would require picking a day (or a month) the source never
# stated, exactly the "period from surrounding assumptions" item 5
# prohibits. Those remain unchanged, and therefore remain correctly
# incomplete per `check_classifier_readiness()` -- "if no qualifying
# period exists, remain incomplete" (item 5's own closing instruction).
_EXPLICIT_MONTH_DATE_PATTERN = re.compile(r"^([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})$")
# A fully-numeric ISO-shaped date with slashes instead of dashes
# ("2026/07/28") -- unambiguous only in Y/M/D order (never D/M/Y or
# M/D/Y, both of which are genuinely ambiguous for two-digit day/month
# values and are deliberately NOT matched here).
_EXPLICIT_YMD_SLASH_PATTERN = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")


def canonicalize_explicit_date(raw: str | None) -> str | None:
    """Returns `raw` unchanged whenever it is already ISO-8601
    (`date.fromisoformat()`-parseable) or does not match one of the two
    narrow, fully-explicit patterns above. Never fabricates a day or
    month that was not literally present in the source string."""
    if raw is None:
        return None
    try:
        _date.fromisoformat(raw)
        return raw
    except (TypeError, ValueError):
        pass

    stripped = raw.strip()

    ymd = _EXPLICIT_YMD_SLASH_PATTERN.fullmatch(stripped)
    if ymd:
        year, month, day = (int(g) for g in ymd.groups())
        try:
            return _date(year, month, day).isoformat()
        except ValueError:
            return raw

    month_date = _EXPLICIT_MONTH_DATE_PATTERN.fullmatch(stripped)
    if month_date:
        month_text, day_text, year_text = month_date.groups()
        month_key = month_text.lower().rstrip(".")
        month = _MONTH_NAMES.get(month_key) or _MONTH_ABBR.get(month_key)
        if month is None:
            return raw
        try:
            return _date(int(year_text), month, int(day_text)).isoformat()
        except ValueError:
            return raw

    return raw


# =============================================================================
# The one entry point extraction.py calls.
# =============================================================================

def canonicalize_structured_fact(fact: dict[str, str] | None) -> dict[str, str] | None:
    """Applies, in order: (1) deterministic `person_id` backfill (reused
    from `claim_identity.py`, unchanged derivation), (2) numeric-amount
    canonicalization for every field `fact_contracts.py`'s own contract
    for this `kind` lists as a `numeric_fields` entry, (3) explicit-date
    canonicalization for every field listed as a `date_fields` entry.
    Fields outside a recognized kind's own contract, or outside its
    numeric/date field lists, are never touched -- this function narrows
    its own reach to exactly the fields each real consumer is already
    known to read as numeric/date (`fact_contracts.py`, Task 27), never
    guessing at a field's type from its name alone."""
    if fact is None:
        return None

    fact = backfill_person_id(fact)

    contract = FACT_CONTRACTS.get(fact.get("kind"))
    if contract is None:
        return fact

    updates: dict[str, str] = {}
    for field in contract.numeric_fields:
        raw = fact.get(field)
        if raw is None:
            continue
        canonical = canonicalize_numeric_amount(raw)
        if canonical is not None and canonical != raw:
            updates[field] = canonical
    for field in contract.date_fields:
        raw = fact.get(field)
        if raw is None:
            continue
        canonical = canonicalize_explicit_date(raw)
        if canonical is not None and canonical != raw:
            updates[field] = canonical

    if updates:
        return {**fact, **updates}
    return fact
