"""
Versioned parameter set for the evidence_engine.v1 methodology.

Every value in this module is a CALIBRATION REQUIRED placeholder
(NEW_ENGINE_SPEC.md Part 6.7) -- reasoned to be plausible enough to
exercise the mechanism end-to-end against this slice's offline fixtures,
never asserted as a final, calibrated number. See
`docs/methodology/NEW_ENGINE_CALIBRATION_REPORT.md` for the reasoning
behind each value below and what evidence from the expanded fixture set
supports (or merely fails to contradict) it. `docs/methodology/
NEW_ENGINE_CALIBRATION.md` remains the plan for how a REAL calibration
pass, against a much larger cohort, would eventually replace these.
"""

from __future__ import annotations

PARAMETER_VERSION = "evidence_engine.v1-provisional-6"

# --- Pillar-level publishability gates (spec Part 6.2) ----------------------
# Unchanged from the first vertical slice -- Task 9's expanded fixture set
# (Notion, Linear, Pathlight, DupliCo, Auroraflow) did not surface a reason
# to move either gate; see the calibration report's "Gate sensitivity"
# section for what was actually checked.
MIN_PILLAR_COVERAGE_PCT: float = 40.0
MIN_SCORED_DIMENSIONS_PER_PILLAR: int = 2

# --- Product & Technology pillar (spec Part 3.3) ----------------------------
PRODUCT_TECHNOLOGY_PILLAR = "Product & Technology"

PRODUCT_TECHNOLOGY_DIMENSION_WEIGHTS: dict[str, float] = {
    "product_existence_maturity": 0.25,
    "differentiation_claim_corroboration": 0.25,
    "technical_depth_signal": 0.25,
    "defensibility_signal": 0.25,
}

PRODUCT_TECHNOLOGY_STALENESS_DAYS: dict[str, int] = {
    "product_existence_maturity": 365,        # 12 months
    "differentiation_claim_corroboration": 548,  # ~18 months
    "technical_depth_signal": 730,              # 24 months
    "defensibility_signal": 730,                 # 24 months
}

# Stage-signal claims are treated more generously than a scored dimension's
# own evidence -- a disclosed funding round or founding date does not
# become "wrong" quickly the way a usage/retention claim can. Reasoned
# placeholder, not calibrated.
STAGE_SIGNAL_STALENESS_DAYS: int = 365 * 5

# --- Computed dimension: Product Existence & Maturity -----------------------
# Deliberately NOT stage-indexed (unlike the three Classified dimensions
# below) -- reasoned, not an oversight: whether an independently-observable
# product artifact exists is a binary structural fact whose meaning does
# not obviously vary by company stage the way a qualitative judgment does.
# Calibration (report, Part 3) found no case in the expanded fixture set
# that contradicts treating this uniformly.
PRODUCT_EXISTENCE_SCORE: float = 7.0

# --- Classified dimensions: stage-tiered label -> score lookup tables -------
# Design decision (spec Part 4.2, restated for this pillar): the SAME
# positive label is worth MORE at an earlier stage, where it is less
# expected, and worth LESS at a later stage, where the same evidence is
# closer to a baseline expectation -- monotonically descending
# early -> growth -> established. This is the opposite of an "automatic
# bonus" for established companies (Task 9's own explicit prohibition);
# if anything, established companies face a higher bar for the identical
# evidence to earn the identical score. See the calibration report for the
# worked comparison (Notion vs. Pathlight) that tests this directly.
#
# A label that never scores (DISPUTED / UNCORROBORATED / NONE_DISCLOSED /
# NONE) has no tier entries at all -- there is no number to look up
# because the dimension is Unscored regardless of stage.

DIFFERENTIATION_LABEL_SCORES: dict[str, dict[str, float]] = {
    "CORROBORATED": {"early": 8.0, "growth": 7.0, "established": 6.0},
}

