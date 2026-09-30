"""
Task 21 -- provider-level tests for `providers_live.py`, `source_
classification.py`, `dedup.py`, and `concurrency_helpers.py`.

**No test in this file makes a real network call.** Every real client
(`TavilyClient`, `OpenAI`, `app.website_scrapper.extract_text_from_
website`) is either monkeypatched at the module level or replaced on the
adapter instance after construction (construction itself makes no
network call for either SDK -- verified directly against the installed
`tavily`/`openai` packages before writing these tests). Adapters are
constructed with an explicit fake `api_key="test-key"` so
`ProviderNotConfiguredError` is never in the way of testing the adapter's
own logic (prompt construction, response parsing, retry classification,
telemetry recording) -- a SEPARATE, small set of tests below proves the
"no key configured" path fails loudly instead.

Run with:
    python -m app.evidence_engine.tests.test_provider_adapters
"""

from __future__ import annotations

import os
from datetime import date

from app.evidence_engine.acquisition import providers_live as live
from app.evidence_engine.acquisition.concurrency_helpers import run_concurrently_with_containment
from app.evidence_engine.acquisition.dedup import (
    dedup_retrieved_content,
    dedup_search_results,
    normalize_url,
)
from app.evidence_engine.acquisition.extraction import extract_many
from app.evidence_engine.acquisition.models import (
    ExtractedClaimCandidate,
    ExtractionRequest,
    ExtractionResponse,
    ResearchQuery,
    ResearchTopic,
    RetrievedSource,
    SearchResult,
)
from app.evidence_engine.acquisition.providers import ProviderNotConfiguredError, drain_call_log
from app.evidence_engine.acquisition.source_classification import classify_source_type
from app.evidence_engine.models import SourceType

AS_OF = date(2026, 9, 28)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# --- helpers ----------------------------------------------------------------

def _query(topic: ResearchTopic = ResearchTopic.PRODUCT_AND_TECHNOLOGY, text: str = "TestCo product") -> ResearchQuery:
    return ResearchQuery(topic=topic, query_text=text, target_dimensions=("product_existence_maturity",))


def _result(url: str, topic: ResearchTopic = ResearchTopic.PRODUCT_AND_TECHNOLOGY, query_text: str = "TestCo product") -> SearchResult:
    return SearchResult(url=url, title="A Title", snippet="a snippet", query_text=query_text, topic=topic)


def _source(url: str = "https://x.example/a", content: str = "hello world", **kw) -> RetrievedSource:
    return RetrievedSource.from_url(
        url=url, title="t", publisher="x.example", source_type=SourceType.INDEPENDENT_REPORTING,
        content=content, retrieved_at=AS_OF, discovered_by_query="q", discovered_by_topic=ResearchTopic.PRODUCT_AND_TECHNOLOGY, **kw,
    )


class _FakeTavilyClient:
    def __init__(self, response=None, raises: Exception | None = None):
        self._response = response
        self._raises = raises
        self.calls: list[dict] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises:
            raise self._raises
        return self._response


class _FakeUsage:
    def __init__(self, prompt_tokens: int | None, completion_tokens: int | None, total_tokens: int | None):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class _FakeParsedResponse:
    """Mimics the shape `client.chat.completions.parse()` returns --
    `.choices[0].message.parsed` is an already-typed
    `live._ExtractionResponseSchema` instance (never raw text), matching
    the real structured-output contract (item 3)."""

    def __init__(
        self, candidates: list[dict], finish_reason: str = "stop",
        prompt_tokens: int | None = 100, completion_tokens: int | None = 50, total_tokens: int | None = 150,
    ):
        class _Msg:
            def __init__(self, parsed):
                self.parsed = parsed
        class _Choice:
            def __init__(self, parsed, fr):
                self.message = _Msg(parsed)
                self.finish_reason = fr
        parsed = live._ExtractionResponseSchema(candidates=[live._CandidateSchema(**c) for c in candidates])
        self.choices = [_Choice(parsed, finish_reason)]
        self.usage = (
            _FakeUsage(prompt_tokens, completion_tokens, total_tokens)
            if total_tokens is not None else None
        )


class _FakeOpenAIChatCompletions:
    def __init__(self, responses_or_errors: list):
        self._queue = list(responses_or_errors)
        self.call_count = 0
        self.last_kwargs: dict | None = None

    def parse(self, **kwargs):
        self.call_count += 1
        self.last_kwargs = kwargs
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeOpenAIClient:
    def __init__(self, responses_or_errors: list):
        class _Chat:
            def __init__(self, completions):
                self.completions = completions
        self.chat = _Chat(_FakeOpenAIChatCompletions(responses_or_errors))


# --- 1. TavilySearchProvider --------------------------------------------------

def test_tavily_provider_requires_an_api_key() -> None:
    saved = os.environ.pop("TAVILY_API_KEY", None)
    try:
        raised = False
        try:
            live.TavilySearchProvider(api_key=None)
        except ProviderNotConfiguredError:
            raised = True
        expect(raised, "no TAVILY_API_KEY anywhere must fail loudly, not silently no-op")
    finally:
        if saved is not None:
            os.environ["TAVILY_API_KEY"] = saved


