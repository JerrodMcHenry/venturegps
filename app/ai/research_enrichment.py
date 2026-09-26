from openai import OpenAI
from tavily import TavilyClient
from dotenv import load_dotenv
import json
import os

from app.ai.concurrency import run_concurrently

load_dotenv()

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


# Methodology V2.1 (Phase 10.8B, Part 4): before this change, enrich_research()
# ran exactly one generic "company overview" Tavily search feeding all six
# pillars' worth of evidence-extraction prompts. Phase 10.8B's full-cohort
# Public-dimension audit (docs/validation/SPS_METHODOLOGY_V2_1_CHANGELOG.md)
# found that a single generic search's results are dominated by product/
# marketing facts and essentially never surface founder history, competitive-
# landscape specifics, or funding/financial figures -- which is why Public
# dimensions whose evidence has to come from exactly those categories
# (Founder-Market Fit, Market Growth/Timing, Competitive Intensity, Runway)
# were marked Unavailable in 48-88% of the frozen 25-company real-company
# cohort, including for extremely well-documented companies. The evidence-
# extraction stage's existing correction pass (evidence_extraction.py's
# "Public Evidence Validation Consistency Fix") already re-asks the model to
# reconsider before accepting Unavailable; re-asking the same model with the
# same thin research material a second time cannot manufacture evidence that
# was never fetched in the first place. This is an input-sourcing problem,
# not a prompt-compliance problem, so the fix belongs here.
RESEARCH_CATEGORIES = ("overview", "market_and_competitors", "founders_and_leadership", "financial_and_funding")


def extract_search_queries(company_text: str) -> dict[str, str]:
    """
    One LLM call producing up to four targeted web-search queries instead
    of one generic one, so each of the six pillars' evidence-extraction
    stage has a realistic chance of finding category-relevant public
    material -- not just whatever a single "company overview" search
    happens to surface.
    """
    response = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract targeted web search queries for researching this "
                    "startup across four distinct categories. Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
Company information:
{company_text}

Create four concise, distinct web search queries to research this company,
one per category below. Each query should be specific enough to surface
category-relevant results, not just general company-overview content.

- overview: general company/product overview query (what does it do, who is it for)
- market_and_competitors: the company's market, market size/growth signals, and named competitors
- founders_and_leadership: the founders'/leadership's prior companies, background, and domain experience
- financial_and_funding: the company's funding history, valuation, investors, and any disclosed financial metrics

Return ONLY this JSON structure, no markdown, no commentary:

{{
  "overview": "...",
  "market_and_competitors": "...",
  "founders_and_leadership": "...",
  "financial_and_funding": "..."
}}
""",
            },
        ],
    )

    content = response.choices[0].message.content or "{}"

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {}

    queries: dict[str, str] = {}
    for category in RESEARCH_CATEGORIES:
        value = data.get(category)
        queries[category] = value.strip() if isinstance(value, str) and value.strip() else ""

    # Fail-safe: if the model returned nothing usable at all (malformed
    # JSON, empty strings), fall back to the single original generic
    # query behavior rather than searching nothing.
    if not any(queries.values()):
        queries["overview"] = extract_legacy_search_query(company_text)

    return queries


def extract_legacy_search_query(company_text: str) -> str:
    """The original, pre-V2.1 single-query behavior -- kept as the
    fail-safe path above, and for any caller that still wants exactly
    one generic query."""
    response = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.0,
        messages=[
            {
                "role": "system",
                "content": "Extract the best web search query for researching this startup"
            },
            {
                "role": "user",
                "content": f"""
Create one concise web search query to research this company.

Company information:
{company_text}

