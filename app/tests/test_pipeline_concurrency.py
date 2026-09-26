"""
Portfolio Release Task 7, Phase 2 -- Reduce Analysis Latency.
Regression coverage for app/ai/concurrency.py::run_concurrently() and
its three call sites (app/workflows/due_diligence_workflow.py's pillar
and free-form call groups, app/ai/research_enrichment.py's Tavily search
group), plus app/ai/sps_v3_adapter.py::sps_v3_enabled()'s flipped
default (Part 1 -- One Production Scoring Methodology).

No real LLM/Tavily calls anywhere in this file -- every AI-calling
function due_diligence_workflow.py/research_enrichment.py import is
monkeypatched at its point of use (the importing module's own
namespace, since `from x import y` binds a new name there that does not
follow a later reassignment of x.y) to a deterministic, sleep-based
stand-in. Sleep durations are real (this is what proves genuine
concurrency, the same reason test_analyze_unified_concurrency.py uses
real threads/timing instead of asserting on mocked call order alone),
just far shorter than a real gpt-4.1-mini call.

Run with:
    python -m app.tests.test_pipeline_concurrency
"""

import io
import time
from contextlib import redirect_stdout

from app.ai.concurrency import run_concurrently
from app.ai.sps_v3_adapter import sps_v3_enabled
from app.models.startup import PillarAnalysis

import app.workflows.due_diligence_workflow as workflow
import app.ai.research_enrichment as research_enrichment


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------------------
# run_concurrently() itself
# ---------------------------------------------------------------------------

def test_run_concurrently_is_actually_concurrent_not_sequential() -> None:
    """Six tasks that each sleep 0.2s: sequential would take >=1.2s;
    concurrent should take well under half that. This is a real timing
    assertion, not just a call-count check -- the same discipline
    test_analyze_unified_concurrency.py already uses for the same reason
    (a mocked call order alone can't distinguish real concurrency from
    sequential execution that merely LOOKS parallel in source code)."""
    delay = 0.2
    tasks = {f"task_{i}": (lambda d=delay: _sleep_and_return(d, d)) for i in range(6)}

    started = time.monotonic()
    results = run_concurrently(tasks)
    elapsed = time.monotonic() - started

    expect(len(results) == 6, f"Expected 6 results, got {len(results)}")
    expect(elapsed < delay * 3, f"Expected concurrent execution (<{delay * 3}s for 6x{delay}s tasks), took {elapsed:.2f}s")


def _sleep_and_return(delay: float, value):
    time.sleep(delay)
    return value


def test_run_concurrently_result_mapping_is_deterministic_regardless_of_completion_order() -> None:
    """Same controlled inputs, deliberately reversed completion order
    between the two runs (task 'a' is slowest in run 1, fastest in run
    2) -- the returned {key: result} mapping must be byte-identical
    either way. This is the literal "same controlled AI outputs produce
    the same scores regardless of completion order" requirement, at the
    level of the shared primitive every call site uses."""
    def make_tasks(delays: dict[str, float]) -> dict:
        return {key: (lambda d=d, k=key: _sleep_and_return(d, f"result-for-{k}")) for key, d in delays.items()}

    run_1 = run_concurrently(make_tasks({"a": 0.15, "b": 0.05, "c": 0.10}))
    run_2 = run_concurrently(make_tasks({"a": 0.05, "b": 0.15, "c": 0.10}))

    expect(run_1 == run_2, f"Expected identical result mappings regardless of completion order, got {run_1} vs {run_2}")
    expect(list(run_1.keys()) == ["a", "b", "c"], "Result key order must match the tasks dict's own insertion order")