def test_tavily_provider_maps_a_successful_response() -> None:
    provider = live.TavilySearchProvider(api_key="test-key")
    provider._client = _FakeTavilyClient(response={"results": [
        {"url": "https://a.example/1", "title": "A", "content": "content a"},
        {"url": "https://b.example/2", "title": "B", "content": "content b"},
    ]})
    results = provider.search(_query())
    expect(len(results) == 2, f"expected 2 results, got {len(results)}")
    expect(results[0].url == "https://a.example/1", "result order/fields must be preserved")
    expect(results[0].snippet == "content a", "snippet must come from Tavily's own content field")
    calls = drain_call_log(provider)
    expect(len(calls) == 1 and calls[0].succeeded and calls[0].call_type == "search", str(calls))


def test_tavily_provider_never_requests_the_synthesized_answer() -> None:
    provider = live.TavilySearchProvider(api_key="test-key")
    fake = _FakeTavilyClient(response={"results": []})
    provider._client = fake
    provider.search(_query())
    expect(fake.calls[0]["include_answer"] is False, "Tavily's own AI-synthesized answer must never be treated as evidence")


def test_tavily_provider_handles_zero_results() -> None:
    provider = live.TavilySearchProvider(api_key="test-key")
    provider._client = _FakeTavilyClient(response={"results": []})
    results = provider.search(_query())
    expect(results == (), "zero results is a real, honest outcome, not an error")


def test_tavily_provider_handles_malformed_response() -> None:
    provider = live.TavilySearchProvider(api_key="test-key")
    provider._client = _FakeTavilyClient(response="not a dict at all")
    results = provider.search(_query())
    expect(results == (), "a malformed response must degrade to zero results, never crash")


def test_tavily_provider_drops_results_missing_a_url() -> None:
    provider = live.TavilySearchProvider(api_key="test-key")
    provider._client = _FakeTavilyClient(response={"results": [{"title": "no url here", "content": "x"}]})
    results = provider.search(_query())
    expect(results == (), "a result with no url cannot become a SearchResult")


def test_tavily_provider_propagates_and_logs_a_failure() -> None:
    provider = live.TavilySearchProvider(api_key="test-key")
    provider._client = _FakeTavilyClient(raises=RuntimeError("simulated provider error"))
    raised = False
    try:
        provider.search(_query())
    except RuntimeError:
        raised = True
    expect(raised, "a real client failure must propagate, never be silently swallowed")
    calls = drain_call_log(provider)
    expect(len(calls) == 1 and not calls[0].succeeded, str(calls))


# --- 2. HttpSourceRetriever ---------------------------------------------------

def test_http_retriever_requires_no_key_but_builds_a_correct_source(monkeypatch=None) -> None:
    retriever = live.HttpSourceRetriever(company_website_url="https://testco.example")
    original = live.extract_text_from_website
    live.extract_text_from_website = lambda url: "Some real page text about TestCo's product."
    try:
        source = retriever.retrieve(_result("https://testco.example/product"), AS_OF)
    finally:
        live.extract_text_from_website = original
    expect(source is not None, "a normal fetch must produce a RetrievedSource")
    expect(source.source_type == SourceType.COMPANY_DISCLOSURE, f"got {source.source_type}")
    expect(source.content.startswith("Some real page text"), source.content)
    calls = drain_call_log(retriever)
    expect(len(calls) == 1 and calls[0].succeeded, str(calls))


def test_http_retriever_returns_none_for_empty_content() -> None:
    retriever = live.HttpSourceRetriever(company_website_url="https://testco.example")
    original = live.extract_text_from_website
    live.extract_text_from_website = lambda url: "   \n  "
    try:
        source = retriever.retrieve(_result("https://testco.example/empty"), AS_OF)
    finally:
        live.extract_text_from_website = original
    expect(source is None, "whitespace-only content is a genuine 'nothing readable' outcome")


def test_http_retriever_truncates_to_the_configured_character_budget() -> None:
    retriever = live.HttpSourceRetriever(company_website_url="https://testco.example", max_chars_per_source=10)
    original = live.extract_text_from_website
    live.extract_text_from_website = lambda url: "x" * 1000
    try:
        source = retriever.retrieve(_result("https://testco.example/big"), AS_OF)
    finally:
        live.extract_text_from_website = original
    expect(len(source.content) == 10, f"got {len(source.content)}")


def test_http_retriever_propagates_website_fetch_error() -> None:
    retriever = live.HttpSourceRetriever(company_website_url="https://testco.example")
    original = live.extract_text_from_website
    def _raise(url):
        raise live.WebsiteFetchError("simulated unsafe/oversized/timeout failure")
    live.extract_text_from_website = _raise
    try:
        raised = False
        try:
            retriever.retrieve(_result("https://testco.example/bad"), AS_OF)
        except live.WebsiteFetchError:
            raised = True
        expect(raised, "a website_scrapper failure (SSRF/oversize/timeout/etc.) must propagate, never be swallowed")
        calls = drain_call_log(retriever)
        expect(len(calls) == 1 and not calls[0].succeeded, str(calls))
    finally:
        live.extract_text_from_website = original


