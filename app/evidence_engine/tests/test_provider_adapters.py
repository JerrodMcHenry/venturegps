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


class _FakeOpenAIResponse:
    def __init__(self, content: str, total_tokens: int | None = 123):
        class _Msg:
            def __init__(self, c):
                self.content = c
        class _Choice:
            def __init__(self, c):
                self.message = _Msg(c)
        class _Usage:
            def __init__(self, t):
                self.total_tokens = t
        self.choices = [_Choice(content)]
        self.usage = _Usage(total_tokens) if total_tokens is not None else None


class _FakeOpenAIChatCompletions:
    def __init__(self, responses_or_errors: list):
        self._queue = list(responses_or_errors)
        self.call_count = 0

    def create(self, **kwargs):
        self.call_count += 1
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


def test_openai_extractor_parses_a_valid_batch_response_with_correct_attribution() -> None:
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(2)
    sid0, sid1 = reqs[0].source.source_id, reqs[1].source.source_id
    payload = (
        f'[{{"source_id": "{sid0}", "claim_text": "fact 0", "subject_entity": "TestCo", '
        f'"excerpt": "TestCo fact number 0 appears here verbatim.", "assessment_criteria": ["product_existence_maturity"]}}, '
        f'{{"source_id": "{sid1}", "claim_text": "fact 1", "subject_entity": "TestCo", '
        f'"excerpt": "TestCo fact number 1 appears here verbatim.", "assessment_criteria": ["product_existence_maturity"]}}]'
    )
    extractor._client = _FakeOpenAIClient([_FakeOpenAIResponse(payload)])
    responses = extractor.extract_batch(reqs)
    expect(len(responses) == 2, f"one ExtractionResponse per request, got {len(responses)}")
    expect(len(responses[0].candidates) == 1 and responses[0].candidates[0].source_id == sid0, "attribution must match request order")
    expect(len(responses[1].candidates) == 1 and responses[1].candidates[0].source_id == sid1, "attribution must match request order")
    calls = drain_call_log(extractor)
    expect(len(calls) == 1 and calls[0].sources_covered == 2 and calls[0].tokens == 123, str(calls))


def test_openai_extractor_strips_markdown_code_fences() -> None:
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    sid = reqs[0].source.source_id
    payload = f'```json\n[{{"source_id": "{sid}", "claim_text": "f", "subject_entity": "TestCo", "excerpt": "TestCo fact number 0 appears here verbatim.", "assessment_criteria": ["product_existence_maturity"]}}]\n```'
    extractor._client = _FakeOpenAIClient([_FakeOpenAIResponse(payload)])
    responses = extractor.extract_batch(reqs)
    expect(len(responses[0].candidates) == 1, "fenced JSON must still parse")


def test_openai_extractor_handles_malformed_json_as_zero_candidates() -> None:
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(2)
    extractor._client = _FakeOpenAIClient([_FakeOpenAIResponse("this is not json at all {{{")])
    responses = extractor.extract_batch(reqs)
    expect(all(len(r.candidates) == 0 for r in responses), "malformed output must degrade to zero candidates, never crash")


def test_openai_extractor_drops_a_candidate_attributed_to_a_foreign_source_id() -> None:
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    payload = '[{"source_id": "not-in-this-batch", "claim_text": "f", "subject_entity": "TestCo", "excerpt": "x", "assessment_criteria": ["product_existence_maturity"]}]'
    extractor._client = _FakeOpenAIClient([_FakeOpenAIResponse(payload)])
    responses = extractor.extract_batch(reqs)
    expect(len(responses[0].candidates) == 0, "a candidate claiming a source_id outside this batch must be dropped, never assigned")


