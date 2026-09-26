import hashlib
import time
from datetime import datetime, timezone

from app.ai.summarize import summarize_company
from app.ai.risk_analysis import analyze_risks
from app.ai.memo_generator import generate_investment_memo
from app.ai.structured_analysis import generate_structured_analysis
from app.ai.competitor_anlalysis import analyze_competitors

from app.ai.founder_analysis import analyze_founders
from app.ai.market_analysis import analyze_market
from app.ai.research_enrichment import enrich_research
from app.ai.traction_analysis import analyze_traction
from app.ai.readiness_score import generate_readiness_score
from app.ai.product_analysis import analyze_product
from app.ai.execution_analysis import analyze_execution
from app.ai.financial_analysis import analyze_financials
from app.ai.analyze_pillar import PILLAR_ANALYSIS_MODEL, PILLAR_PROMPT_VERSION
from app.ai.scoring_methodology import SCORING_VERSION
from app.ai.sie_v2_methodology import METHODOLOGY_VERSION, ANCHOR_REGISTRY_VERSION

from app.models.startup import SIEContext
from app.models.analysis_context import AnalysisContext
from app.workflows.sie_assembler import assemble_sie_analysis
from app.ai.sps_v3_adapter import sps_v3_enabled, compute_sps_v3_assessment
from app.ai.concurrency import run_concurrently


# ---------------------------------------------------------------------------
# Portfolio Release Task 7, Phase 3 -- Add Processing-Time Observability.
# Reuses this codebase's existing logging convention (print() to stdout --
# see app/auth.py's own auth-failure diagnostics, CLAUDE.md's own
# description of this as the established mechanism) rather than adding a
# new monitoring service or dependency. One line per stage plus one total
# line, all prefixed the same way so they're trivially greppable
# ("[due_diligence_workflow]") in whatever already collects stdout
# (Render's own log capture in production, a local terminal in dev).
#
# `run_id` is a short (12-hex-char) SHA-256 prefix of company_text --
# deterministic, and reveals nothing about the content (a hash is not
# reversible), so it's safe to log even though company_text itself never
# is. It exists only so multiple stage lines from the SAME analysis can
# be correlated in a log stream where many analyses may be interleaved
# across concurrent requests -- never company text, never a prompt,
# never a research brief, never any credential.
# ---------------------------------------------------------------------------

def _new_run_id(company_text: str) -> str:
    return hashlib.sha256(company_text.encode("utf-8")).hexdigest()[:12]


def _log_stage(run_id: str, stage: str, duration_s: float) -> None:
    print(f"[due_diligence_workflow] run_id={run_id} stage={stage} duration_s={duration_s:.2f}")


def build_provenance_context(
    company_text: str = "",
    search_query: str = "",
    research_brief: str = "",
    sources: list | None = None,
    analysis_type: str = "public",
    evidence_sources: list[str] | None = None,
) -> AnalysisContext:
    """
    Build the provenance record for one analysis (SIE Scoring Reliability
    sprint, Phase 5). model_identifier / prompt_version / scoring_version
    are always stamped (they are static constants, always knowable).
    company_text_hash / search_query / research_brief_snapshot /
    source_snapshot are only populated when the caller actually has live
    research to record -- run_due_diligence() always supplies them; the
    frozen-evidence reliability harness does not, since it intentionally
    bypasses live research and has no new research to attribute.

    Pitch Deck / PDF Ingestion: analysis_type is provenance/display
    metadata only (see AnalysisContext.analysis_type's AnalysisType
    literal) -- it never reaches scoring, evidence, or any pillar
    analysis. Defaults to "public" so every existing caller (text,
    website, calibration, the reliability harness) is unaffected; only
    /analyze-pdf and /analyze pass a non-default value through
    run_due_diligence().

    Unified Multi-Source Analyze Startup: evidence_sources is the real,
    non-mutually-exclusive record of which evidence source TYPES fed this
    analysis (see AnalysisContext.evidence_sources' EvidenceSourceType
    literal, already defined and already list-shaped -- this activates
    it, it doesn't add a new field). Left as None for every caller except
    POST /analyze, so AnalysisContext's own pre-existing default
    (["company_description"]) is unchanged for /analyze-startup,
    /analyze-website, /analyze-pdf, calibration, and the reliability
    harness -- exactly their current (dormant-field) behavior, preserved.
    Like analysis_type, this is provenance/display metadata only.
    """
    kwargs = dict(
        analysis_type=analysis_type,
        # SIE Methodology v2: methodology_version was previously never
        # explicitly set here, so it silently stayed at AnalysisContext's
        # Pydantic default ("1.0") for every analysis, v1 included -- a
        # real provenance gap the v2 implementation gap analysis found and
        # fixes. anchor_registry_version is new in v2: distinguishes "same
        # 28 dimensions, refined anchor" from "different dimension set" if
        # the anchor registry is ever updated independently of the
        # architecture (see app/ai/sie_v2_methodology.py).
        methodology_version=METHODOLOGY_VERSION,
        anchor_registry_version=ANCHOR_REGISTRY_VERSION,
        scoring_version=SCORING_VERSION,
        model_identifier=PILLAR_ANALYSIS_MODEL,
        prompt_version=PILLAR_PROMPT_VERSION,
        company_text_hash=(
            hashlib.sha256(company_text.encode("utf-8")).hexdigest()
            if company_text
            else ""
        ),
        search_query=search_query,
        research_brief_snapshot=research_brief,
        source_snapshot=sources or [],
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )

    if evidence_sources is not None:
        kwargs["evidence_sources"] = evidence_sources

    return AnalysisContext(**kwargs)