def test_run_concurrently_fails_loud_never_returns_a_partial_result() -> None:
    """One task raises -- the whole call must raise, never silently
    return a dict missing that key (or any key)."""
    ran = []

    def failing_task():
        ran.append("failing")
        raise RuntimeError("simulated provider failure")

    def ok_task(name):
        time.sleep(0.05)
        ran.append(name)
        return name

    raised = False
    try:
        run_concurrently({
            "ok_1": lambda: ok_task("ok_1"),
            "failing": failing_task,
            "ok_2": lambda: ok_task("ok_2"),
        })
    except RuntimeError as error:
        raised = True
        expect("simulated provider failure" in str(error), f"Expected the original exception to propagate, got {error!r}")

    expect(raised, "run_concurrently() must raise when any task fails, never return a partial dict")
    # Every task was still submitted and allowed to run -- nothing was
    # silently cancelled/abandoned mid-flight just because one failed.
    expect(set(ran) == {"failing", "ok_1", "ok_2"}, f"Expected every task to have actually run, got {ran}")


def test_run_concurrently_respects_a_conservative_max_workers_bound() -> None:
    """A real, honest bound -- never more than max_workers tasks run at
    the same instant, even when more are queued."""
    import threading

    active = 0
    peak_active = 0
    lock = threading.Lock()

    def tracked_task():
        nonlocal active, peak_active
        with lock:
            active += 1
            peak_active = max(peak_active, active)
        time.sleep(0.1)
        with lock:
            active -= 1
        return None

    tasks = {f"task_{i}": tracked_task for i in range(8)}
    run_concurrently(tasks, max_workers=2)

    expect(peak_active <= 2, f"Expected at most 2 tasks running at once with max_workers=2, observed peak {peak_active}")


def test_run_concurrently_empty_tasks_returns_empty_dict() -> None:
    expect(run_concurrently({}) == {}, "run_concurrently({}) must return {} without error")


# ---------------------------------------------------------------------------
# sps_v3_enabled(): Part 1 -- One Production Scoring Methodology
# ---------------------------------------------------------------------------

def test_sps_v3_disabled_by_default() -> None:
    import os
    original = os.environ.pop("SPS_ENGINE_VERSION", None)
    try:
        expect(sps_v3_enabled() is False, "sps_v3_enabled() must default to False (V3 off) with SPS_ENGINE_VERSION unset")
    finally:
        if original is not None:
            os.environ["SPS_ENGINE_VERSION"] = original


def test_sps_v3_enabled_only_when_explicitly_set_to_v3() -> None:
    import os
    original = os.environ.get("SPS_ENGINE_VERSION")
    try:
        os.environ["SPS_ENGINE_VERSION"] = "v3"
        expect(sps_v3_enabled() is True, "SPS_ENGINE_VERSION=v3 must explicitly re-enable V3")

        os.environ["SPS_ENGINE_VERSION"] = "v2_1"
        expect(sps_v3_enabled() is False, "SPS_ENGINE_VERSION=v2_1 must keep V3 off (unchanged, explicit legacy-only)")

        os.environ["SPS_ENGINE_VERSION"] = "some_typo"
        expect(sps_v3_enabled() is False, "An unrecognized value must fail closed to V3-off, never silently to some third state")
    finally:
        if original is None:
            os.environ.pop("SPS_ENGINE_VERSION", None)
        else:
            os.environ["SPS_ENGINE_VERSION"] = original


# ---------------------------------------------------------------------------
# analyze_pillars_from_enriched_text(): the six-pillar concurrent group
# ---------------------------------------------------------------------------