TECHNICAL_DEPTH_LABEL_SCORES: dict[str, dict[str, float]] = {
    "SUBSTANTIAL": {"early": 9.0, "growth": 8.0, "established": 7.0},
    "SOME": {"early": 6.5, "growth": 5.5, "established": 4.5},
}
TECHNICAL_DEPTH_SUBSTANTIAL_MIN_FACTS = 3
TECHNICAL_DEPTH_SOME_MIN_FACTS = 1

DEFENSIBILITY_LABEL_SCORES: dict[str, dict[str, float]] = {
    "CORROBORATED_MOAT": {"early": 8.0, "growth": 7.0, "established": 6.0},
}

# --- Market Opportunity pillar (Task 13; spec Part 3.3) ---------------------
# All four dimensions are Classified (spec Part 3.3's own table lists no
# Computed dimension for this pillar). Deliberately, explicitly
# STAGE-INDEPENDENT (documented in full in market_opportunity.py's own
# module docstring): Market Opportunity measures the external market, not
# the assessed company, and a real market fact (a $10B category, a named
# regulatory catalyst) does not change meaning depending on which
# company's report happens to cite it. Task 13, item 6's own instruction
# ("do not automatically give younger companies easier market scores")
# is satisfied structurally here, not by a calibrated-flat table: there is
# no stage input to this pillar's scoring path at all.
MARKET_OPPORTUNITY_PILLAR = "Market Opportunity"

MARKET_OPPORTUNITY_DIMENSION_WEIGHTS: dict[str, float] = {
    "market_definition_size": 0.30,
    "market_growth_signal": 0.25,
    "timing_catalyst": 0.20,
    "competitive_landscape_position": 0.25,
}

MARKET_OPPORTUNITY_STALENESS_DAYS: dict[str, int] = {
    "market_definition_size": 730,        # 24 months (spec Part 3.3)
    "market_growth_signal": 548,           # 18 months (spec Part 3.3)
    "timing_catalyst": 730,                 # 24 months (spec Part 3.3)
    "competitive_landscape_position": 548,   # 18 months (spec Part 3.3)
}

# Market Definition & Size: a band, not a raw number (Design Principle 6 --
# no dimension ever lets the AI emit a number directly). The mock/real
# classifier reads a magnitude cue (Claim.structured_fact, propagated
# through EvidenceItem -- Task 13's shared-layer extension) and picks the
# closed band label; deterministic code owns the label->score mapping and
# the band cutoffs below. CALIBRATION REQUIRED, reasoned only from the
# legacy Market Size rubric's own qualitative band language ("massive
# global market" / "moderate market" / "limited market").
MARKET_SIZE_NARROW_MAX_USD: float = 1_000_000_000        # <$1B
MARKET_SIZE_SUBSTANTIAL_MAX_USD: float = 10_000_000_000   # $1B-$10B; >$10B is LARGE

MARKET_SIZE_LABEL_SCORES: dict[str, float] = {
    "NARROW": 4.0,
    "SUBSTANTIAL": 6.5,
    "LARGE": 8.5,
}

# Market Growth Signal: same banding approach, over a disclosed category
# growth-rate percentage.
MARKET_GROWTH_SLOW_MAX_PCT: float = 10.0      # <10%/yr
MARKET_GROWTH_MODERATE_MAX_PCT: float = 25.0   # 10-25%/yr; >25% is FAST

MARKET_GROWTH_LABEL_SCORES: dict[str, float] = {
    "SLOW": 4.0,
    "MODERATE": 6.5,
    "FAST": 8.5,
}

# Timing & Catalyst: binary in spirit (spec Part 3.3's own admissible-
# evidence column describes a single named, dated catalyst, not a
# magnitude to bucket) -- GENERIC_ONLY (an independent claim exists but
# names no specific catalyst -- exactly the "fast-growing industry"/"huge
# opportunity" style claim Task 13, item 4 explicitly warns against
# treating as evidence) is Unscored, distinct from no evidence at all.
TIMING_CATALYST_LABEL_SCORES: dict[str, float] = {
    "SPECIFIC_CATALYST": 7.5,
}