def test_http_retriever_never_weakens_the_underlying_ssrf_protection() -> None:
    """Structural check: HttpSourceRetriever.retrieve calls the real,
    unmodified extract_text_from_website -- it does not implement its own
    parallel fetch path that could bypass website_scrapper.py's own
    validation."""
    import inspect
    source = inspect.getsource(live.HttpSourceRetriever.retrieve)
    expect("extract_text_from_website(" in source, "must call the real, hardened fetcher directly")
    expect("requests.get(" not in source and "urllib3.PoolManager(" not in source, "must not implement a second, unvalidated fetch path")


# --- 3. OpenAIEvidenceExtractor ------------------------------------------------

def test_openai_extractor_requires_an_api_key() -> None:
    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        raised = False
        try:
            live.OpenAIEvidenceExtractor(api_key=None)
        except ProviderNotConfiguredError:
            raised = True
        expect(raised, "no OPENAI_API_KEY anywhere must fail loudly")
    finally:
        if saved is not None:
            os.environ["OPENAI_API_KEY"] = saved


def _batch_requests(n: int) -> tuple[ExtractionRequest, ...]:
    reqs = []
    for i in range(n):
        src = _source(url=f"https://x.example/{i}", content=f"TestCo fact number {i} appears here verbatim.")
        reqs.append(ExtractionRequest(source=src, target_dimensions=("product_existence_maturity",), company_name="TestCo"))
    return tuple(reqs)

def _candidate_dict(sid: str, excerpt: str, claim_text: str = "f", criteria: list[str] | None = None, structured_fact: dict | None = None, support_status: str = "directly_supported") -> dict:
    return {
        "source_id": sid, "claim_text": claim_text, "subject_entity": "TestCo",
        "excerpt": excerpt, "assessment_criteria": criteria or ["product_existence_maturity"],
        "structured_fact": structured_fact, "support_status": support_status,
    }


def test_openai_extractor_parses_a_valid_batch_response_with_correct_attribution() -> None:
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(2)
    sid0, sid1 = reqs[0].source.source_id, reqs[1].source.source_id
    response = _FakeParsedResponse([
        _candidate_dict(sid0, "TestCo fact number 0 appears here verbatim.", "fact 0"),
        _candidate_dict(sid1, "TestCo fact number 1 appears here verbatim.", "fact 1"),
    ], total_tokens=150, prompt_tokens=100, completion_tokens=50)
    extractor._client = _FakeOpenAIClient([response])
    responses = extractor.extract_batch(reqs)
    expect(len(responses) == 2, f"one ExtractionResponse per request, got {len(responses)}")
    expect(len(responses[0].candidates) == 1 and responses[0].candidates[0].source_id == sid0, "attribution must match request order")
    expect(len(responses[1].candidates) == 1 and responses[1].candidates[0].source_id == sid1, "attribution must match request order")
    calls = drain_call_log(extractor)
    expect(len(calls) == 1 and calls[0].sources_covered == 2, str(calls))
    expect(calls[0].tokens == 150 and calls[0].input_tokens == 100 and calls[0].output_tokens == 50, str(calls[0]))
    expect(calls[0].provider_attempts == 1, f"a clean success must use exactly 1 real attempt, got {calls[0].provider_attempts}")


def test_openai_extractor_passes_the_explicit_output_token_ceiling(item=None) -> None:
    """Item 2: the configured output-token limit must actually reach the
    OpenAI request as a real parameter, not merely exist as an unused
    constant."""
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    sid = reqs[0].source.source_id
    response = _FakeParsedResponse([_candidate_dict(sid, "TestCo fact number 0 appears here verbatim.")])
    fake_client = _FakeOpenAIClient([response])
    extractor._client = fake_client
    extractor.extract_batch(reqs)
    kwargs = fake_client.chat.completions.last_kwargs
    expect(kwargs is not None, "the request kwargs must be observable")
    expect(kwargs.get("max_completion_tokens") == live.EXTRACTION_MAX_OUTPUT_TOKENS, f"got {kwargs.get('max_completion_tokens')}")
    expect(kwargs.get("response_format") is live._ExtractionResponseSchema, "the typed schema must be passed as response_format (item 3)")


def test_openai_extractor_uses_structured_output_parse_not_free_form_create() -> None:
    """Item 3: confirms the real call path is `.parse()` (the API-
    enforced structured-output mechanism), not `.create()` + manual
    json.loads -- proven by inspecting the real method's own source."""
    import inspect
    source = inspect.getsource(live.OpenAIEvidenceExtractor._call_once)
    expect(".chat.completions.parse(" in source, "must use the structured-output .parse() path")
    expect(".chat.completions.create(" not in source, "must not fall back to free-form .create()")


def test_openai_extractor_handles_an_unexpected_provider_exception_as_permanent() -> None:
    """A raised exception that is neither a classified-transient OpenAI
    error nor Length/ContentFilter must be treated as permanent (no
    retry), preserving the existing fail-safe classification."""
    class _WeirdError(RuntimeError):
        pass
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    extractor._client = _FakeOpenAIClient([_WeirdError("totally unexpected")])
    raised = False
    try:
        extractor.extract_batch(reqs)
    except _WeirdError:
        raised = True
    expect(raised, "an unrecognized exception must propagate, not be silently swallowed")
    expect(extractor._client.chat.completions.call_count == 1, "a permanent failure must not be retried")