Return only the search query. No quotes. No explination.
"""
            }
        ]
    )
    return response.choices[0].message.content.strip()


def search_web(query: str) -> dict:
    if not query:
        return {"research_text": "", "sources": []}

    results = tavily_client.search(
        query=query,
        search_depth="basic",
        max_results=5,
        include_answer=True
    )
    research_text = ""

    if results.get("answer"):
        research_text += f"Tavily Answer:\n{results['answer']}\n\n"

    for item in results.get("results", []):
        title = item.get("title", "")
        url = item.get("url", "")
        content = item.get("content", "")

        research_text +=  f"Title: {title}\nURL: {url}\nContent: {content}\n\n"

    sources = []

    for item in results.get("results", []):
        sources.append({
            "title": item.get("title", ""),
            "url": item.get("url", "")
        })

    return {
        "research_text": research_text.strip(),
        "sources": sources
    }


_CATEGORY_LABELS = {
    "overview": "COMPANY OVERVIEW RESEARCH",
    "market_and_competitors": "MARKET & COMPETITIVE-LANDSCAPE RESEARCH",
    "founders_and_leadership": "FOUNDERS & LEADERSHIP RESEARCH",
    "financial_and_funding": "FUNDING & FINANCIAL RESEARCH",
}


def enrich_research(company_text):
    queries = extract_search_queries(company_text)

    # Portfolio Release Task 7, Phase 2 -- Reduce Analysis Latency: these
    # up-to-four category searches are independent Tavily calls (each
    # its own query, no shared state) -- confirmed by the Phase 1 audit
    # as one of the three safely-parallelizable groups. Run concurrently
    # via run_concurrently() (app/ai/concurrency.py), bounded to at most
    # len(RESEARCH_CATEGORIES) at once. A category whose query came back
    # empty is skipped exactly as before -- never submitted as a task at
    # all, not merely filtered out of the result afterward.
    categories_to_search = [category for category in RESEARCH_CATEGORIES if queries.get(category)]

    results_by_category = run_concurrently(
        {
            # Default-arg capture (q=queries[category]) -- without it,
            # every one of these closures would share the SAME final
            # loop variable `category` by the time they actually run
            # (Python's usual late-binding-closure trap), and every
            # search would query for whichever category happened to be
            # last, not its own.
            category: (lambda q=queries[category]: search_web(q))
            for category in categories_to_search
        }
    )

    combined_research_text_parts = []
    combined_sources = []
    seen_source_urls = set()

    # Deterministic assembly: iterate RESEARCH_CATEGORIES' own FIXED
    # order (never dict/completion order) so the combined research text
    # fed into the brief-synthesis call below is identical to what the
    # old sequential loop produced for the same underlying Tavily
    # results, regardless of which search actually finished first. This
    # is what makes "the same controlled inputs produce the same output"
    # true here, not just at the pillar/free-form call level.
    for category in RESEARCH_CATEGORIES:
        if category not in results_by_category:
            continue

        query = queries[category]
        web_results = results_by_category[category]

        if web_results["research_text"]:
            combined_research_text_parts.append(
                f"=== {_CATEGORY_LABELS[category]} (query: {query}) ===\n"
                f"{web_results['research_text']}"
            )

        for source in web_results["sources"]:
            url = source.get("url", "")
            if url and url not in seen_source_urls:
                seen_source_urls.add(url)
                combined_sources.append(source)

    web_research = "\n\n".join(combined_research_text_parts)

    # Single readable string for analysis_context.search_query (a plain
    # str field, app/models/analysis_context.py) -- the full per-category
    # breakdown is preserved in the returned dict's "search_queries" for
    # anything that wants it, but the persisted analysis_context keeps
    # its existing shape.
    search_query_summary = " | ".join(
        f"{category}: {queries[category]}"
        for category in RESEARCH_CATEGORIES
        if queries.get(category)
    )

    response = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.0,
        messages=[
            {
                "role": "system",
                "content": "You are a startup research analyst helping enrich due diligence context using web research evidence."
            },
            {
                "role": "user",
                "content": f"""


Company information:
{company_text}

Web research (organized by category -- use ALL categories, not just the
overview, when writing the brief below; founder background belongs in
Verified Facts/Reasonable Assumptions just like product facts do):
{web_research}

Create a due diligence brief using ONLY the provided information.

Rules:

- Only state information as a fact if it is supported by the web research.
- Clearly seperate facts from assumptions.
- If information cannot be verified, state UNKNOWN.
- Do not invent funding amounts.
- Do not invent TAM, SAM, SOM, market size, market share, growth rates, or revenue figures.
- Do not make unsupported claims sound certain.
- If the Founders & Leadership research surfaced any named founder/executive
  background (prior companies, domain expertise, education), include it
  explicitly -- do not omit it merely because it is not financial.

Return these sections:

1. Company Overview
2. Verified Facts
3. Reasonable Assumptions
4. Business Model
5. Target Customers
6. Competitors
7. Key Risks
8. Important Unknowns
9. Sources

For the Sources section, include any URLs referenced in the web research.
"""
            }
        ]
    )

    return {
        "research_brief": response.choices[0].message.content,
        "sources": combined_sources,
        "search_query": search_query_summary or extract_legacy_search_query(company_text),
        "search_queries": queries,
    }