# Competitive Landscape Position: a read on MARKET STRUCTURE (how
# fragmented/concentrated the named competitive set is), never a
# company-vs-competitor differentiation judgment -- that question belongs
# to Product & Technology's own Differentiation Claim Corroboration (spec
# Part 3.1's double-counting prohibition, restated for this pillar in
# market_opportunity.py). A fragmented market (no dominant named
# incumbent) represents more open opportunity than a concentrated one
# (an entrenched leader) -- a reasoned, explicitly stated interpretation,
# not asserted as universal investment doctrine, and itself CALIBRATION
# REQUIRED like every other value here.
COMPETITIVE_LANDSCAPE_LABEL_SCORES: dict[str, float] = {
    "FRAGMENTED": 7.5,
    "CONCENTRATED": 4.5,
}

# --- Team & Leadership pillar (Task 14; spec Part 3.3) ----------------------
# All three dimensions are Classified (spec Part 3.3's own table lists no
# Computed dimension here). Founder Relevant Experience and Public Track
# Record are documented, FIXED biographical facts -- a prior exit or a
# prior domain role means the same thing regardless of this company's
# current stage -- so both are stage-independent, exactly like Market
# Opportunity's own reasoning, restated here for a different reason (there
# it was "the market doesn't change meaning by stage"; here it is "a past
# fact about a person doesn't change meaning by this company's current
# stage"). Leadership Composition is the one dimension the approved
# spec's own wording ("explicit confirmation the founder(s) are the only
# leadership" as a legitimate, non-penalized state) supports genuine stage
# sensitivity for -- documented in full in team_leadership.py's own
# module docstring, including the explicit guard against the two
# prohibited directions (never reward smallness, never punish an
# early-stage company for an executive bench it would be unreasonable to
# have yet).
TEAM_LEADERSHIP_PILLAR = "Team & Leadership"

TEAM_LEADERSHIP_DIMENSION_WEIGHTS: dict[str, float] = {
    "founder_relevant_experience": 0.40,
    "leadership_composition": 0.30,
    "public_track_record": 0.30,
}

TEAM_LEADERSHIP_STALENESS_DAYS: dict[str, int] = {
    "founder_relevant_experience": 1095,   # 36 months (spec Part 3.3 -- "biographical facts age slowly")
    "leadership_composition": 365,          # 12 months (spec Part 3.3)
    "public_track_record": 1095,             # 36 months (spec Part 3.3)
}

# Founder Relevant Experience: NONE_DISCLOSED has no table entry (Unscored
# by construction -- see team_leadership.py's own documented reading of
# "NONE_DISCLOSED" as "no RELEVANT experience established," covering both
# a genuine absence of disclosed experience and disclosed-but-topically-
# unrelated experience, a documented ambiguity resolution per Task 14's
# own "narrowest reasonable decision" instruction). ADJACENT < DIRECT,
# reasoned placeholders.
FOUNDER_EXPERIENCE_LABEL_SCORES: dict[str, float] = {
    "ADJACENT": 5.5,
    "DIRECT": 8.0,
}

# Leadership Composition: stage-tiered, per the reasoning above.
# NONE_BEYOND_FOUNDERS is pinned to the SAME value across every tier,
# deliberately -- it is a confirmed structural fact, not evidence of
# strength or weakness at any stage, and must be neither rewarded nor
# punished for being small. SOME_HIRES/SUBSTANTIAL_HIRES genuinely vary
# by tier, in the same direction as every other stage-tiered table in
# this engine (the same fact is more remarkable, and scores higher, at an
# earlier stage where it is less expected).
LEADERSHIP_COMPOSITION_LABEL_SCORES: dict[str, dict[str, float]] = {
    "NONE_BEYOND_FOUNDERS": {"early": 5.0, "growth": 5.0, "established": 5.0},
    "SOME_HIRES": {"early": 7.0, "growth": 6.0, "established": 5.0},
    "SUBSTANTIAL_HIRES": {"early": 9.0, "growth": 8.0, "established": 7.0},
}
LEADERSHIP_SOME_HIRES_MIN_COUNT = 1
LEADERSHIP_SUBSTANTIAL_HIRES_MIN_COUNT = 3