def test_openai_extractor_drops_a_candidate_attributed_to_a_foreign_source_id() -> None:
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    response = _FakeParsedResponse([_candidate_dict("not-in-this-batch", "x")])
    extractor._client = _FakeOpenAIClient([response])
    responses = extractor.extract_batch(reqs)
    expect(len(responses[0].candidates) == 0, "a candidate claiming a source_id outside this batch must be dropped, never assigned")


def test_openai_extractor_grounding_validation_still_runs_after_schema_validation() -> None:
    """Item 3's own core requirement: even though `.parse()` guarantees
    SCHEMA-valid output, a schema-valid-but-UNGROUNDED excerpt (never
    actually present in the source) must still be rejected by
    validate_candidate() -- structured output validates syntax, not
    truth."""
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    sid = reqs[0].source.source_id
    ungrounded = _candidate_dict(sid, "this text does not appear in the source at all")
    # An ungrounded proposal is retry-worthy (item 4's own combined
    # budget) -- supply it twice so the retry itself is also ungrounded,
    # proving validate_candidate() rejects it EVERY time, not just once.
    extractor._client = _FakeOpenAIClient([_FakeParsedResponse([ungrounded]), _FakeParsedResponse([ungrounded])])
    responses = extractor.extract_batch(reqs)
    expect(len(responses[0].candidates) == 0, "an ungrounded excerpt must still be rejected despite being schema-valid")


def test_openai_extractor_extract_delegates_to_extract_batch() -> None:
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    sid = reqs[0].source.source_id
    response = _FakeParsedResponse([_candidate_dict(sid, "TestCo fact number 0 appears here verbatim.")])
    extractor._client = _FakeOpenAIClient([response])
    response_obj = extractor.extract(reqs[0])
    expect(isinstance(response_obj, ExtractionResponse) and len(response_obj.candidates) == 1, "extract() must be a thin single-element wrapper over extract_batch()")


def test_openai_extractor_never_requests_a_score_field() -> None:
    prompt = live._build_system_prompt(("product_existence_maturity",))
    expect("never" in prompt.lower() and "score" in prompt.lower(), "the system prompt must explicitly forbid scoring")


def test_openai_extractor_prompt_labels_source_content_as_untrusted_data() -> None:
    reqs = list(_batch_requests(1))
    _system, user_prompt, _outcomes = live._render_batch_request(reqs, 20_000)
    expect("untrusted" in user_prompt.lower(), "retrieved content must be explicitly labeled untrusted data, not instructions")


# --- 3a. Batch character budget (item 1) --------------------------------

def test_render_batch_request_never_exceeds_the_configured_character_budget() -> None:
    """4 maximum-size (6000-char) sources must not push the complete
    rendered request (system + user prompt combined) over the configured
    ceiling."""
    reqs = []
    for i in range(4):
        src = _source(url=f"https://x.example/{i}", content="y" * 6000)
        reqs.append(ExtractionRequest(source=src, target_dimensions=("product_existence_maturity",), company_name="TestCo"))
    budget = 20_000
    system_prompt, user_prompt, outcomes = live._render_batch_request(reqs, budget)
    total = len(system_prompt) + len(user_prompt)
    expect(total <= budget, f"rendered request ({total} chars) exceeded the configured budget ({budget})")
    expect(len(outcomes) == 4, f"got {len(outcomes)} outcomes")


def test_render_batch_request_accounts_for_system_prompt_overhead() -> None:
    """The budget must cover system instructions, not just source
    bodies -- proven by confirming available content shrinks as the
    system prompt itself grows (more target dimensions -> longer prompt
    -> less room for content), not by an independent, unenforced cap."""
    reqs_one_dim = [ExtractionRequest(source=_source(content="z" * 6000), target_dimensions=("product_existence_maturity",), company_name="TestCo")]
    reqs_many_dims = [ExtractionRequest(
        source=_source(content="z" * 6000),
        target_dimensions=("product_existence_maturity", "technical_depth_signal", "market_definition_size", "funding_history"),
        company_name="TestCo",
    )]
    _sys_a, user_a, outcomes_a = live._render_batch_request(reqs_one_dim, 4_200)
    _sys_b, user_b, outcomes_b = live._render_batch_request(reqs_many_dims, 4_200)
    expect(len(user_b) <= len(user_a), "a longer system prompt must leave less room for the user prompt under the same total budget")


def test_render_batch_request_truncation_is_deterministic() -> None:
    reqs = []
    for i in range(4):
        src = _source(url=f"https://x.example/{i}", content=f"content-{i}-" + "q" * 6000)
        reqs.append(ExtractionRequest(source=src, target_dimensions=("product_existence_maturity",), company_name="TestCo"))
    _s1, u1, o1 = live._render_batch_request(reqs, 8_000)
    _s2, u2, o2 = live._render_batch_request(reqs, 8_000)
    expect(u1 == u2, "identical input must always produce an identical rendered prompt")
    expect(tuple(o1) == tuple(o2), "identical input must always produce identical budget outcomes")