def test_six_pillars_run_concurrently_with_correct_deterministic_shape() -> None:
    delay = 0.15
    fake_scores = {
        "founder_analysis": 7.1, "market_analysis": 8.1, "product_analysis": 6.6,
        "execution_analysis": 6.5, "traction_analysis": 6.0, "financial_analysis": 5.7,
    }

    originals = {
        "analyze_founders": workflow.analyze_founders,
        "analyze_market": workflow.analyze_market,
        "analyze_product": workflow.analyze_product,
        "analyze_execution": workflow.analyze_execution,
        "analyze_traction": workflow.analyze_traction,
        "analyze_financials": workflow.analyze_financials,
    }

    def make_fake(key: str, score: float):
        def fake(_enriched_text: str) -> PillarAnalysis:
            time.sleep(delay)
            return PillarAnalysis(score=score, confidence="Medium", summary=f"fake {key}")
        return fake

    workflow.analyze_founders = make_fake("founder_analysis", fake_scores["founder_analysis"])
    workflow.analyze_market = make_fake("market_analysis", fake_scores["market_analysis"])
    workflow.analyze_product = make_fake("product_analysis", fake_scores["product_analysis"])
    workflow.analyze_execution = make_fake("execution_analysis", fake_scores["execution_analysis"])
    workflow.analyze_traction = make_fake("traction_analysis", fake_scores["traction_analysis"])
    workflow.analyze_financials = make_fake("financial_analysis", fake_scores["financial_analysis"])

    try:
        started = time.monotonic()
        results = workflow.analyze_pillars_from_enriched_text("fake enriched text")
        elapsed = time.monotonic() - started

        expect(elapsed < delay * 3, f"Expected the six pillar calls to run concurrently (<{delay * 3}s), took {elapsed:.2f}s")
        expect(set(results.keys()) == set(fake_scores.keys()), f"Expected all six pillar keys, got {list(results.keys())}")
        for key, expected_score in fake_scores.items():
            expect(results[key].score == expected_score, f"{key} must carry its own correct score ({expected_score}), got {results[key].score}")
    finally:
        for name, fn in originals.items():
            setattr(workflow, name, fn)


def test_six_pillars_fail_loud_if_one_raises() -> None:
    originals = {
        "analyze_founders": workflow.analyze_founders,
        "analyze_market": workflow.analyze_market,
        "analyze_product": workflow.analyze_product,
        "analyze_execution": workflow.analyze_execution,
        "analyze_traction": workflow.analyze_traction,
        "analyze_financials": workflow.analyze_financials,
    }

    def ok(_text: str) -> PillarAnalysis:
        time.sleep(0.05)
        return PillarAnalysis(score=7.0)

    def failing(_text: str) -> PillarAnalysis:
        raise RuntimeError("simulated OpenAI failure for one pillar")

    workflow.analyze_founders = ok
    workflow.analyze_market = ok
    workflow.analyze_product = failing
    workflow.analyze_execution = ok
    workflow.analyze_traction = ok
    workflow.analyze_financials = ok

    try:
        raised = False
        try:
            workflow.analyze_pillars_from_enriched_text("fake enriched text")
        except RuntimeError:
            raised = True

        expect(raised, "A failure in one pillar must raise, never silently return a five-of-six partial analysis")
    finally:
        for name, fn in originals.items():
            setattr(workflow, name, fn)


# ---------------------------------------------------------------------------
# enrich_research(): the four-category Tavily search concurrent group
# ---------------------------------------------------------------------------

def test_research_categories_search_concurrently_and_assemble_deterministically() -> None:
    delay = 0.15
    original_extract_queries = research_enrichment.extract_search_queries
    original_search_web = research_enrichment.search_web

    fake_queries = {
        "overview": "acme overview",
        "market_and_competitors": "acme market",
        "founders_and_leadership": "acme founders",
        "financial_and_funding": "acme funding",
    }

    def fake_extract_search_queries(_company_text: str) -> dict:
        return fake_queries

    def fake_search_web(query: str) -> dict:
        time.sleep(delay)
        return {"research_text": f"[research for: {query}]", "sources": [{"url": f"https://example.com/{query.split()[-1]}", "title": query}]}

    research_enrichment.extract_search_queries = fake_extract_search_queries
    research_enrichment.search_web = fake_search_web

    # openai_client is only reached for the final brief-synthesis call --
    # patch that too so this test makes zero real network calls.
    original_openai_client = research_enrichment.openai_client

    class _FakeMessage:
        content = "[fake synthesized research brief]"

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    class _FakeCompletions:
        def create(self, **_kwargs):
            return _FakeResponse()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeOpenAIClient:
        chat = _FakeChat()

    research_enrichment.openai_client = _FakeOpenAIClient()

    try:
        started = time.monotonic()
        result = research_enrichment.enrich_research("Acme Corp does things.")
        elapsed = time.monotonic() - started

        expect(elapsed < delay * 3, f"Expected the four category searches to run concurrently (<{delay * 3}s), took {elapsed:.2f}s")
        expect(result["research_brief"] == "[fake synthesized research brief]", "Must still synthesize the brief from the (concurrently fetched) research")
        expect(len(result["sources"]) == 4, f"Expected all four categories' sources to be combined, got {len(result['sources'])}")
    finally:
        research_enrichment.extract_search_queries = original_extract_queries
        research_enrichment.search_web = original_search_web
        research_enrichment.openai_client = original_openai_client