def build_sie_methodology_analysis(
    structured_analysis,
    readiness,
    founder_analysis,
    market_analysis,
    product_analysis,
    execution_analysis,
    traction_analysis,
    financial_analysis,
    company_text: str = "",
    search_query: str = "",
    research_brief: str = "",
    sources: list | None = None,
    analysis_type: str = "public",
    evidence_sources: list[str] | None = None,
):
    # generate_structured_analysis() (app/ai/structured_analysis.py) asks the
    # model for a single "stage" field (e.g. "Series A") -- there is no
    # separate "company_stage" or "funding_stage" key in its output. Reading
    # those two keys here always returned None, so both context fields were
    # silently empty on every analysis regardless of what the model actually
    # extracted. Map the one stage signal that exists to both fields; they
    # are the same concept as far as extraction goes today.
    stage = structured_analysis.get("stage") or ""

    context = SIEContext(
    company_name=structured_analysis.get("company_name") or "",
    industry=structured_analysis.get("industry") or "",
    business_model=structured_analysis.get("business_model") or "",
    company_stage=stage,
    funding_stage=stage,
)
    return assemble_sie_analysis(
        context=context,
        market_analysis=market_analysis,
        team_analysis=founder_analysis,
        product_analysis=product_analysis,
        execution_analysis=execution_analysis,
        traction_analysis=traction_analysis,
        financial_analysis=financial_analysis,
        readiness=readiness,
        analysis_context=build_provenance_context(
            company_text=company_text,
            search_query=search_query,
            research_brief=research_brief,
            sources=sources,
            analysis_type=analysis_type,
            evidence_sources=evidence_sources,
        ),
    )


def get_pillar_score(pillar):
    return pillar.score if pillar else None


def assemble_multi_source_text(
    website_text: str | None = None,
    pdf_text: str | None = None,
    user_text: str | None = None,
) -> str:
    """
    Unified Multi-Source Analyze Startup: joins whichever evidence
    sources were actually supplied into ONE labeled company_text blob --
    this is the entire "Evidence/Input Assembly" step. Only sections that
    were actually supplied are included (no empty "=== Pitch Deck ==="
    header when no deck was given). No LLM call, no summarization, no
    second pipeline -- the result is handed to run_due_diligence()
    exactly like any other company_text always has been; the labeling is
    what lets source identity survive into the model's own evidence
    rationale (it can say "the pitch deck states..." vs "the website
    states...") without touching evidence-extraction prompts or the
    Evidence/DimensionEvidence schema, the same way build_enriched_text()
    below already separates "Original Company Information" from
    "Additional Research Context" today.
    """
    sections: list[str] = []

    if website_text:
        sections.append(f"=== Company Website ===\n{website_text}")

    if pdf_text:
        sections.append(f"=== Pitch Deck ===\n{pdf_text}")

    if user_text:
        sections.append(f"=== Additional Company Information ===\n{user_text}")

    return "\n\n".join(sections)


def build_enriched_text(company_text: str, research_context: str) -> str:
    """
    Combine raw company_text with the research brief exactly as
    run_due_diligence() has always done. Factored out so the reliability
    harness (app/reliability/) can freeze one enriched_text and reuse it
    across repeated scoring runs without re-deriving it.
    """
    return f"""
Original Company Information:
{company_text}

Additional Research Context:
{research_context}
"""