def test_render_batch_request_preserves_source_id_and_boundaries_under_truncation() -> None:
    reqs = []
    for i in range(4):
        src = _source(url=f"https://x.example/{i}", content="w" * 6000)
        reqs.append(ExtractionRequest(source=src, target_dimensions=("product_existence_maturity",), company_name="TestCo"))
    _system, user_prompt, outcomes = live._render_batch_request(reqs, 8_000)
    for r in reqs:
        sid = r.source.source_id
        outcome = next(o for o in outcomes if o.source_id == sid)
        if not outcome.excluded:
            expect(f'<source id="{sid}">' in user_prompt, f"source_id tag for {sid} must never be truncated/corrupted")
            expect("</source>" in user_prompt, "closing tag must always be present for an included source")


def test_render_batch_request_gives_a_shorter_source_its_full_content_and_redistributes() -> None:
    """Water-filling: a source genuinely shorter than an equal share
    should never be truncated, and the freed budget should benefit its
    siblings (not simply be wasted)."""
    short_content = "short and complete."
    reqs = [
        ExtractionRequest(source=_source(url="https://x.example/short", content=short_content), target_dimensions=("product_existence_maturity",), company_name="TestCo"),
        ExtractionRequest(source=_source(url="https://x.example/long", content="v" * 6000), target_dimensions=("product_existence_maturity",), company_name="TestCo"),
    ]
    # 8,000 (not the tighter 4,500 originally used) -- Task 23 lengthened
    # the system prompt with new routing/relevance guidance, so this
    # budget must comfortably exceed that longer prompt's own overhead
    # for the test to still exercise water-filling rather than exclusion.
    _system, user_prompt, outcomes = live._render_batch_request(reqs, 8_000)
    short_outcome = next(o for o in outcomes if o.source_id == reqs[0].source.source_id)
    long_outcome = next(o for o in outcomes if o.source_id == reqs[1].source.source_id)
    expect(not short_outcome.truncated and short_outcome.allocated_chars == len(short_content), str(short_outcome))
    expect(long_outcome.allocated_chars > 0, "the longer source should still receive some content")


def test_render_batch_request_excludes_a_source_that_cannot_fit_safely() -> None:
    """A source whose fair share would fall below the safety floor is
    excluded entirely (graceful degradation, item 5) -- never sent a
    content sliver too short to safely excerpt from."""
    reqs = []
    for i in range(20):
        src = _source(url=f"https://x.example/{i}", content="p" * 6000)
        reqs.append(ExtractionRequest(source=src, target_dimensions=("product_existence_maturity",), company_name="TestCo"))
    _system, user_prompt, outcomes = live._render_batch_request(reqs, 4_500)
    expect(any(o.excluded for o in outcomes), "with 20 sources sharing a small budget, at least one must be excluded rather than sent a useless sliver")
    for o in outcomes:
        if o.excluded:
            expect(f'<source id="{o.source_id}">' not in user_prompt, "an excluded source's block must never appear in the prompt at all")


def test_openai_extractor_records_truncation_telemetry() -> None:
    reqs = []
    for i in range(4):
        src = _source(url=f"https://x.example/{i}", content="a" * 6000)
        reqs.append(ExtractionRequest(source=src, target_dimensions=("product_existence_maturity",), company_name="TestCo"))
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key", max_total_input_chars_per_batch=4_000)
    response = _FakeParsedResponse([])
    extractor._client = _FakeOpenAIClient([response])
    extractor.extract_batch(tuple(reqs))
    calls = drain_call_log(extractor)
    expect(len(calls) == 1 and calls[0].truncated, "truncation of source content must be recorded on the call's own telemetry")


# --- 3b. Retry ownership (item 4) -----------------------------------------

def test_openai_extractor_success_uses_exactly_one_provider_attempt() -> None:
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    sid = reqs[0].source.source_id
    extractor._client = _FakeOpenAIClient([_FakeParsedResponse([_candidate_dict(sid, "TestCo fact number 0 appears here verbatim.")])])
    extractor.extract_batch(reqs)
    calls = drain_call_log(extractor)
    expect(calls[0].provider_attempts == 1 and calls[0].validation_retries == 0, str(calls[0]))


def test_openai_extractor_transient_failure_then_success_uses_two_attempts() -> None:
    import openai as openai_pkg
    live.time.sleep = lambda s: None
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    sid = reqs[0].source.source_id
    transient = openai_pkg.APIConnectionError(request=None)
    good = _FakeParsedResponse([_candidate_dict(sid, "TestCo fact number 0 appears here verbatim.")])
    extractor._client = _FakeOpenAIClient([transient, good])
    responses = extractor.extract_batch(reqs)
    expect(len(responses[0].candidates) == 1, "must recover after one transient failure")
    calls = drain_call_log(extractor)
    expect(calls[0].provider_attempts == 2 and calls[0].succeeded, str(calls[0]))
    expect(extractor._client.chat.completions.call_count == 2, f"expected exactly 2 real attempts, got {extractor._client.chat.completions.call_count}")