# Public Track Record: an actual prior exit is a stronger, more concrete,
# more checkable accomplishment than merely having held a role at a
# venture-backed company -- PRIOR_VENTURE_ROLE < PRIOR_EXIT. Stage-
# independent (a fixed biographical fact).
PUBLIC_TRACK_RECORD_LABEL_SCORES: dict[str, float] = {
    "PRIOR_VENTURE_ROLE": 6.0,
    "PRIOR_EXIT": 8.5,
}

# --- Confidence and source reliability (spec Part 6.4) ----------------------
# A dimension's own confidence weighs THREE inputs, none of which is score:
# (1) the support_status mix of its admissible evidence, (2) corroboration
# (independence-group count), (3) SOURCE RELIABILITY -- new in this
# calibration pass, previously implicit. Independent reporting and public
# filings are weighted above a company's own disclosure and above an
# aggregator/directory restatement, since the latter two are either
# self-interested or frequently just a restatement of the former (spec
# Part 5.2/5.3). Weights, not final: CALIBRATION REQUIRED.
SOURCE_RELIABILITY_WEIGHT: dict[str, float] = {
    "independent_reporting": 1.0,
    "public_filing": 1.0,
    "product_documentation": 0.8,
    "aggregator_or_directory": 0.6,
    # Task 12, item 3: an anonymous public forum/comment-section post is
    # independent of the company (see INDEPENDENT_SOURCE_TYPES, models.py)
    # but not accountable/attributable the way bylined reporting is --
    # weighted below every attributable source type, above only the
    # company's own word. Placed here, not folded into
    # "independent_reporting", specifically so the two questions ("is this
    # independent of the company" vs. "how much should this specific
    # source be trusted") stay separately answerable, per Task 11 §5.5 and
    # Task 12's own "separate X from Y" framing.
    "community_commentary": 0.5,
    "company_disclosure": 0.4,
    "other": 0.3,
}

# --- Evidence-independence verification (Task 10, item 1) ------------------
# Jaccard token-overlap thresholds over two claims' own text
# (excerpt/claim_text). >= DUPLICATE means "confidently the same
# underlying disclosure" (syndication, a copied press release); >=
# UNKNOWN but below DUPLICATE means "cannot confidently establish either
# way" (per Task 10's own instruction, treated conservatively -- not
# counted as an additional distinct fact); below UNKNOWN means
# independent. Both CALIBRATION REQUIRED: chosen to be structurally
# reasonable (near-verbatim text is almost certainly a restatement;
# moderate overlap is genuinely ambiguous without real-world data on how
# similar independently-written coverage of the same real event actually
# tends to be) rather than derived from any measured corpus.
PROVENANCE_DUPLICATE_SIMILARITY_THRESHOLD: float = 0.75
PROVENANCE_UNKNOWN_SIMILARITY_THRESHOLD: float = 0.40

CONFIDENCE_MIN_CORROBORATION_GROUPS_FOR_HIGH: int = 2
# A dimension's admissible evidence must average at least this much
# reliability (0-1 scale, weighted by claim) to be eligible for HIGH
# confidence, regardless of corroboration count -- prevents e.g. two
# corroborating aggregator-only restatements of the same weak-reliability
# source from reaching HIGH purely on count.
CONFIDENCE_MIN_RELIABILITY_FOR_HIGH: float = 0.9
CONFIDENCE_MIN_RELIABILITY_FOR_MEDIUM: float = 0.5
