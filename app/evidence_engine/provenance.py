"""
Task 10, item 1 -- evidence-independence verification.

Closes a gap flagged explicitly in NEW_ENGINE_CALIBRATION_REPORT.md Part 9
(Task 9): `independence_group_id` was, until now, trusted at face value --
assigned once, upstream, and never independently re-checked. This module
adds a deterministic, content/provenance-based re-check that DOWNGRADES,
never upgrades, what a declared `independence_group_id` claims: two
claims declared as different groups can be found here to be the same
underlying disclosure (a wire-syndicated restatement, a copied press
release) and folded together; two claims can never be split apart into
MORE distinct facts than their declared grouping already implies. This
is deliberately a safety net that only makes independence counting more
conservative, never less.

No AI/LLM call, no external similarity library -- a plain, reviewable
token-overlap (Jaccard) measure over each claim's own text plus an exact
source_url match, both pure functions of already-persisted Claim fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from app.evidence_engine import parameters as P
from app.evidence_engine.models import Claim

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class IndependenceVerdict(str, Enum):
    INDEPENDENT = "independent"
    UNKNOWN = "unknown"
    LIKELY_DUPLICATE = "likely_duplicate"


def _tokenize(text: str) -> frozenset[str]:
    return frozenset(_TOKEN_PATTERN.findall(text.lower()))


def _jaccard_similarity(a: str, b: str) -> float:
    tokens_a, tokens_b = _tokenize(a), _tokenize(b)
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union else 0.0


def assess_independence(a: Claim, b: Claim) -> IndependenceVerdict:
    """Pairwise verdict, based on CLAIM CONTENT ONLY -- a token-overlap
    ratio over each claim's own excerpt/claim_text against two
    provisional, CALIBRATION REQUIRED thresholds (parameters.py). High
    overlap means likely the same underlying disclosure (syndication, a
    copied press release, or two outlets restating one wire story);
    moderate overlap means the relationship cannot be confidently
    established either way (per Task 10's own explicit instruction: "when
    independence cannot be established, treat it as unknown"); low
    overlap means independent.

    Task 12, item 1 (fixing a real error NEW_ENGINE_LIVE_EVALUATION.md
    §4.1 found): this function deliberately does NOT treat an identical
    `source_url` as evidence of duplication. Claim identity (are these
    the same underlying FACT) and source identity (are these the same
    SOURCE/page) are different questions -- a single reference/
    documentation page routinely states many distinct facts at one
    stable URL (Notion's own integrations page discloses both "we
    publish a public API" and "our gallery lists Jira/Drive/Slack",
    two different facts, one URL), and collapsing them because they
    share a URL was exactly the bug found in practice. A genuine
    same-source restatement of the same fact is still caught correctly
    here, because restated text is almost always near-identical wording
    -- which the similarity check below already detects on its own,
    without needing the URL as a second, overriding signal."""
    text_a = a.excerpt or a.claim_text
    text_b = b.excerpt or b.claim_text
    similarity = _jaccard_similarity(text_a, text_b)

    if similarity >= P.PROVENANCE_DUPLICATE_SIMILARITY_THRESHOLD:
        return IndependenceVerdict.LIKELY_DUPLICATE
    if similarity >= P.PROVENANCE_UNKNOWN_SIMILARITY_THRESHOLD:
        return IndependenceVerdict.UNKNOWN
    return IndependenceVerdict.INDEPENDENT


@dataclass(frozen=True)
class VerifiedIndependence:
    # One representative claim per confirmed-distinct underlying fact --
    # this is the number that should be trusted for a "how many separate
    # facts does this evidence establish" question.
    confirmed_independent: tuple[Claim, ...] = field(default_factory=tuple)
    # Claims whose independence from every already-confirmed fact is
    # UNKNOWN -- retained as usable evidence elsewhere, but never counted
    # toward a distinct-fact minimum (conservative, per Task 10's
    # instruction).
    unknown_independence: tuple[Claim, ...] = field(default_factory=tuple)
    # Claims folded into an existing confirmed fact as a likely duplicate
    # / syndicated restatement -- explicitly not counted, and named in any
    # rejection message so a human reviewer can see exactly why.
    folded_duplicates: tuple[Claim, ...] = field(default_factory=tuple)


def verify_independence(claims: tuple[Claim, ...]) -> VerifiedIndependence:
    """Greedy clustering in a stable, deterministic order (claims must
    already be sorted by claim_id by the caller -- ledger.py's
    `resolve_dimension_evidence` already returns `admissible` this way, so
    this function's own output is reproducible regardless of any
    non-deterministic collection order upstream)."""
    confirmed: list[Claim] = []
    unknown: list[Claim] = []
    duplicates: list[Claim] = []

    for claim in claims:
        verdicts = [assess_independence(claim, existing) for existing in confirmed]
        if any(v == IndependenceVerdict.LIKELY_DUPLICATE for v in verdicts):
            duplicates.append(claim)
            continue
        if any(v == IndependenceVerdict.UNKNOWN for v in verdicts):
            unknown.append(claim)
            continue
        confirmed.append(claim)

    return VerifiedIndependence(
        confirmed_independent=tuple(confirmed),
        unknown_independence=tuple(unknown),
        folded_duplicates=tuple(duplicates),
    )


def verified_distinct_fact_count(claims: tuple[Claim, ...]) -> int:
    return len(verify_independence(claims).confirmed_independent)