def test_openai_extractor_repeated_transient_failure_exhausts_gracefully() -> None:
    import openai as openai_pkg
    live.time.sleep = lambda s: None
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    extractor._client = _FakeOpenAIClient([openai_pkg.APIConnectionError(request=None), openai_pkg.APIConnectionError(request=None)])
    responses = extractor.extract_batch(reqs)
    expect(len(responses) == 1 and len(responses[0].candidates) == 0, "exhaustion must degrade to zero candidates, never raise, never fabricate")
    calls = drain_call_log(extractor)
    expect(calls[0].provider_attempts == 2 and not calls[0].succeeded, str(calls[0]))
    expect(extractor._client.chat.completions.call_count == 2, f"must never exceed the combined attempt budget: got {extractor._client.chat.completions.call_count}")


def test_openai_extractor_validation_failure_then_success_uses_two_attempts() -> None:
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    sid = reqs[0].source.source_id
    ungrounded = _FakeParsedResponse([_candidate_dict(sid, "text not present in the source")])
    grounded = _FakeParsedResponse([_candidate_dict(sid, "TestCo fact number 0 appears here verbatim.")])
    extractor._client = _FakeOpenAIClient([ungrounded, grounded])
    responses = extractor.extract_batch(reqs)
    expect(len(responses[0].candidates) == 1, "a validation failure followed by a grounded retry must recover")
    calls = drain_call_log(extractor)
    expect(calls[0].provider_attempts == 2 and calls[0].validation_retries == 1, str(calls[0]))


def test_openai_extractor_validation_failure_plus_transient_failure_still_bounded() -> None:
    """A validation failure on attempt 1 and a transient failure that
    WOULD be attempt 3 must never happen -- the combined budget is 2,
    covering EITHER failure class, never both independently."""
    import openai as openai_pkg
    live.time.sleep = lambda s: None
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    sid = reqs[0].source.source_id
    ungrounded = _FakeParsedResponse([_candidate_dict(sid, "text not present in the source")])
    extractor._client = _FakeOpenAIClient([ungrounded, openai_pkg.APIConnectionError(request=None)])
    responses = extractor.extract_batch(reqs)
    expect(len(responses[0].candidates) == 0, "both attempts exhausted -- must degrade honestly, not fabricate")
    expect(extractor._client.chat.completions.call_count == 2, f"must stay within the combined 2-attempt budget: got {extractor._client.chat.completions.call_count}")


def test_openai_extractor_complete_exhaustion_never_raises_for_validation_only_failures() -> None:
    """Pure validation exhaustion (every attempt proposes something, but
    nothing ever grounds) must degrade to zero candidates -- never raise
    an exception (a validation failure is not a provider error)."""
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    sid = reqs[0].source.source_id
    bad1 = _FakeParsedResponse([_candidate_dict(sid, "still not present")])
    bad2 = _FakeParsedResponse([_candidate_dict(sid, "also not present")])
    extractor._client = _FakeOpenAIClient([bad1, bad2])
    responses = extractor.extract_batch(reqs)
    expect(len(responses[0].candidates) == 0, "exhausted validation retries must degrade honestly")
    calls = drain_call_log(extractor)
    expect(calls[0].provider_attempts == 2 and calls[0].succeeded, "the provider itself succeeded both times -- only grounding failed, so this is not a call failure")


def test_openai_extractor_worst_case_matches_the_documented_formula() -> None:
    """6 batches x EXTRACTION_MAX_PROVIDER_ATTEMPTS_PER_BATCH (2) = 12,
    the new documented absolute maximum (down from the old 36)."""
    import math
    from app.evidence_engine.acquisition.models import AcquisitionBudget
    budget = AcquisitionBudget()
    worst_case_batches = math.ceil(budget.max_extraction_calls / budget.max_sources_per_batch)
    worst_case_attempts = worst_case_batches * live.EXTRACTION_MAX_PROVIDER_ATTEMPTS_PER_BATCH
    expect(worst_case_batches == 6, f"got {worst_case_batches}")
    expect(worst_case_attempts == 12, f"got {worst_case_attempts}")
    expect(worst_case_attempts < 36, "must be a real reduction from the original two-layer design's own worst case")


# --- 4. Deterministic source-type classification (item 13) -------------------

COMPANY_URL = "https://testco.example"


def test_company_own_domain_classifies_as_company_disclosure() -> None:
    expect(classify_source_type("https://testco.example/about", COMPANY_URL) == SourceType.COMPANY_DISCLOSURE, "own domain")


def test_company_docs_subdomain_classifies_as_product_documentation() -> None:
    expect(classify_source_type("https://docs.testco.example/api", COMPANY_URL) == SourceType.PRODUCT_DOCUMENTATION, "docs subdomain")


def test_known_aggregator_domain_classifies_correctly() -> None:
    got = classify_source_type("https://www.crunchbase.com/organization/testco", COMPANY_URL)
    expect(got == SourceType.AGGREGATOR_OR_DIRECTORY, f"got {got}")


def test_known_public_filing_domain_classifies_correctly() -> None:
    got = classify_source_type("https://www.sec.gov/cgi-bin/browse-edgar", COMPANY_URL)
    expect(got == SourceType.PUBLIC_FILING, f"got {got}")


def test_known_community_domain_classifies_correctly() -> None:
    got = classify_source_type("https://news.ycombinator.com/item?id=1", COMPANY_URL)
    expect(got == SourceType.COMMUNITY_COMMENTARY, f"got {got}")