# ---------------------------------------------------------------------------
# run_due_diligence(): the full orchestration function, every AI-calling
# dependency mocked with a fixed artificial delay standing in for a real
# gpt-4.1-mini/Tavily call. Proves the free-form-call group's concurrency
# specifically (not yet covered above), and -- the real point of this
# section -- that the same controlled AI outputs, run twice with
# deliberately DIFFERENT per-call delays (so completion order genuinely
# differs between the two runs), produce byte-identical scores. SPS V3
# is deliberately left at its new default (off) -- no SPS_ENGINE_VERSION
# override -- which also doubles as a regression check that Part 1's
# flipped default actually holds inside the real orchestration function,
# not just in a direct call to sps_v3_enabled().
# ---------------------------------------------------------------------------

_FREE_FORM_NAMES = ["summarize_company", "analyze_risks", "analyze_competitors", "generate_investment_memo", "generate_structured_analysis"]
_PILLAR_NAMES = ["analyze_founders", "analyze_market", "analyze_product", "analyze_execution", "analyze_traction", "analyze_financials"]
_ALL_MOCKED_NAMES = ["enrich_research"] + _FREE_FORM_NAMES + _PILLAR_NAMES + ["generate_readiness_score"]


def _install_full_pipeline_mocks(delays: dict[str, float], call_counts: dict[str, int]):
    """Returns the dict of originals to restore, and monkeypatches
    `workflow` in place. `delays` maps mock name -> sleep seconds;
    `call_counts` is mutated in place, one entry per mock name, so the
    test can assert each dependency was called exactly once (concurrency
    must never duplicate or drop a call)."""
    originals = {name: getattr(workflow, name) for name in _ALL_MOCKED_NAMES}

    def record(name: str):
        call_counts[name] = call_counts.get(name, 0) + 1

    def fake_enrich_research(_company_text):
        time.sleep(delays.get("enrich_research", 0.05))
        record("enrich_research")
        return {"research_brief": "fake brief", "sources": [], "search_query": "fake query"}

    def make_free_form_fake(name: str, value):
        def fake(_enriched_text):
            time.sleep(delays.get(name, 0.05))
            record(name)
            return value
        return fake

    def make_pillar_fake(name: str, score: float):
        def fake(_enriched_text):
            time.sleep(delays.get(name, 0.05))
            record(name)
            return PillarAnalysis(score=score, confidence="Medium", summary=f"fake {name}")
        return fake

    def fake_readiness(*_args, **_kwargs):
        time.sleep(delays.get("generate_readiness_score", 0.05))
        record("generate_readiness_score")
        return {"readiness_score": 72, "readiness_summary": "fake readiness", "strengths": [], "weaknesses": []}

    workflow.enrich_research = fake_enrich_research
    workflow.summarize_company = make_free_form_fake("summarize_company", "fake summary")
    workflow.analyze_risks = make_free_form_fake("analyze_risks", "fake risks")
    workflow.analyze_competitors = make_free_form_fake("analyze_competitors", "fake competitors")
    workflow.generate_investment_memo = make_free_form_fake("generate_investment_memo", "fake memo")
    workflow.generate_structured_analysis = make_free_form_fake(
        "generate_structured_analysis",
        {"company_name": "Acme Corp", "industry": "SaaS", "business_model": "B2B", "stage": "Seed"},
    )
    workflow.analyze_founders = make_pillar_fake("analyze_founders", 7.1)
    workflow.analyze_market = make_pillar_fake("analyze_market", 8.1)
    workflow.analyze_product = make_pillar_fake("analyze_product", 6.6)
    workflow.analyze_execution = make_pillar_fake("analyze_execution", 6.5)
    workflow.analyze_traction = make_pillar_fake("analyze_traction", 6.0)
    workflow.analyze_financials = make_pillar_fake("analyze_financials", 5.7)
    workflow.generate_readiness_score = fake_readiness

    return originals


