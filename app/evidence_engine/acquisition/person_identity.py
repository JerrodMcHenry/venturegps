"""
Deterministic person-identity normalization (Task 23, LINEAR_001
remediation item 6).

**The problem this closes.** `LIVE_EVALUATION_LINEAR_001.md` found two
genuinely independent sources (a YouTube video title, a First Round
Review podcast page) both confirming "Karri Saarinen is co-founder/CEO
of Linear" -- but they landed in two DIFFERENT `independence_group_id`s
instead of being recognized as corroborating the same person fact. Root
cause: `claim_identity.py::IDENTITY_KEY_FIELDS["team_identity"] =
("person_id",)` keys identity claims on `structured_fact.person_id` --
but the extractor supplied `named_entity`/`role` instead of `person_id`
on one claim, and no `structured_fact` at all on the others, so the
identity key fell back to `person_id=""` (empty) or the free-text
fallback (`claim_identity.py::compute_independence_group_id`'s own
"least preferred path"), which differs across differently-worded claims
about the SAME person.

**The fix.** `person_id` is never something the LLM is trusted to
invent -- item 6's own explicit "The LLM must not manufacture a person
identifier. Prefer deterministic normalization from an explicitly
extracted person name." `normalize_person_name_to_id()` below is a pure
function: given the person's NAME as free text (something the extractor
already reliably supplies as `named_entity` on identity/experience/
track-record facts), it deterministically derives a stable id -- the
same real name, however it is capitalized or spaced, always normalizes
to the same id; two different real names never collide (short of an
exact, deliberate homograph, which normalization does not try to solve
-- see "Known limitation" below). `claim_identity.py::finalize_claim()`
calls this to BACKFILL `person_id` from `named_entity` when the model
supplied a name but not an id -- never overwriting a `person_id` the
model DID supply, and never inventing a name that was never extracted.

**Vague titles are explicitly refused, never resolved.** Item 6's own
"do not infer identity from vague titles such as 'the CEO'" -- a string
that is a title/role/pronoun rather than an actual proper name (checked
against a small, explicit denylist, not a guess) returns `None`
("identity could not be established"), which every existing caller
(`_confirmed_person_ids()`, `compute_independence_group_id()`) already
treats identically to "no identity claim at all" -- fails closed by
construction, not a new failure mode.

**Known limitation, documented rather than silently assumed away:** this
is name-STRING normalization (whitespace/case/diacritics/punctuation),
not real-world entity resolution -- two different real people who
happen to share an identical full name would still collide, and a name
spelled two genuinely different ways in two sources (a typo, a
transliteration difference) would not be recognized as the same person.
Both are explicitly out of scope for a deterministic, no-network,
no-ML-model normalizer; see `LINEAR_001_REMEDIATION.md` for the same
caveat restated in the context of this specific fix.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9\s]")

# Titles/roles/pronouns that are NOT a person's name -- explicit,
# reviewable, never a heuristic like "starts with 'the'" that could
# accidentally reject a real name. Checked against the FULLY normalized
# string, so "the CEO", "The CEO", "the  ceo" all match the same entry.
_VAGUE_TITLE_DENYLIST: frozenset[str] = frozenset({
    "the ceo", "the cto", "the coo", "the cfo", "the cpo",
    "the founder", "the co founder", "the cofounder",
    "the founders", "the co founders", "the cofounders",
    "the executive", "the executives", "the leadership team",
    "the leadership", "the team", "the founding team",
    "he", "she", "they", "him", "her", "them",
    "management", "the management team",
    "the company", "the ceo of the company",
})

# A name this short after normalization is very unlikely to be a real
# full name (a single initial, an empty string after stripping
# punctuation, etc.) -- refused for the same "do not guess" reason as a
# vague title, not because short real names never exist, but because
# there is no way to distinguish a genuine short name from a stripped-
# down fragment without guessing.
_MIN_NORMALIZED_NAME_LENGTH = 3


def _normalize_name_text(name: str) -> str:
    """Lowercase, strip diacritics (NFKD-decompose then drop combining
    marks -- "Åsa" and "asa" normalize identically, a deliberate,
    documented simplification, not a claim that the two are always the
    same person), collapse punctuation to whitespace, collapse repeated
    whitespace."""
    decomposed = unicodedata.normalize("NFKD", name)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = without_marks.lower()
    despunctuated = _NON_ALNUM.sub(" ", lowered)
    return _WHITESPACE.sub(" ", despunctuated).strip()


def normalize_person_name_to_id(name: str | None) -> str | None:
    """Returns a stable, deterministic `person_id`, or `None` when
    identity cannot be safely established (empty/missing name, a vague
    title, or too short to trust). Same real name -> same id, regardless
    of case/spacing/diacritics; never invented, never guessed from a
    role alone."""
    if not name or not name.strip():
        return None
    normalized = _normalize_name_text(name)
    if not normalized:
        return None
    if normalized in _VAGUE_TITLE_DENYLIST:
        return None
    if len(normalized) < _MIN_NORMALIZED_NAME_LENGTH:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