def test_unknown_third_party_domain_defaults_to_independent_reporting() -> None:
    got = classify_source_type("https://techcrunch.com/2026/testco-raises", COMPANY_URL)
    expect(got == SourceType.INDEPENDENT_REPORTING, f"got {got}")


def test_source_type_classification_ignores_page_content_entirely() -> None:
    """The core item-13 invariant: source_type is a pure function of two
    URLs. It structurally CANNOT read page content, because it is never
    given any -- proven here by inspecting the function's own signature
    rather than merely by example."""
    import inspect
    params = list(inspect.signature(classify_source_type).parameters)
    expect(params == ["url", "company_website_url"], f"must take only URLs, never content: got {params}")


def test_a_company_domain_cannot_self_declare_independence_via_a_deceptive_path() -> None:
    """A path/query on the company's OWN domain that looks like it is
    trying to claim independence (e.g. an /independent-review URL slug)
    still classifies as COMPANY_DISCLOSURE -- only the registered domain
    matters, never the path."""
    tricky = "https://testco.example/independent-verified-review?source=trusted-third-party"
    expect(classify_source_type(tricky, COMPANY_URL) == SourceType.COMPANY_DISCLOSURE, "path text must never influence classification")


# --- 5. dedup.py --------------------------------------------------------------

def test_normalize_url_strips_tracking_params_and_trailing_slash() -> None:
    a = normalize_url("https://EXAMPLE.com/page/?utm_source=x&id=7")
    b = normalize_url("https://example.com/page?id=7")
    expect(a == b, f"{a!r} != {b!r}")


def test_normalize_url_keeps_genuinely_different_query_params_distinct() -> None:
    a = normalize_url("https://example.com/page?id=7")
    b = normalize_url("https://example.com/page?id=8")
    expect(a != b, "a different, non-tracking query param must stay a different URL")


def test_dedup_search_results_collapses_exact_duplicate_urls_keeping_first() -> None:
    r1 = _result("https://a.example/x")
    r2 = _result("https://a.example/x/")  # trailing slash only
    r3 = _result("https://b.example/y")
    out = dedup_search_results((r1, r2, r3))
    expect(len(out) == 2 and out[0] is r1 and out[1] is r3, f"got {[o.url for o in out]}")


def test_dedup_search_results_never_collapses_different_urls() -> None:
    r1 = _result("https://a.example/x")
    r2 = _result("https://a.example/y")
    out = dedup_search_results((r1, r2))
    expect(len(out) == 2, "two genuinely different URLs must never be collapsed")


def test_dedup_retrieved_content_collapses_byte_identical_content() -> None:
    s1 = _source(url="https://a.example/1", content="Identical wire-copy text.")
    s2 = _source(url="https://b.example/2", content="Identical wire-copy text.")
    kept, dropped = dedup_retrieved_content((s1, s2))
    expect(len(kept) == 1 and kept[0] is s1, "first-seen content must be kept")
    expect(len(dropped) == 1 and dropped[0] is s2, "the later exact-duplicate must be recorded as dropped")


def test_dedup_retrieved_content_never_collapses_merely_similar_content() -> None:
    s1 = _source(url="https://a.example/1", content="TestCo raised a $5M seed round led by Acme Ventures.")
    s2 = _source(url="https://b.example/2", content="According to our sources, TestCo closed a $5M seed financing.")
    kept, dropped = dedup_retrieved_content((s1, s2))
    expect(len(kept) == 2 and len(dropped) == 0, "genuinely different wording must never be collapsed here")


# --- 6. concurrency_helpers.py -------------------------------------------------

def test_run_concurrently_with_containment_all_succeed() -> None:
    tasks = {f"k{i}": (lambda i=i: i * 2) for i in range(5)}
    out = run_concurrently_with_containment(tasks, max_workers=3)
    expect(list(out.keys()) == [f"k{i}" for i in range(5)], "result keys/order must match insertion order")
    expect(all(out[f"k{i}"].ok and out[f"k{i}"].value == i * 2 for i in range(5)), str(out))


def test_run_concurrently_with_containment_isolates_one_failure() -> None:
    def _boom():
        raise ValueError("simulated")
    tasks = {"ok1": lambda: 1, "bad": _boom, "ok2": lambda: 2}
    out = run_concurrently_with_containment(tasks, max_workers=3)
    expect(out["ok1"].ok and out["ok1"].value == 1, "sibling task 1 must be unaffected")
    expect(out["ok2"].ok and out["ok2"].value == 2, "sibling task 2 must be unaffected")
    expect(not out["bad"].ok and isinstance(out["bad"].error, ValueError), str(out["bad"]))


def test_run_concurrently_with_containment_respects_a_small_worker_cap() -> None:
    tasks = {f"k{i}": (lambda i=i: i) for i in range(10)}
    out = run_concurrently_with_containment(tasks, max_workers=2)
    expect(len(out) == 10 and all(o.ok for o in out.values()), "a small worker cap must not lose or fail any task")


# --- 7. extract_many: batch-path source-id spoofing resistance ---------------