def _restore(originals: dict) -> None:
    for name, fn in originals.items():
        setattr(workflow, name, fn)


def test_full_pipeline_runs_concurrently_and_calls_each_dependency_exactly_once() -> None:
    delay = 0.15
    call_counts: dict[str, int] = {}
    originals = _install_full_pipeline_mocks({name: delay for name in _ALL_MOCKED_NAMES}, call_counts)

    try:
        started = time.monotonic()
        result = workflow.run_due_diligence("Fake company text describing Acme Corp.")
        elapsed = time.monotonic() - started

        # Sequential would be ~12 stages x 0.15s = ~1.8s (research, 5
        # free-form, 6 pillars, readiness -- research/pillars run as
        # their own concurrent groups but the GROUPS themselves are
        # still sequential relative to each other, so the honest
        # sequential baseline is enrich(1) + free-form(1, if it were
        # sequential 5x) + pillars(1, if sequential 6x) + readiness(1)).
        # Concurrent must be well under half of the fully-sequential sum.
        fully_sequential_estimate = delay * (1 + len(_FREE_FORM_NAMES) + len(_PILLAR_NAMES) + 1)
        expect(
            elapsed < fully_sequential_estimate / 2,
            f"Expected concurrent groups to meaningfully beat a fully-sequential run "
            f"(<{fully_sequential_estimate / 2:.2f}s), took {elapsed:.2f}s",
        )

        expect(all(call_counts.get(name) == 1 for name in _ALL_MOCKED_NAMES), f"Every dependency must be called exactly once, got {call_counts}")
        expect(result["overall_score"] is not None, "Expected a real overall_score from the six fake (but real-shaped) pillar results")
        # V3 stays off (this test's own env has no SPS_ENGINE_VERSION=v3) --
        # confirmed by there being no sps_v3 key issue and no attempted
        # real network call (this whole test makes none).
    finally:
        _restore(originals)


def test_full_pipeline_produces_identical_scores_regardless_of_completion_order() -> None:
    """The actual, literal requirement: same controlled AI outputs (the
    fake pillar scores/summary/etc. never change between these two
    runs) -- only the artificial per-call DELAYS are shuffled, so which
    call physically finishes first genuinely differs between run 1 and
    run 2 -- yet the assembled result must be byte-identical."""
    delays_run_1 = {name: 0.05 + (i % 3) * 0.05 for i, name in enumerate(_ALL_MOCKED_NAMES)}
    delays_run_2 = {name: 0.05 + ((i + 5) % 3) * 0.05 for i, name in enumerate(_ALL_MOCKED_NAMES)}
    expect(delays_run_1 != delays_run_2, "Test setup error: the two delay patterns must actually differ")

    call_counts_1: dict[str, int] = {}
    originals = _install_full_pipeline_mocks(delays_run_1, call_counts_1)
    try:
        result_1 = workflow.run_due_diligence("Fake company text describing Acme Corp.")
    finally:
        _restore(originals)

    call_counts_2: dict[str, int] = {}
    originals = _install_full_pipeline_mocks(delays_run_2, call_counts_2)
    try:
        result_2 = workflow.run_due_diligence("Fake company text describing Acme Corp.")
    finally:
        _restore(originals)

    for key in ("overall_score", "market_score", "team_score", "product_score", "competition_score", "traction_score", "financial_score", "readiness_score"):
        expect(result_1[key] == result_2[key], f"Expected identical '{key}' regardless of completion order, got {result_1[key]!r} vs {result_2[key]!r}")


