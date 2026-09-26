"""
Phase 10.9, Part 9 -- V3 evidence adapter.

    Production research (app/ai/research_enrichment.py)
    -> evidence extraction + pillar scoring (V2.1, app/ai/analyze_pillar.py,
       app/ai/pillar_scoring.py, app/ai/evidence_extraction.py -- UNCHANGED,
       still the only thing that runs by default)
    -> V3 canonical observation adapter (THIS FILE)
    -> canonical signals (app/ai/sps_v3_engine/signals.py)
    -> deterministic evaluators (app/ai/sps_v3_engine/evaluators.py)
    -> aggregation (app/ai/sps_v3_engine/aggregation.py)
    -> SIEMethodologyAnalysis.sps_v3 (app/models/sps_v3.py)

This module makes ZERO new research calls and gathers ZERO new evidence
(Phase 10.9 Part 8) -- it only re-reads the SAME six PillarAnalysis
objects V2.1 already computed for this exact analysis. Its one LLM call
(gated behind SPS_V3_ENABLED, see below) is a narrow CLASSIFICATION step
over text V2.1 already extracted and already marked "Observed" (real,
sourced, non-inferred) -- explicitly permitted by Phase 10.9 Part 7
("The LLM may... extract facts, normalize facts, classify evidence").
It is never asked for, and structurally cannot produce, a numeric score:
its output schema (_ExtractionResult below) has no score-shaped field at
all. Every downstream number is produced exclusively by the frozen,
deterministic app.ai.sps_v3_engine evaluators.

SCOPE (Part 9's "responsibly possible", Part 8's "not an attempt to
maximize Coverage"): this v1 adapter classifies evidence for 9 of the 27
V3 dimensions -- the qualitative ones whose required observation fields
(a named competitor, a founder's role, a shipped capability label, a
contract type) are safely groundable in a verbatim quote from V2.1's own
evidence text. It deliberately does NOT attempt the 4 Category-A
quantitative dimensions (current_scale, growth_trajectory,
retention_engagement, capital_efficiency) or the 2 remaining Category-B
Financial Health / Traction dimensions that require a precise number with
an as-of date (revenue_quality, customer_adoption) -- fabricating those
from loosely-parsed narrative text is exactly the numeric-fabrication
risk Part 10 exists to prevent, and the V2.1 evidence pipeline's own free-
text Evidence.statement shape (app/models/evidence.py) offers no
structured number to safely draw from. These dimensions are correctly,
honestly UNKNOWN under this adapter -- see
docs/methodology/SPS_V3_PRODUCTION_INTEGRATION_10_9.md Section 5 for the
full accounting and the explicitly-named next step (a dedicated
structured-numeric-extraction adapter) this phase does NOT build.

FIREWALL: every observation this adapter constructs carries a
verbatim_quote that is re-verified (after the LLM call returns) to
actually appear, near-verbatim, in the source text the model was given --
mirroring app/ai/evidence_provenance.py's existing "verify, don't just
prompt" discipline. A classification whose quote cannot be found is
dropped entirely, never kept on trust. No observation is ever
constructed from an "Inferred" or "Unavailable" V2.1 subscore -- only
"Observed".

ADAPTER HARDENING (post-Real-World-Acceptance-Test phase): three concrete
adapter-layer defects, found by running this adapter against 7 real
companies (docs/validation/SPS_V3_REAL_WORLD_ACCEPTANCE.md), are fixed
here. The deterministic engine (app/ai/sps_v3_engine/) is untouched --
these are evidence-acquisition/classification fixes only:

1. CAPABILITY CLASSIFICATION LEAKAGE -- generic financial/operational
   boilerplate ("healthy cash runway," "strong margins," "customer
   growth") was being misclassified as a shipped ProductCapabilityObservation.
   Fixed with (a) explicit positive/negative criteria in _SYSTEM_MESSAGE,
   and (b) a deterministic secondary safety net,
   _is_financial_operational_boilerplate(), built from generic term
   FAMILIES (never the literal sentences the acceptance test found --
   this is not a company- or phrase-specific blacklist).
2. NO NEGATIVE-EVIDENCE PATH -- the adapter had zero code that ever
   constructed a NegativeSignalObservation. Fixed by adding a
   negative_signals extraction category that reuses the existing,
   frozen NegativeSignalObservation contract exactly (no parallel
   architecture), gated by the same grounding firewall and by a
   dimension whitelist derived read-only from the frozen engine's own
   DIMENSION_PILLARS table.
3. GROUNDING-LOSS ON MISSING verbatim_quote -- the classifier often
   identified a real fact correctly but omitted the verbatim_quote
   field, and the (correctly strict) firewall dropped the whole claim.
   Fixed with a two-tier recovery, preferred order: (a) deterministic,
   no-LLM recovery -- if the claim carries its own proper-noun anchor
   (a named competitor, a prior entity name, a named customer), search
   the ALREADY-STORED source text for a literal sentence containing
   that anchor and use it as the quote (by construction, extracted
   directly from source text, so it trivially satisfies the firewall);
   (b) only for claims with no reliable anchor, a single bounded
   correction-retry LLM call, batched across every such claim in this
   analysis, narrowly scoped to "return the exact supporting quote or
   null" -- never a second content-classification pass. Every recovered
   observation is marked (extraction_confidence=LOW, source_reference=
   "recovered_by_grounding_repair") so it remains distinguishable from a
   claim the classifier grounded on the first try. No fix here ever
   makes an evidence-acceptance decision based on a score -- every
   decision is grounding-based (firewall pass/fail) or content-shape-based
   (boilerplate-term-family match, dimension-vocabulary membership),
   exactly like the pre-existing firewall.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

from pydantic import BaseModel, Field

from app.ai.pillar_shared import call_analysis_model, parse_json_from_response
from app.ai.sps_v3_engine.aggregation import evaluate_sps, classify_ux_state
from app.ai.sps_v3_engine.evaluators import DIMENSION_PILLARS, evaluate_all_dimensions
from app.ai.sps_v3_engine.evidence_bundle import EvidenceBundle
from app.ai.sps_v3_engine.registry import DEFAULT_REGISTRY
from app.ai.sps_v3_engine.types import (
    CommercialContractObservation,
    CompetitiveEvidenceObservation,
    CompetitorType,
    CustomerEvidenceObservation,
    CustomerType,
    DirectOrDerived,
    EvidenceBase,
    ExtractionConfidence,
    FounderExperienceObservation,
    FounderExperienceType,
    FounderOutcomeObservation,
    FounderOutcomeType,
    NegativeSignalObservation,
    ProductCapabilityObservation,
    ProvenanceGrade,
    ProvenanceStatus,
    Stage,
)
from app.models.startup import PillarAnalysis, SIEMethodologyAnalysis
from app.models.sps_v3 import SPSV3Assessment, SPSV3PillarResult

# Bumped from "SPS_V3_10_9" (Adapter Hardening phase): the adapter's
# evidence-acquisition/classification behavior changed materially (see
# module docstring); the deterministic scoring math did not, so
# SPS_V3_SCORING_VERSION is intentionally unchanged. Only referenced
# symbolically in tests (app/tests/test_sps_v3_adapter.py), never
# asserted as a literal string elsewhere -- safe to bump.
SPS_V3_ENGINE_VERSION = "SPS_V3_10_9H"
# Deliberately NOT app.ai.sie_v2_methodology.METHODOLOGY_VERSION or
# app.ai.scoring_methodology.SCORING_VERSION -- Phase 10.9 Part 28
# forbids reusing a V2.1 version string for V3.
SPS_V3_SCORING_VERSION = "sps_v3.10_9.1"

# Fix #2 -- read-only import of the frozen engine's own dimension/pillar
# vocabulary, used only to validate a negative-signal claim's
# affected_dimension against the SAME pillar's real dimension ids (never
# a parallel or hand-maintained list).
_PILLAR_KEY_TO_DISPLAY: dict[str, str] = {
    "market": "Market", "team": "Team", "product": "Product",
    "execution": "Execution", "traction": "Traction",
}
_DIMENSIONS_BY_PILLAR_KEY: dict[str, tuple[str, ...]] = {
    key: tuple(sorted(dim for dim, pillar in DIMENSION_PILLARS.items() if pillar == display))
    for key, display in _PILLAR_KEY_TO_DISPLAY.items()
}


def sps_v3_enabled() -> bool:
    """
    Portfolio Release Task 7, Phase 2 -- One Production Scoring
    Methodology. Reverses the "SPS V3 Canonical Activation" default from
    the previous phase: V3 is now OFF for new analyses unless explicitly
    requested. The Phase 1 audit (docs/methodology/-- see this task's own
    report) found V3 running in production by default with no product
    surface actually using it (Rankings/Search/Discovery/Compare/Score
    History all key off V2.1's startup_intelligence_score, never
    sps_v3), each analysis paying for an extra sequential LLM call for
    an assessment nothing downstream reads. Six-pillar V2.1 is the one
    canonical production scoring system per this task's own explicit
    instruction.

    This uses the SAME configuration mechanism as before, not a new
    one: SPS_ENGINE_VERSION unset, or any value that isn't exactly
    "v3", now selects V2.1-only. Explicitly setting
    SPS_ENGINE_VERSION=v3 still turns V3 back on -- nothing about V3's
    OWN code, its adapter, its engine, or any already-persisted
    analysis's sps_v3 field changed; this flips which state is the
    default, the same one-line-config-change shape the previous phase's
    own rollback switch already used in the other direction. V2.1
    remains fully intact and unconditionally computed either way (see
    run_due_diligence()'s own comment) -- this flag only ever controlled
    whether the ADDITIVE sps_v3 field is also computed, never V2.1
    itself.
    """
    return os.getenv("SPS_ENGINE_VERSION", "v2_1").strip().lower() == "v3"


_STAGE_KEYWORDS: tuple[tuple[str, Stage], ...] = (
    ("pre-seed", Stage.PRE_SEED),
    ("pre seed", Stage.PRE_SEED),
    ("idea", Stage.IDEA),
    ("seed", Stage.SEED),
    ("series a", Stage.SERIES_A),
    ("series b", Stage.SERIES_B_PLUS),
    ("series c", Stage.SERIES_B_PLUS),
    ("series d", Stage.SERIES_B_PLUS),
    ("growth", Stage.GROWTH),
    ("public", Stage.GROWTH),
    ("ipo", Stage.GROWTH),
)


def map_stage(stage_text: str | None) -> Stage:
    """Best-effort free-text -> Stage mapping. Only affects the 4
    Category-A dimensions this v1 adapter never feeds evidence to (see
    module docstring), so an unrecognized/empty stage defaulting to SEED
    has no observable effect on this adapter's output today -- kept
    correct anyway for whenever a future phase extends Category-A
    coverage."""
    lowered = (stage_text or "").strip().lower()
    for keyword, stage in _STAGE_KEYWORDS:
        if keyword in lowered:
            return stage
    return Stage.SEED


# ---------------------------------------------------------------------
# Extraction schema -- structurally cannot carry a score. Every field is
# either a closed enum, a bool, or a short label string, plus
# verbatim_quote, used by the post-call firewall below.
#
# verbatim_quote is `str | None` (SPS V3 local activation verification
# pass -- found via a real live /analyze run): it is REQUIRED in spirit
# (the system prompt insists on it, and _quote_is_grounded() below
# treats a missing/empty quote as ungrounded, so an unquoted claim is
# still always dropped) but declared optional in the schema so that a
# single claim the model forgot to quote fails ONLY that one claim's
# grounding check, not the whole pillar's Pydantic validation. Before
# this fix, a strict `str` field meant one missing quote anywhere in a
# pillar's claim list raised a ValidationError for the entire
# _PillarExtraction, silently discarding every OTHER, correctly-quoted
# claim in that same pillar too -- confirmed live: a real analysis whose
# Team evidence contained a clean, classifiable, grounded founder-
# background quote still produced 0 Team observations, traced to
# exactly this failure mode via a raw-response debug capture.
# ---------------------------------------------------------------------

class _CompetitorClaim(BaseModel):
    verbatim_quote: str | None = None
    named_competitor: str
    # bool | None (not plain bool): the model sometimes emits an explicit
    # `null` for a boolean it isn't confident about, rather than omitting
    # the key or writing `false` -- a bare `bool` field rejects that with
    # a validation error and (before this fix) discarded the entire
    # extraction result. None is treated as "not stated" -> False when
    # constructing the observation (_extraction_to_observations), never
    # as True.
    differentiator_named: bool | None = False


class _CustomerDemandClaim(BaseModel):
    verbatim_quote: str | None = None
    outcome_claim: str
    named_customer: str | None = None


class _FounderExperienceClaim(BaseModel):
    verbatim_quote: str | None = None
    founder_role: str
    experience_type: str  # one of FounderExperienceType values
    prior_entity_name: str | None = None


class _FounderOutcomeClaim(BaseModel):
    verbatim_quote: str | None = None
    prior_entity_name: str
    outcome_type: str  # one of FounderOutcomeType values


class _CapabilityClaim(BaseModel):
    verbatim_quote: str | None = None
    capability_label: str
    shipped: bool | None = False


class _ContractClaim(BaseModel):
    verbatim_quote: str | None = None
    contract_type: str  # one of CustomerType values
    named_customer: str | None = None
    renewal_evidence: bool | None = False


class _NegativeSignalClaim(BaseModel):
    """Fix #2 -- reuses the existing, frozen NegativeSignalObservation
    contract exactly (signal_type/severity/affected_dimension); adds
    nothing new to that contract. verbatim_quote is optional for the
    same missing-field-robustness reason as every other claim type
    above (see the class comment)."""
    verbatim_quote: str | None = None
    signal_type: str
    severity: str | None = "MODERATE"  # LOW | MODERATE | SEVERE
    affected_dimension: str


class _PillarExtraction(BaseModel):
    competitors: list[_CompetitorClaim] = Field(default_factory=list)
    customer_demand: list[_CustomerDemandClaim] = Field(default_factory=list)
    customer_value: list[_CustomerDemandClaim] = Field(default_factory=list)
    founder_experience: list[_FounderExperienceClaim] = Field(default_factory=list)
    founder_outcomes: list[_FounderOutcomeClaim] = Field(default_factory=list)
    capabilities: list[_CapabilityClaim] = Field(default_factory=list)
    contracts: list[_ContractClaim] = Field(default_factory=list)
    negative_signals: list[_NegativeSignalClaim] = Field(default_factory=list)


class _ExtractionResult(BaseModel):
    market: _PillarExtraction = Field(default_factory=_PillarExtraction)
    team: _PillarExtraction = Field(default_factory=_PillarExtraction)
    product: _PillarExtraction = Field(default_factory=_PillarExtraction)
    execution: _PillarExtraction = Field(default_factory=_PillarExtraction)
    traction: _PillarExtraction = Field(default_factory=_PillarExtraction)


_SYSTEM_MESSAGE = """You are a strict evidence classifier. You are given, per \
pillar, a list of ALREADY-VERIFIED text passages about one startup. Your \
ONLY job is to classify what is explicitly stated into a fixed taxonomy. \
You do not score, rate, rank, or judge the company in any way -- there is \
no score field in your output schema, and any such judgment is out of \
scope. You do not invent, estimate, or infer any fact not explicitly \
present in the given text. Every classification you produce MUST include \
verbatim_quote: an exact, word-for-word substring copied from the \
provided text that supports it. If you cannot find explicit text \
supporting a classification, do not include it -- an empty list is \
always a valid, correct answer for any category.

CAPABILITIES -- what qualifies as a shipped product/technical capability: \
a capability claim must describe something the company actually BUILT, \
LAUNCHED, SHIPPED, or OPERATES as part of its product or technology -- a \
feature, an integration, an architecture choice, a deployment, or a \
measurable technical/product milestone. Generic financial facts (cash \
balance, funding raised, revenue figures, gross margin, burn rate, \
runway) and generic operational facts (headcount, hiring plans, customer \
or revenue growth stated with no product detail, routine financial or \
operating reviews) are NEVER capabilities, even when the sentence uses \
words like "scaling," "expanding," or "strong execution." Example of a \
VALID capability: "the team shipped a real-time fraud-detection engine \
that processes transactions in under 200ms." Example of something that \
is NOT a capability: "the company reported healthy gross margins and a \
strong cash position." If a passage is purely financial or operational \
with no product/technical content, do not classify it as a capability.

NEGATIVE SIGNALS -- explicit, affirmative adverse facts only. A negative \
signal requires text stating something actually went wrong: a decline, a \
failure, a departure, a shutdown, a compliance or legal problem, a \
material loss of customers/revenue, or a similar disclosed adverse event. \
Missing or unavailable information is NOT a negative signal -- if the \
text simply doesn't mention a topic, that is silence, not evidence of a \
problem. Vague, modest, or merely unimpressive language is also NOT a \
negative signal -- "growth has been steady" or "the company has not \
disclosed revenue" describe absence or ordinariness, not an adverse fact. \
Example of a VALID negative signal: "the company laid off a third of its \
staff in 2023." Example of something that is NOT a negative signal: "the \
company did not provide updated financials this quarter." For every \
negative signal, also supply affected_dimension: the single most \
specific dimension id (from the valid-dimension list given below for \
that pillar) this adverse fact is actually about -- never a generic or \
unrelated dimension.

Return only valid JSON matching the given schema."""


def _pillar_observed_text(pillar: PillarAnalysis) -> str:
    """Only 'Observed' subscores -- never 'Inferred' (an LLM judgment
    call, not a verified fact) or 'Unavailable'. Pulls each such
    subscore's own evidence quotes and extraction-stage signals -- the
    same fields app/models/scoring.py's Subscore docstring documents as
    populated by the evidence-extraction stage, not the scoring stage."""
    lines: list[str] = []
    for subscore in pillar.score_breakdown.subscores:
        if subscore.evidence_status != "Observed":
            continue
        for item in subscore.evidence:
            if item:
                lines.append(str(item))
        for signal in subscore.signals:
            if signal:
                lines.append(str(signal))
    return "\n".join(lines)


def _quote_is_grounded(quote: str | None, source_text: str) -> bool:
    """Post-call firewall (module docstring) -- mirrors
    app/ai/evidence_provenance.py's verify-don't-trust discipline. A
    normalized substring check: whitespace-insensitive, case-insensitive.
    Never trusts the model's own claim that a quote is verbatim. A
    missing quote (None -- the model omitted it) is always ungrounded,
    same as an empty one -- never a special case."""
    if not quote or not source_text:
        return False
    normalize = lambda s: " ".join(s.split()).lower()
    return normalize(quote) in normalize(source_text)


def _extraction_confidence_from_v2_confidence(level: str) -> ExtractionConfidence:
    return {
        "Low": ExtractionConfidence.LOW,
        "Medium": ExtractionConfidence.MEDIUM,
        "High": ExtractionConfidence.HIGH,
    }.get(level, ExtractionConfidence.MEDIUM)


def _base_kwargs(observation_id: str, quote: str, recovered: bool = False) -> dict:
    return dict(
        observation_id=observation_id,
        source_excerpt=quote,
        provenance_status=ProvenanceStatus.ACCEPTED,
        # V2.1's own evidence is sourced from company materials + public
        # research the model was given, never independently re-verified
        # against a primary filing -- PRIMARY_SELF_REPORTED is the
        # correct, non-inflated grade (never PRIMARY_VERIFIED, which
        # Phase 10.8's rulebook reserves for independently-confirmed
        # facts this adapter has no way to establish).
        provenance_grade=ProvenanceGrade.PRIMARY_SELF_REPORTED,
        direct_or_derived=DirectOrDerived.DIRECT,
        # Fix #3 (Adapter Hardening): an observation whose quote was
        # RECOVERED (deterministic anchor match or the bounded
        # correction retry) rather than supplied directly by the
        # classifier gets a strictly lower extraction_confidence and an
        # explicit source_reference marker -- full provenance is
        # preserved without touching the frozen EvidenceBase contract
        # (source_reference is an existing, scoring-inert free-text
        # field; no evaluator reads it).
        extraction_confidence=(ExtractionConfidence.LOW if recovered else ExtractionConfidence.MEDIUM),
        source_reference=("recovered_by_grounding_repair" if recovered else None),
    )


# ---------------------------------------------------------------------
# Fix #1 -- capability classification leakage: a deterministic secondary
# safety net BEHIND the prompt-level positive/negative criteria above.
# Term families only (never the literal sentences the acceptance test
# found for any specific company) -- rejects a capability quote ONLY
# when it contains generic financial/operational disclosure language AND
# contains no product/technical language at all, mirroring the
# codebase's established "LLM instruction + Python-level verification"
# pattern (app/ai/evidence_provenance.py's numeric guard; this module's
# own _quote_is_grounded()).
# ---------------------------------------------------------------------

_FINANCIAL_OPERATIONAL_TERMS: tuple[str, ...] = (
    "cash balance", "cash position", "cash runway", "runway",
    "burn rate", "burn multiple", "gross margin", "margins",
    "funding round", "raised a round", "valuation", "arr", "mrr",
    "revenue growth", "customer growth", "financial review",
    "operating cadence", "headcount", "hiring plan", "hiring pace",
)

_PRODUCT_TECHNICAL_TERMS: tuple[str, ...] = (
    "launch", "shipped", "ship", "released", "release", "built", "build",
    "api", "platform", "feature", "architecture",
    "infrastructure", "algorithm", "model", "engine", "pipeline",
    "workflow", "capability", "product",
)

# Deliberate prefix STEMS (start-of-word match only, never a full
# \bterm\b) -- a single entry covers real morphological variants
# (deploy/deployed/deployment, integrate/integration/integrated,
# automate/automation/automated) without enumerating every inflection.
# Kept separate from _PRODUCT_TECHNICAL_TERMS (which require BOTH word
# boundaries) precisely because a stray whole-word match here would be
# too permissive for these.
_PRODUCT_TECHNICAL_STEMS: tuple[str, ...] = ("deploy", "integrat", "automat")


def _contains_any_term(lowered_text: str, terms: tuple[str, ...], stems: tuple[str, ...] = ()) -> bool:
    """Full word-boundary match (\\bterm\\b) for standalone single-word
    terms -- e.g. "engine" must never match inside "engineering", "ship"
    must never match inside "leadership" -- plain substring match for
    multi-word phrases (inherently low collision risk), and a
    start-boundary-only match for the small explicit `stems` set
    (deliberately meant to catch morphological variants, e.g. "deploy"
    matching "deployed"/"deployment")."""
    for term in terms:
        if " " in term:
            if term in lowered_text:
                return True
        elif re.search(rf"\b{re.escape(term)}\b", lowered_text):
            return True
    for stem in stems:
        if re.search(rf"\b{re.escape(stem)}", lowered_text):
            return True
    return False


def _is_financial_operational_boilerplate(quote: str) -> bool:
    lowered = quote.lower()
    if not _contains_any_term(lowered, _FINANCIAL_OPERATIONAL_TERMS):
        return False
    return not _contains_any_term(lowered, _PRODUCT_TECHNICAL_TERMS, _PRODUCT_TECHNICAL_STEMS)


# ---------------------------------------------------------------------
# Fix #3 -- safe grounding recovery.
# ---------------------------------------------------------------------

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    """Deterministic, newline- and punctuation-aware sentence split over
    the same evidence text _pillar_observed_text() already assembled
    (one evidence/signal item per line) -- never re-fetches or alters
    the source, only reads it."""
    pieces: list[str] = []
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        for sentence in _SENTENCE_SPLIT_RE.split(line):
            sentence = sentence.strip()
            if sentence:
                pieces.append(sentence)
    return pieces


def _recover_quote_by_anchor(anchor: str | None, source_text: str) -> str | None:
    """Tier 1 (deterministic, zero LLM calls): if `anchor` (a claim's
    own proper-noun field -- a named competitor, a prior entity name, a
    named customer) appears in the source text, return the FIRST
    sentence containing it, verbatim -- a real, literal substring of the
    source, so it trivially satisfies _quote_is_grounded() by
    construction. Never invents, paraphrases, or extends the sentence.
    Returns None (no recovery -- stays fail-closed) if the anchor is
    empty or not found in any sentence."""
    if not anchor or not anchor.strip():
        return None
    normalize = lambda s: " ".join(s.split()).lower()
    anchor_norm = normalize(anchor)
    if not anchor_norm:
        return None
    for sentence in _split_sentences(source_text):
        if anchor_norm in normalize(sentence):
            return sentence
    return None


def _grounded_or_recovered(
    quote: str | None,
    anchor: str | None,
    source_text: str,
) -> tuple[str | None, bool]:
    """Returns (quote_to_use, was_recovered). Tries the model's own
    quote first (never counted as recovered); if that fails the
    firewall, tries deterministic anchor recovery; returns (None, False)
    if neither succeeds, leaving the caller to queue tier-2 recovery or
    drop the claim."""
    if _quote_is_grounded(quote, source_text):
        return quote, False
    recovered = _recover_quote_by_anchor(anchor, source_text)
    if recovered is not None:
        return recovered, True
    return None, False


@dataclass
class _PendingRecovery:
    """One claim that survived classification but has no grounded
    quote yet (the model omitted verbatim_quote, and no deterministic
    anchor recovered it). `build` takes a recovered, already-
    firewall-verified quote and constructs the final observation (or
    returns None if the recovered quote still fails a content-shape
    check, e.g. Fix #1's boilerplate guard) -- it is only ever invoked
    AFTER a tier-2 quote has independently passed _quote_is_grounded()
    again, never on trust."""
    pillar_key: str
    source_text: str
    detail: str
    build: Callable[[str], "EvidenceBase | None"]


def _extraction_to_observations(
    pillar_key: str,
    extraction: _PillarExtraction,
    source_text: str,
    id_seed: str,
) -> tuple[list[EvidenceBase], list[_PendingRecovery]]:
    observations: list[EvidenceBase] = []
    pending: list[_PendingRecovery] = []
    counter = 0

    def next_id(prefix: str) -> str:
        nonlocal counter
        counter += 1
        return f"{id_seed}-{prefix}-{counter}"

    valid_dims = _DIMENSIONS_BY_PILLAR_KEY.get(pillar_key, ())

    for claim in extraction.competitors:
        quote, recovered = _grounded_or_recovered(claim.verbatim_quote, claim.named_competitor, source_text)
        if quote is not None:
            observations.append(CompetitiveEvidenceObservation(
                **_base_kwargs(next_id("COMP"), quote, recovered=recovered),
                named_competitor=claim.named_competitor[:200],
                competitor_type=CompetitorType.DIRECT,
                differentiator_named=bool(claim.differentiator_named),
            ))
        else:
            def _build(q: str, claim=claim) -> EvidenceBase:
                return CompetitiveEvidenceObservation(
                    **_base_kwargs(next_id("COMP"), q, recovered=True),
                    named_competitor=claim.named_competitor[:200],
                    competitor_type=CompetitorType.DIRECT,
                    differentiator_named=bool(claim.differentiator_named),
                )
            pending.append(_PendingRecovery(pillar_key, source_text, f'a named-competitor claim about "{claim.named_competitor}"', _build))

    for claim in extraction.customer_demand + extraction.customer_value:
        if not claim.outcome_claim:
            continue
        quote, recovered = _grounded_or_recovered(claim.verbatim_quote, claim.named_customer, source_text)
        if quote is not None:
            observations.append(CustomerEvidenceObservation(
                **_base_kwargs(next_id("CEV"), quote, recovered=recovered),
                named_customer=(claim.named_customer or None),
                outcome_claim=claim.outcome_claim[:500],
                quantified=False,
            ))
        else:
            def _build(q: str, claim=claim) -> EvidenceBase:
                return CustomerEvidenceObservation(
                    **_base_kwargs(next_id("CEV"), q, recovered=True),
                    named_customer=(claim.named_customer or None),
                    outcome_claim=claim.outcome_claim[:500],
                    quantified=False,
                )
            pending.append(_PendingRecovery(pillar_key, source_text, f'a customer-outcome claim: "{claim.outcome_claim}"', _build))

    for claim in extraction.founder_experience:
        try:
            experience_type = FounderExperienceType(claim.experience_type)
        except ValueError:
            continue
        if experience_type in (FounderExperienceType.REPEAT_FOUNDER, FounderExperienceType.PRIOR_EXIT) and not claim.prior_entity_name:
            # Firewall: these two enum values require a named prior
            # entity (enforced by the dataclass itself) -- downgrade
            # rather than fabricate a name.
            experience_type = FounderExperienceType.DIRECT_DOMAIN
        if not claim.founder_role:
            continue
        quote, recovered = _grounded_or_recovered(claim.verbatim_quote, claim.prior_entity_name, source_text)
        if quote is not None:
            observations.append(FounderExperienceObservation(
                **_base_kwargs(next_id("FEXP"), quote, recovered=recovered),
                founder_role=claim.founder_role[:200],
                experience_type=experience_type,
                prior_entity_name=(claim.prior_entity_name or None),
            ))
        else:
            def _build(q: str, claim=claim, experience_type=experience_type) -> EvidenceBase:
                return FounderExperienceObservation(
                    **_base_kwargs(next_id("FEXP"), q, recovered=True),
                    founder_role=claim.founder_role[:200],
                    experience_type=experience_type,
                    prior_entity_name=(claim.prior_entity_name or None),
                )
            detail = f"a founder-experience claim about the {claim.founder_role} ({experience_type.value}"
            detail += f", prior entity {claim.prior_entity_name})" if claim.prior_entity_name else ")"
            pending.append(_PendingRecovery(pillar_key, source_text, detail, _build))

    for claim in extraction.founder_outcomes:
        if not claim.prior_entity_name:
            continue
        try:
            outcome_type = FounderOutcomeType(claim.outcome_type)
        except ValueError:
            continue
        quote, recovered = _grounded_or_recovered(claim.verbatim_quote, claim.prior_entity_name, source_text)
        if quote is not None:
            observations.append(FounderOutcomeObservation(
                **_base_kwargs(next_id("FOUT"), quote, recovered=recovered),
                outcome_type=outcome_type,
                prior_entity_name=claim.prior_entity_name[:200],
                attributed_to_founder=True,
            ))
        else:
            def _build(q: str, claim=claim, outcome_type=outcome_type) -> EvidenceBase:
                return FounderOutcomeObservation(
                    **_base_kwargs(next_id("FOUT"), q, recovered=True),
                    outcome_type=outcome_type,
                    prior_entity_name=claim.prior_entity_name[:200],
                    attributed_to_founder=True,
                )
            pending.append(_PendingRecovery(pillar_key, source_text, f"a founder-outcome claim: {claim.prior_entity_name} ({outcome_type.value})", _build))

    for claim in extraction.capabilities:
        if not claim.capability_label:
            continue
        # Fix #1: no reliable proper-noun anchor exists for a capability
        # claim (capability_label is an LLM paraphrase, not a literal
        # source term) -- tier-1 anchor recovery is skipped by passing
        # anchor=None; only the model's own quote or a tier-2 correction
        # retry can ground a capability claim.
        quote, recovered = _grounded_or_recovered(claim.verbatim_quote, None, source_text)
        if quote is not None:
            if _is_financial_operational_boilerplate(quote):
                continue
            observations.append(ProductCapabilityObservation(
                **_base_kwargs(next_id("PCAP"), quote, recovered=recovered),
                capability_label=claim.capability_label[:200],
                shipped=bool(claim.shipped),
            ))
        else:
            def _build(q: str, claim=claim) -> EvidenceBase | None:
                if _is_financial_operational_boilerplate(q):
                    return None
                return ProductCapabilityObservation(
                    **_base_kwargs(next_id("PCAP"), q, recovered=True),
                    capability_label=claim.capability_label[:200],
                    shipped=bool(claim.shipped),
                )
            pending.append(_PendingRecovery(pillar_key, source_text, f'a shipped-capability claim: "{claim.capability_label}"', _build))

    for claim in extraction.contracts:
        try:
            contract_type = CustomerType(claim.contract_type)
        except ValueError:
            continue
        quote, recovered = _grounded_or_recovered(claim.verbatim_quote, claim.named_customer, source_text)
        if quote is not None:
            observations.append(CommercialContractObservation(
                **_base_kwargs(next_id("CONTR"), quote, recovered=recovered),
                contract_type=contract_type,
                named_customer=(claim.named_customer or None),
                renewal_evidence=bool(claim.renewal_evidence),
            ))
        else:
            def _build(q: str, claim=claim, contract_type=contract_type) -> EvidenceBase:
                return CommercialContractObservation(
                    **_base_kwargs(next_id("CONTR"), q, recovered=True),
                    contract_type=contract_type,
                    named_customer=(claim.named_customer or None),
                    renewal_evidence=bool(claim.renewal_evidence),
                )
            detail = f"a commercial-contract claim ({contract_type.value}"
            detail += f", customer {claim.named_customer})" if claim.named_customer else ")"
            pending.append(_PendingRecovery(pillar_key, source_text, detail, _build))

    # Fix #2 -- negative signals. affected_dimension is validated against
    # the REAL dimension vocabulary for THIS pillar (read-only from the
    # frozen engine's DIMENSION_PILLARS) before anything else runs; an
    # invalid/unrecognized dimension is dropped, never guessed or
    # defaulted. No reliable proper-noun anchor exists for a negative
    # claim in general (signal_type is a short category label), so
    # tier-1 recovery is skipped (anchor=None) -- same as capabilities.
    for claim in extraction.negative_signals:
        if not claim.signal_type or not claim.affected_dimension:
            continue
        if claim.affected_dimension not in valid_dims:
            continue
        severity = claim.severity if claim.severity in ("LOW", "MODERATE", "SEVERE") else "MODERATE"
        quote, recovered = _grounded_or_recovered(claim.verbatim_quote, None, source_text)
        if quote is not None:
            observations.append(NegativeSignalObservation(
                **_base_kwargs(next_id("NEG"), quote, recovered=recovered),
                signal_type=claim.signal_type[:200],
                severity=severity,
                affected_dimension=claim.affected_dimension,
            ))
        else:
            def _build(q: str, claim=claim, severity=severity) -> EvidenceBase:
                return NegativeSignalObservation(
                    **_base_kwargs(next_id("NEG"), q, recovered=True),
                    signal_type=claim.signal_type[:200],
                    severity=severity,
                    affected_dimension=claim.affected_dimension,
                )
            pending.append(_PendingRecovery(
                pillar_key, source_text,
                f"a negative/adverse-fact claim ({claim.signal_type}) affecting {claim.affected_dimension}",
                _build,
            ))

    return observations, pending


# ---------------------------------------------------------------------
# Fix #3, tier 2 -- a SINGLE bounded correction-retry LLM call, batched
# across every claim (any pillar, any claim type) that survived
# classification but has no grounded quote after tier-1 anchor recovery.
# Mirrors app/ai/analyze_pillar.py's established "one correction pass"
# pattern: never recursive -- whatever this one call returns is final,
# a claim still ungrounded (or whose recovered quote fails the SAME
# firewall again) is dropped, never retried again. Capped at
# _MAX_CORRECTION_RETRY_ITEMS to bound worst-case prompt size; anything
# beyond the cap is simply dropped, never silently trusted.
# ---------------------------------------------------------------------

_MAX_CORRECTION_RETRY_ITEMS = 40

_CORRECTION_SYSTEM_MESSAGE = """You will be given several previously-\
identified claims about one startup, each paired with the exact source \
text it was drawn from. For EACH claim, your ONLY job is to find the \
exact, word-for-word sentence or clause in that claim's own source text \
that supports it, and return it verbatim -- copied exactly as it \
appears, with no paraphrasing, shortening, correcting, or added words. \
If no sentence in the given source text actually supports the claim, \
return null for it. You are not scoring, judging, re-classifying, or \
adding any new claim -- there is no score field, and any claim not in \
the input list must not appear in your output. Return only valid JSON: \
a list of objects, each with "index" (matching the input) and "quote" \
(the exact verbatim substring, or null)."""


class _CorrectionItem(BaseModel):
    index: int
    quote: str | None = None


def _parse_json_array_from_response(content: str) -> list:
    """Same lenient-fallback spirit as pillar_shared.parse_json_from_response,
    but for a top-level JSON ARRAY response (the correction pass's own
    schema) rather than an object."""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = None
    if parsed is None:
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                return value
    return []


def _attempt_correction_retry(pending: list[_PendingRecovery]) -> list[EvidenceBase]:
    """Never raises -- any failure (call error, malformed response,
    unparseable item) degrades to recovering fewer (or zero) claims,
    exactly like the rest of this adapter's fail-closed discipline. This
    function's own failure must never cascade into discarding the
    claims that WERE already grounded elsewhere in the pipeline."""
    batch = pending[:_MAX_CORRECTION_RETRY_ITEMS]
    if not batch:
        return []

    items_payload = "\n\n".join(
        f"=== CLAIM {i} ===\nClaim: {item.detail}\nSource text:\n{item.source_text}"
        for i, item in enumerate(batch)
    )

    try:
        raw = call_analysis_model(_CORRECTION_SYSTEM_MESSAGE, items_payload, temperature=0.0)
        parsed_items = _parse_json_array_from_response(raw)
    except Exception:
        return []

    recovered: list[EvidenceBase] = []
    for entry in parsed_items:
        if not isinstance(entry, dict):
            continue
        try:
            item = _CorrectionItem(**entry)
        except Exception:
            continue
        if not (0 <= item.index < len(batch)):
            continue
        pending_item = batch[item.index]
        # Never trust the retry's own quote either -- same firewall,
        # re-verified independently.
        if not _quote_is_grounded(item.quote, pending_item.source_text):
            continue
        try:
            built = pending_item.build(item.quote)
        except Exception:
            continue
        if built is not None:
            recovered.append(built)
    return recovered


def classify_evidence_for_v3(
    market: PillarAnalysis,
    team: PillarAnalysis,
    product: PillarAnalysis,
    execution: PillarAnalysis,
    traction: PillarAnalysis,
    id_seed: str,
) -> tuple[EvidenceBase, ...]:
    """
    The classification LLM call(s) this adapter makes (Part 7-permitted
    classification, never scoring) -- one primary call always, plus at
    most one additional bounded correction-retry call (Fix #3 tier 2)
    when grounding is otherwise lost. Financial Health is deliberately
    excluded from the request -- this v1 adapter has no safely-
    classifiable qualitative dimension in that pillar (module
    docstring) -- so no tokens are spent asking about it.
    """
    pillar_texts = {
        "market": _pillar_observed_text(market),
        "team": _pillar_observed_text(team),
        "product": _pillar_observed_text(product),
        "execution": _pillar_observed_text(execution),
        "traction": _pillar_observed_text(traction),
    }

    if not any(pillar_texts.values()):
        return ()

    user_content = "\n\n".join(
        f"=== {name.upper()} EVIDENCE ===\n{text}" if text else f"=== {name.upper()} EVIDENCE ===\n(none)"
        for name, text in pillar_texts.items()
    )
    dimension_hint = "\n".join(
        f"Valid affected_dimension values for {name}: {', '.join(_DIMENSIONS_BY_PILLAR_KEY[name])}"
        for name in pillar_texts
    )
    user_content += (
        "\n\nSchema fields per pillar: competitors (named_competitor, "
        "differentiator_named), customer_demand / customer_value "
        "(outcome_claim, named_customer), founder_experience "
        "(founder_role, experience_type: one of UNRELATED_DOMAIN/"
        "ADJACENT_DOMAIN/DIRECT_DOMAIN/REPEAT_FOUNDER/PRIOR_EXIT, "
        "prior_entity_name), founder_outcomes (prior_entity_name, "
        "outcome_type: one of ACQUIRED/IPO/SHUT_DOWN/STILL_OPERATING), "
        "capabilities (capability_label, shipped -- see the CAPABILITIES "
        "rule above), contracts "
        "(contract_type: one of PAYING/PILOT/SIGNED_CONTRACT_UNPAID/"
        "FREEMIUM_ACTIVE, named_customer, renewal_evidence), "
        "negative_signals (signal_type, severity: one of LOW/MODERATE/"
        "SEVERE, affected_dimension -- see the NEGATIVE SIGNALS rule "
        "above and the valid dimension ids per pillar below). Only Team "
        "evidence should populate founder_experience/founder_outcomes. "
        "Only Market evidence should populate competitors. Return JSON "
        "with top-level keys: market, team, product, execution, traction."
        f"\n\n{dimension_hint}"
    )

    raw = call_analysis_model(_SYSTEM_MESSAGE, user_content, temperature=0.0)
    parsed = parse_json_from_response(raw)

    # Parsed per-pillar rather than as one _ExtractionResult(**parsed)
    # call: a single malformed claim (an unexpected null, an out-of-enum
    # string) anywhere in the model's response must not discard every
    # OTHER pillar's otherwise-valid, correctly-grounded claims. Each
    # pillar that fails to validate degrades to an empty _PillarExtraction
    # (equivalent to "no claims for this pillar"), never a crash and
    # never a fabricated fallback value.
    observations: list[EvidenceBase] = []
    all_pending: list[_PendingRecovery] = []
    for pillar_key in ("market", "team", "product", "execution", "traction"):
        pillar_raw = parsed.get(pillar_key) or {}
        try:
            pillar_extraction = _PillarExtraction(**pillar_raw)
        except Exception:
            continue
        pillar_observations, pillar_pending = _extraction_to_observations(
            pillar_key, pillar_extraction, pillar_texts[pillar_key], f"{id_seed}-{pillar_key}"
        )
        observations.extend(pillar_observations)
        all_pending.extend(pillar_pending)

    if all_pending:
        observations.extend(_attempt_correction_retry(all_pending))

    return tuple(observations)


# The engine's ConfidenceLevel enum values are upper-case ("LOW",
# "MEDIUM", "HIGH", app/ai/sps_v3_engine/types.py); every other
# confidence field in this codebase (app/models/scoring.py's
# ConfidenceLevel, app/models/sps_v3.py's SPSV3ConfidenceLevel) uses
# title case ("Low", "Medium", "High"). This maps engine output to the
# codebase-wide convention -- never the other way around.
_CONFIDENCE_TO_TITLE_CASE = {"LOW": "Low", "MEDIUM": "Medium", "HIGH": "High"}


def _pillar_result_to_model(result) -> SPSV3PillarResult:
    return SPSV3PillarResult(
        pillar=result.pillar,
        strength=(float(result.strength) if result.strength is not None else None),
        coverage_pct=float(result.completeness_pct),
        confidence=_CONFIDENCE_TO_TITLE_CASE[result.confidence.value],
        publishable=result.publishable,
        withhold_reason=result.withhold_reason,
    )


def compute_sps_v3_assessment(
    methodology: SIEMethodologyAnalysis,
    id_seed: str,
) -> SPSV3Assessment | None:
    """
    Entry point called from run_due_diligence() (only when
    sps_v3_enabled() is True). Takes the SIEMethodologyAnalysis V2.1 has
    ALREADY fully computed (market/team/product/execution/traction
    PillarAnalysis objects) and produces the additive sps_v3 field.
    Returns None (never raises) on any classification-call failure --
    Part 8's "if it doesn't support even LIMITED, return INSUFFICIENT" is
    honored by the deterministic engine itself when there is simply no
    evidence; a failed/unparseable LLM call is a different case (adapter
    unavailable, not "no evidence") and degrades to the analysis simply
    having no sps_v3 at all, exactly like an analysis run before this
    field existed -- never a fabricated INSUFFICIENT result standing in
    for an error.
    """
    stage = map_stage(methodology.context.company_stage or methodology.context.funding_stage)

    try:
        observations = classify_evidence_for_v3(
            methodology.market,
            methodology.team,
            methodology.product,
            methodology.execution,
            methodology.traction,
            id_seed=id_seed,
        )
    except Exception:
        return None

    # Fix #2 wiring: classify_evidence_for_v3 returns a single flat tuple
    # mixing positive typed observations and NegativeSignalObservation
    # together -- but the deterministic engine's evaluators only ever
    # consult company.negative_signals (a SEPARATE field from
    # company.evidence; see app/ai/sps_v3_engine/evaluators.py, every
    # eval_* function). They must be split here, not left merged, or
    # every negative signal this adapter extracts would silently never
    # reach the engine.
    positive_observations = tuple(o for o in observations if not isinstance(o, NegativeSignalObservation))
    negative_observations = tuple(o for o in observations if isinstance(o, NegativeSignalObservation))
    bundle = EvidenceBundle(
        company_id=id_seed, stage=stage,
        evidence=positive_observations, negative_signals=negative_observations,
    )

    dimension_results = evaluate_all_dimensions(bundle, DEFAULT_REGISTRY)
    sps_result = evaluate_sps(dimension_results, stage, DEFAULT_REGISTRY)
    ux_state = classify_ux_state(sps_result)

    return SPSV3Assessment(
        engine_version=SPS_V3_ENGINE_VERSION,
        scoring_version=SPS_V3_SCORING_VERSION,
        overall_score=(float(sps_result.sps) if sps_result.sps is not None else None),
        coverage_pct=float(sps_result.coverage.overall_pct),
        confidence=_CONFIDENCE_TO_TITLE_CASE[sps_result.confidence.overall.value],
        assessment_state=ux_state.lower(),
        withhold_reason=sps_result.withhold_reason,
        pillars={p.pillar: _pillar_result_to_model(p) for p in sps_result.pillar_results},
        computed_at=datetime.now(timezone.utc).isoformat(),
    )
