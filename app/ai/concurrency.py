"""
Portfolio Release Task 7, Phase 2 -- Reduce Analysis Latency. One small,
shared helper for the three independent-call groups the Phase 1 audit
identified (four Tavily research searches, five free-form analysis
calls, six pillar analyses) -- rather than three separately hand-rolled
ThreadPoolExecutor blocks. Every existing call site this is used from
(app/workflows/due_diligence_workflow.py, app/ai/research_enrichment.py)
still calls the same underlying functions (analyze_founders(),
summarize_company(), search_web(), ...) with the same arguments; only
the orchestration -- sequential loop vs. concurrent dispatch -- changed.
No prompt, model, scoring formula, or retry/backoff behavior inside any
of those functions is touched by this module.
"""

from __future__ import annotations

import concurrent.futures
from typing import Callable, TypeVar

T = TypeVar("T")


def run_concurrently(
    tasks: dict[str, Callable[[], T]],
    max_workers: int | None = None,
) -> dict[str, T]:
    """
    Run every callable in `tasks` concurrently, bounded to at most
    `max_workers` at once (defaults to len(tasks) -- every group this is
    used for today is small (4-6 calls) and every member is
    independent, so there is no reason to under-parallelize; still a
    real, explicit, conservative bound -- never unbounded fan-out, and
    callers may pass a smaller number to be more conservative about
    provider rate limits).

    Returns {key: result}, built by iterating `tasks` in its OWN
    insertion order (never completion order) -- the result dict's
    contents are therefore identical regardless of which call happens
    to finish first. This is what makes concurrent execution here safe
    to introduce without changing anything downstream: the same
    controlled inputs always produce the same {key: result} mapping,
    whichever call physically finishes first.

    Fails loud, never partial: `future.result()` re-raises whatever
    exception that task raised (including after the reliability-hardened
    call_analysis_model()'s own bounded retries are exhausted, for the
    calls that use it) the first time this function reaches that task's
    key in `tasks`' own order. Every task was already submitted (running
    concurrently) before any result is read, so a failure is never a
    silently-partial result -- the caller gets one clean exception, the
    same "this analysis failed, full stop" contract run_due_diligence()
    already had when everything was sequential. ThreadPoolExecutor's own
    context-manager exit waits for the rest of this batch to finish
    (success or failure) before that exception reaches the caller, so no
    in-flight call is ever abandoned mid-request either.
    """
    if not tasks:
        return {}

    bound = max_workers if max_workers is not None else len(tasks)

    with concurrent.futures.ThreadPoolExecutor(max_workers=bound) as executor:
        futures = {key: executor.submit(fn) for key, fn in tasks.items()}
        return {key: future.result() for key, future in futures.items()}