def test_full_pipeline_fails_cleanly_when_a_dependency_fails() -> None:
    call_counts: dict[str, int] = {}
    originals = _install_full_pipeline_mocks({name: 0.05 for name in _ALL_MOCKED_NAMES}, call_counts)

    def failing_memo(_enriched_text):
        raise RuntimeError("simulated OpenAI failure in the memo call")

    workflow.generate_investment_memo = failing_memo

    try:
        raised = False
        try:
            workflow.run_due_diligence("Fake company text describing Acme Corp.")
        except RuntimeError:
            raised = True

        expect(raised, "run_due_diligence() must raise, never return a misleading partial analysis, when a dependency fails")
    finally:
        _restore(originals)


# ---------------------------------------------------------------------------
# Processing-time observability (Task 7, Phase 3)
# ---------------------------------------------------------------------------

def test_run_due_diligence_logs_a_duration_line_per_stage_and_a_total() -> None:
    """Verifies the actual log OUTPUT, not just that timing doesn't
    break anything -- the point of this instrumentation is that someone
    reading stdout can see per-stage and total durations. Also confirms
    company_text itself is never printed (only a short, irreversible
    hash prefix) -- the "never log private content" requirement."""
    call_counts: dict[str, int] = {}
    originals = _install_full_pipeline_mocks({name: 0.02 for name in _ALL_MOCKED_NAMES}, call_counts)

    captured = io.StringIO()
    try:
        with redirect_stdout(captured):
            workflow.run_due_diligence("Confidential Acme Corp pitch deck text that must never be logged verbatim.")
    finally:
        _restore(originals)

    output = captured.getvalue()
    expect("[due_diligence_workflow]" in output, "Expected the established log prefix to appear")
    for stage in ("stage=research", "stage=free_form_calls", "stage=pillar_analyses", "stage=readiness_score", "stage=total"):
        expect(stage in output, f"Expected a log line for {stage}, got:\n{output}")
    expect("run_id=" in output, "Expected a run_id correlation field on each log line")
    expect(
        "Confidential Acme Corp pitch deck text" not in output,
        "The raw company_text must NEVER appear in logs -- only a short hash prefix (run_id)",
    )
    # SPS V3 is off by default (Task 7 Phase 2) -- its own stage line
    # must not appear when no SPS_ENGINE_VERSION=v3 override is set.
    expect("stage=sps_v3_assessment" not in output, "V3's stage line must not appear when V3 is off (the default)")


TESTS = [
    test_run_concurrently_is_actually_concurrent_not_sequential,
    test_run_concurrently_result_mapping_is_deterministic_regardless_of_completion_order,
    test_run_concurrently_fails_loud_never_returns_a_partial_result,
    test_run_concurrently_respects_a_conservative_max_workers_bound,
    test_run_concurrently_empty_tasks_returns_empty_dict,
    test_sps_v3_disabled_by_default,
    test_sps_v3_enabled_only_when_explicitly_set_to_v3,
    test_six_pillars_run_concurrently_with_correct_deterministic_shape,
    test_six_pillars_fail_loud_if_one_raises,
    test_research_categories_search_concurrently_and_assemble_deterministically,
    test_full_pipeline_runs_concurrently_and_calls_each_dependency_exactly_once,
    test_full_pipeline_produces_identical_scores_regardless_of_completion_order,
    test_full_pipeline_fails_cleanly_when_a_dependency_fails,
    test_run_due_diligence_logs_a_duration_line_per_stage_and_a_total,
]


def main() -> None:
    print("\nPortfolio Release Task 7, Phase 2 -- Pipeline Concurrency tests")
    print("-" * 72)

    failures: list[str] = []

    for test in TESTS:
        name = test.__name__
        try:
            test()
        except AssertionError as error:
            print(f"FAIL  {name}\n      {error}")
            failures.append(name)
        else:
            print(f"PASS  {name}")

    print("-" * 72)
    print(f"{len(TESTS) - len(failures)}/{len(TESTS)} passed")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