def analyze_pillars_from_enriched_text(enriched_text: str) -> dict:
    """
    Run the six independent SIE pillar analyses against already-enriched
    text, without calling live research.

    This is the seam the frozen-evidence reliability harness
    (app/reliability/) uses to repeatedly score the SAME evidence: it
    calls this function directly instead of run_due_diligence(), so no
    live Tavily search or research-enrichment LLM call happens per
    scoring run. Production behavior is unchanged -- run_due_diligence()
    below still always builds enriched_text from live research first and
    calls this same function.

    Portfolio Release Task 7, Phase 2 -- Reduce Analysis Latency: these
    six calls are independent of each other (each reads only
    enriched_text -- confirmed by the Phase 1 audit) and now run
    CONCURRENTLY via run_concurrently() (app/ai/concurrency.py), bounded
    to all six at once -- a small, explicit, conservative bound, not
    unbounded fan-out. Each pillar's own internal evidence-extraction ->
    scoring dependency (app/ai/analyze_pillar.py::analyze_pillar(), and
    that function's own bounded retry/correction-pass behavior via
    call_analysis_model()) is completely unchanged and still runs
    sequentially within that one pillar's own call; only the six
    pillars' relationship TO EACH OTHER changed, from sequential to
    concurrent. Same prompts, same model, same scoring methodology --
    this is an orchestration change only. A failure in any one pillar
    raises (run_concurrently()'s own "fails loud, never partial"
    contract) rather than silently omitting that pillar or returning an
    incomplete analysis.
    """
    return run_concurrently({
        "founder_analysis": lambda: analyze_founders(enriched_text),
        "market_analysis": lambda: analyze_market(enriched_text),
        "product_analysis": lambda: analyze_product(enriched_text),
        "execution_analysis": lambda: analyze_execution(enriched_text),
        "traction_analysis": lambda: analyze_traction(enriched_text),
        "financial_analysis": lambda: analyze_financials(enriched_text),
    })