class _SpoofingBatchExtractor:
    """A stub batch-capable extractor whose candidate claims a DIFFERENT
    source_id than the request it was returned for -- proves extract_
    many()'s own per-request validate_candidate() call still catches
    this even on the batch-capable path, not only the fallback path."""

    def extract_batch(self, requests):
        responses = []
        for i, req in enumerate(requests):
            foreign_sid = requests[(i + 1) % len(requests)].source.source_id if len(requests) > 1 else "totally-unknown-id"
            responses.append(ExtractionResponse(candidates=(
                ExtractedClaimCandidate(
                    source_id=foreign_sid, claim_text="x", subject_entity="TestCo",
                    excerpt=req.source.content, assessment_criteria=["product_existence_maturity"],
                ),
            )))
        return tuple(responses)

    def extract(self, request):
        return self.extract_batch((request,))[0]


def test_extract_many_batch_path_rejects_a_candidate_claiming_a_sibling_source_id() -> None:
    reqs = _batch_requests(2)
    accepted, rejected, errors, _attempts = extract_many(_SpoofingBatchExtractor(), reqs, max_attempts=1)
    expect(all(len(v) == 0 for v in accepted.values()), f"a spoofed source_id must never be accepted, got {accepted}")
    expect(all(len(rejected.get(r.source.source_id, ())) >= 1 for r in reqs), "each request should see its own rejection")
    expect(errors == {}, "this is a validation rejection, not a raised extraction error")


TESTS = [
    test_tavily_provider_requires_an_api_key,
    test_tavily_provider_maps_a_successful_response,
    test_tavily_provider_never_requests_the_synthesized_answer,
    test_tavily_provider_handles_zero_results,
    test_tavily_provider_handles_malformed_response,
    test_tavily_provider_drops_results_missing_a_url,
    test_tavily_provider_propagates_and_logs_a_failure,
    test_http_retriever_requires_no_key_but_builds_a_correct_source,
    test_http_retriever_returns_none_for_empty_content,
    test_http_retriever_truncates_to_the_configured_character_budget,
    test_http_retriever_propagates_website_fetch_error,
    test_http_retriever_never_weakens_the_underlying_ssrf_protection,
    test_openai_extractor_requires_an_api_key,
    test_openai_extractor_parses_a_valid_batch_response_with_correct_attribution,
    test_openai_extractor_passes_the_explicit_output_token_ceiling,
    test_openai_extractor_uses_structured_output_parse_not_free_form_create,
    test_openai_extractor_handles_an_unexpected_provider_exception_as_permanent,
    test_openai_extractor_drops_a_candidate_attributed_to_a_foreign_source_id,
    test_openai_extractor_grounding_validation_still_runs_after_schema_validation,
    test_openai_extractor_extract_delegates_to_extract_batch,
    test_openai_extractor_never_requests_a_score_field,
    test_openai_extractor_prompt_labels_source_content_as_untrusted_data,
    test_render_batch_request_never_exceeds_the_configured_character_budget,
    test_render_batch_request_accounts_for_system_prompt_overhead,
    test_render_batch_request_truncation_is_deterministic,
    test_render_batch_request_preserves_source_id_and_boundaries_under_truncation,
    test_render_batch_request_gives_a_shorter_source_its_full_content_and_redistributes,
    test_render_batch_request_excludes_a_source_that_cannot_fit_safely,
    test_openai_extractor_records_truncation_telemetry,
    test_openai_extractor_success_uses_exactly_one_provider_attempt,
    test_openai_extractor_transient_failure_then_success_uses_two_attempts,
    test_openai_extractor_repeated_transient_failure_exhausts_gracefully,
    test_openai_extractor_validation_failure_then_success_uses_two_attempts,
    test_openai_extractor_validation_failure_plus_transient_failure_still_bounded,
    test_openai_extractor_complete_exhaustion_never_raises_for_validation_only_failures,
    test_openai_extractor_worst_case_matches_the_documented_formula,
    test_company_own_domain_classifies_as_company_disclosure,
    test_company_docs_subdomain_classifies_as_product_documentation,
    test_known_aggregator_domain_classifies_correctly,
    test_known_public_filing_domain_classifies_correctly,
    test_known_community_domain_classifies_correctly,
    test_unknown_third_party_domain_defaults_to_independent_reporting,
    test_source_type_classification_ignores_page_content_entirely,
    test_a_company_domain_cannot_self_declare_independence_via_a_deceptive_path,
    test_normalize_url_strips_tracking_params_and_trailing_slash,
    test_normalize_url_keeps_genuinely_different_query_params_distinct,
    test_dedup_search_results_collapses_exact_duplicate_urls_keeping_first,
    test_dedup_search_results_never_collapses_different_urls,
    test_dedup_retrieved_content_collapses_byte_identical_content,
    test_dedup_retrieved_content_never_collapses_merely_similar_content,
    test_run_concurrently_with_containment_all_succeed,
    test_run_concurrently_with_containment_isolates_one_failure,
    test_run_concurrently_with_containment_respects_a_small_worker_cap,
    test_extract_many_batch_path_rejects_a_candidate_claiming_a_sibling_source_id,
]


def main() -> None:
    passed = 0
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  {test.__name__}: {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {test.__name__}: {exc!r}")
            failed += 1
    print("-" * 74)
    print(f"{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
