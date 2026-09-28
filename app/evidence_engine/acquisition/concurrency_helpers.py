"""
Bounded concurrency for the acquisition pipeline (Task 21 item 10),
reusing `app.ai.concurrency.run_concurrently` -- one of the four legacy
modules `NEW_ENGINE_ARCHITECTURE.md` Part 1.2 explicitly approves this
package importing (a general bounded-concurrency utility, carved out of
the broader `app.ai.*` ban; see this package's own `__init__.py`).

**Why this thin wrapper exists rather than calling `run_concurrently`
directly from `pipeline.py`.** `run_concurrently`'s own docstring is
explicit: "fails loud, never partial" -- `future.result()` re-raises the
first task's exception in insertion order. That is the CORRECT contract
for its existing legacy call sites (a pillar analysis call failing
really should fail the whole legacy `run_due_diligence()`). It is the
WRONG contract for this pipeline, which item 16 (Task 20) already
established and this task must not weaken: one failed search, one failed
retrieval, or one failed extraction must degrade to an
`AcquisitionQualityFinding` and let every OTHER concurrent call's result
still be used.

`run_concurrently_with_containment()` below closes that gap the only way
that does not touch `run_concurrently` itself (which stays exactly as
legacy code depends on it): each task callable is wrapped so it catches
its OWN exception internally and returns a `_Outcome` instead of letting
it propagate -- `run_concurrently`'s own fail-loud branch can then never
actually trigger, because no wrapped task ever raises. The caller gets
back `{key: _Outcome}` in the SAME deterministic, insertion-order-keyed
shape `run_concurrently` already guarantees (its own docstring's "the
same controlled inputs always produce the same {key: result} mapping" is
unchanged and unweakened by this wrapper).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from app.ai.concurrency import run_concurrently

T = TypeVar("T")


@dataclass(frozen=True)
class Outcome(Generic[T]):
    ok: bool
    value: T | None = None
    error: BaseException | None = None


def run_concurrently_with_containment(
    tasks: dict[str, Callable[[], T]],
    max_workers: int | None = None,
) -> dict[str, Outcome[T]]:
    """Bounded (`max_workers`, an explicit, always-real cap -- never
    unbounded gather), deterministic-by-key result ordering (inherited
    directly from `run_concurrently`), one failure never cancels or
    blocks any other task's result."""

    def _wrap(fn: Callable[[], T]) -> Callable[[], Outcome[T]]:
        def _run() -> Outcome[T]:
            try:
                return Outcome(ok=True, value=fn())
            except Exception as exc:  # noqa: BLE001 -- intentionally contained, never re-raised
                return Outcome(ok=False, error=exc)
        return _run

    wrapped = {key: _wrap(fn) for key, fn in tasks.items()}
    return run_concurrently(wrapped, max_workers=max_workers)