def run_due_diligence(
    company_text,
    analysis_type: str = "public",
    evidence_sources: list[str] | None = None,
):
    # analysis_type / evidence_sources are provenance/display metadata
    # only (see build_provenance_context above) -- they flow straight
    # through to AnalysisContext and never influence research, pillar
    # analysis, or scoring. Defaults keep every pre-existing caller
    # (text, website, calibration, the CLI) behaving exactly as before;
    # only /analyze-pdf and /analyze pass non-default values.
    run_id = _new_run_id(company_text)
    pipeline_started = time.monotonic()

    stage_started = time.monotonic()
    research_result = enrich_research(company_text)
    _log_stage(run_id, "research", time.monotonic() - stage_started)

    research_context = research_result["research_brief"]
    sources = research_result["sources"]
    search_query = research_result["search_query"]

    enriched_text = build_enriched_text(company_text, research_context)

    # Portfolio Release Task 7, Phase 2: these five calls are independent
    # of each other (each reads only enriched_text -- confirmed by the
    # Phase 1 audit) and now run concurrently via the same
    # run_concurrently() helper analyze_pillars_from_enriched_text() uses
    # below, bounded to all five at once. Same functions, same
    # arguments, same outputs -- only the orchestration (sequential ->
    # concurrent) changed. A failure in any one of them raises rather
    # than silently omitting it.
    stage_started = time.monotonic()
    free_form_results = run_concurrently({
        "summary": lambda: summarize_company(enriched_text),
        "risk_analysis": lambda: analyze_risks(enriched_text),
        "competitor_analysis": lambda: analyze_competitors(enriched_text),
        "memo": lambda: generate_investment_memo(enriched_text),
        "structured_analysis": lambda: generate_structured_analysis(enriched_text),
    })
    _log_stage(run_id, "free_form_calls", time.monotonic() - stage_started)
    summary = free_form_results["summary"]
    risk_analysis = free_form_results["risk_analysis"]
    competitor_analysis = free_form_results["competitor_analysis"]
    memo = free_form_results["memo"]
    structured_analysis = free_form_results["structured_analysis"]

    stage_started = time.monotonic()
    pillar_results = analyze_pillars_from_enriched_text(enriched_text)
    _log_stage(run_id, "pillar_analyses", time.monotonic() - stage_started)
    founder_analysis = pillar_results["founder_analysis"]
    market_analysis = pillar_results["market_analysis"]
    product_analysis = pillar_results["product_analysis"]
    execution_analysis = pillar_results["execution_analysis"]
    traction_analysis = pillar_results["traction_analysis"]
    financial_analysis = pillar_results["financial_analysis"]

    initial_readiness = None

    sie_analysis = build_sie_methodology_analysis(
        structured_analysis=structured_analysis,
        readiness=initial_readiness,
        founder_analysis=founder_analysis,
        market_analysis=market_analysis,
        product_analysis=product_analysis,
        execution_analysis=execution_analysis,
        traction_analysis=traction_analysis,
        financial_analysis=financial_analysis,
        company_text=company_text,
        search_query=search_query,
        research_brief=research_context,
        sources=sources,
        analysis_type=analysis_type,
        evidence_sources=evidence_sources,
    )

    market_score = get_pillar_score(sie_analysis.market)
    team_score = get_pillar_score(sie_analysis.team)
    product_score = get_pillar_score(sie_analysis.product)
    execution_score = get_pillar_score(sie_analysis.execution)
    traction_score = get_pillar_score(sie_analysis.traction)
    financial_score = get_pillar_score(sie_analysis.financial_health)
    overall_score = sie_analysis.startup_intelligence_score

    stage_started = time.monotonic()
    readiness = generate_readiness_score(
        market_score,
        team_score,
        product_score,
        execution_score,
        traction_score,
        financial_score,
        overall_score,
    )
    _log_stage(run_id, "readiness_score", time.monotonic() - stage_started)

    sie_analysis = build_sie_methodology_analysis(
        structured_analysis=structured_analysis,
        readiness=readiness,
        founder_analysis=founder_analysis,
        market_analysis=market_analysis,
        product_analysis=product_analysis,
        execution_analysis=execution_analysis,
        traction_analysis=traction_analysis,
        financial_analysis=financial_analysis,
        company_text=company_text,
        search_query=search_query,
        research_brief=research_context,
        sources=sources,
        analysis_type=analysis_type,
        evidence_sources=evidence_sources,
    )

    overall_score = sie_analysis.startup_intelligence_score

    # Portfolio Release Task 7, Phase 2 -- One Production Scoring
    # Methodology: sps_v3_enabled() now defaults OFF (SPS_ENGINE_VERSION
    # unset, or anything other than exactly "v3", selects V2.1-only;
    # explicit "v3" re-enables it) -- reversing the prior phase's
    # "Canonical Activation" default now that the Phase 1 audit found no
    # product surface (Rankings/Search/Discovery/Compare/Score History)
    # actually reads sps_v3, so every analysis was paying for an extra
    # sequential LLM call for an assessment nothing downstream used.
    # NOTHING above this line changes either way -- the V2.1 pipeline
    # that produced overall_score/investment_score/readiness runs
    # unconditionally, completely unaffected by this flag; it is not
    # replaced, only supplemented. When enabled, this makes exactly ONE
    # additional LLM call (a classification pass over evidence V2.1
    # already extracted -- no new research, no new Tavily call) and can
    # only ADD sie_analysis.sps_v3; it never modifies
    # market_score/team_score/.../overall_score or any other field
    # already assembled above. V3's own code (app/ai/sps_v3_adapter.py,
    # app/ai/sps_v3_engine/) and every already-persisted analysis's
    # sps_v3 field are completely unchanged -- see
    # sps_v3_enabled()'s own docstring for the full record.
    if sps_v3_enabled():
        stage_started = time.monotonic()
        sie_analysis.sps_v3 = compute_sps_v3_assessment(
            sie_analysis,
            id_seed=(structured_analysis.get("company_name") or "STARTUP")[:40],
        )
        _log_stage(run_id, "sps_v3_assessment", time.monotonic() - stage_started)

    _log_stage(run_id, "total", time.monotonic() - pipeline_started)

    investment_score = {
        "market_score": market_score,
        "team_score": team_score,
        "product_score": product_score,
        "competition_score": execution_score,
        "traction_score": traction_score,
        "financial_score": financial_score,
        "overall_score": overall_score,
        "recommendation": None,
    }

    return {
        "summary": summary,
        "risk_analysis": risk_analysis,
        "competitor_analysis": competitor_analysis,
        "memo": memo,
        "structured_analysis": structured_analysis,
        "investment_score": investment_score,
        "readiness": readiness,
        "readiness_score": readiness.get("readiness_score"),
        "readiness_summary": readiness.get("readiness_summary"),
        "founder_analysis": founder_analysis,
        "market_analysis": market_analysis,
        "sources": sources,
        "traction_analysis": traction_analysis,
        "market_score": market_score,
        "team_score": team_score,
        "product_score": product_score,
        "competition_score": execution_score,
        "traction_score": traction_score,
        "financial_score": financial_score,
        "overall_score": overall_score,
        "recommendation": None,
        "sie_analysis": sie_analysis,
    }