def test_openai_extractor_drops_a_schema_invalid_item_but_keeps_the_rest() -> None:
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    sid = reqs[0].source.source_id
    payload = f'[{{"source_id": "{sid}"}}, {{"source_id": "{sid}", "claim_text": "f", "subject_entity": "TestCo", "excerpt": "TestCo fact number 0 appears here verbatim.", "assessment_criteria": ["product_existence_maturity"]}}]'
    extractor._client = _FakeOpenAIClient([_FakeOpenAIResponse(payload)])
    responses = extractor.extract_batch(reqs)
    expect(len(responses[0].candidates) == 1, "a malformed item (missing required fields) must be dropped, valid sibling kept")


def test_openai_extractor_retries_a_transient_failure_then_succeeds() -> None:
    import openai as openai_pkg
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    live.time.sleep = lambda s: None  # keep the test fast; restored implicitly (module-level, test process only)
    reqs = _batch_requests(1)
    sid = reqs[0].source.source_id
    good = f'[{{"source_id": "{sid}", "claim_text": "f", "subject_entity": "TestCo", "excerpt": "TestCo fact number 0 appears here verbatim.", "assessment_criteria": ["product_existence_maturity"]}}]'
    transient = openai_pkg.APIConnectionError(request=None) if hasattr(openai_pkg.APIConnectionError, "__init__") else RuntimeError()
    extractor._client = _FakeOpenAIClient([transient, _FakeOpenAIResponse(good)])
    responses = extractor.extract_batch(reqs)
    expect(len(responses[0].candidates) == 1, "must recover after one transient failure")
    expect(extractor._client.chat.completions.call_count == 2, f"expected exactly 2 attempts, got {extractor._client.chat.completions.call_count}")


def test_openai_extractor_does_not_retry_a_permanent_failure() -> None:
    class _PermanentError(RuntimeError):
        pass
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    extractor._client = _FakeOpenAIClient([_PermanentError("bad request, not retryable")])
    raised = False
    try:
        extractor.extract_batch(reqs)
    except _PermanentError:
        raised = True
    expect(raised, "a permanent (non-transient) failure must raise, not be retried away")
    expect(extractor._client.chat.completions.call_count == 1, f"expected exactly 1 attempt, got {extractor._client.chat.completions.call_count}")


def test_openai_extractor_extract_delegates_to_extract_batch() -> None:
    extractor = live.OpenAIEvidenceExtractor(api_key="test-key")
    reqs = _batch_requests(1)
    sid = reqs[0].source.source_id
    payload = f'[{{"source_id": "{sid}", "claim_text": "f", "subject_entity": "TestCo", "excerpt": "TestCo fact number 0 appears here verbatim.", "assessment_criteria": ["product_existence_maturity"]}}]'
    extractor._client = _FakeOpenAIClient([_FakeOpenAIResponse(payload)])
    response = extractor.extract(reqs[0])
    expect(isinstance(response, ExtractionResponse) and len(response.candidates) == 1, "extract() must be a thin single-element wrapper over extract_batch()")


def test_openai_extractor_never_requests_a_score_field() -> None:
    prompt = live._build_system_prompt(("product_existence_maturity",))
    expect("never" in prompt.lower() and "score" in prompt.lower(), "the system prompt must explicitly forbid scoring")


def test_openai_extractor_prompt_labels_source_content_as_untrusted_data() -> None:
    reqs = _batch_requests(1)
    user_prompt = live._build_user_prompt(reqs)
    expect("untrusted" in user_prompt.lower(), "retrieved content must be explicitly labeled untrusted data, not instructions")


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
    test_openai_extractor_strips_markdown_code_fences,
    test_openai_extractor_handles_malformed_json_as_zero_candidates,
    test_openai_extractor_drops_a_candidate_attributed_to_a_foreign_source_id,
    test_openai_extractor_drops_a_schema_invalid_item_but_keeps_the_rest,
    test_openai_extractor_retries_a_transient_failure_then_succeeds,
    test_openai_extractor_does_not_retry_a_permanent_failure,
    test_openai_extractor_extract_delegates_to_extract_batch,
    test_openai_extractor_never_requests_a_score_field,
    test_openai_extractor_prompt_labels_source_content_as_untrusted_data,
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
