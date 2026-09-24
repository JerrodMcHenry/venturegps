"""
Bounded, lock-protected, job-history-tracked collection runs (Increment 18.5).

run_bounded_collection() is the ONE new orchestration function this increment adds. It does not reimplement
collection: every filing still goes through app.v2.tools.cli._collect_and_extract_one, the exact same function
`collect-form-d-batch` already used and 18.3 already tested (bounded discovery, SSRF/redirect/size/rate-limit
controls, no automatic canonical promotion). What this module adds on top is purely operational:

  1. acquire the single-active-run lock (app.v2.repositories.collection_runs.start_run; the database's own
     partial unique index is the actual lock, not anything held in this process's memory)
  2. run the existing bounded pipeline, unchanged
  3. record what happened as a terminal, immutable v2.collection_run row

This is deliberately a plain function that returns and exits -- NOT a long-running scheduler, per Increment
18.5's explicit decision. An external cron service invokes the `run-collection` CLI command (which calls this
function) on whatever interval it configures; nothing in this codebase loops or sleeps waiting for the next run.

Imports app.v2.tools.cli (not the reverse) to reuse _collect_and_extract_one and SOURCE_SEC_FORM_D_AUTO without
duplicating either -- see cli.py's own cmd_run_collection for the CLI entry point, which imports this module
lazily (a function-local import) specifically to keep this the one-directional edge.
"""

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.v2.domain.collection import CollectionRunStatus, CollectionTriggerType, StoredCollectionRun, validate_job_name
from app.v2.repositories.collection_runs import (
    DEFAULT_LEASE_SECONDS,
    CollectionAlreadyRunningError,
    complete_run,
    recover_interrupted_runs,
    start_run,
)
from app.v2.tools import sec_form_d_collector

DEFAULT_JOB_NAME = "sec_form_d"
MAX_RESULT_DETAIL_CHARS = 20000  # matches ck_collection_run_result_detail_len (migration 0011)


def _json_default(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return str(value)


def _bounded_result_detail(payload: dict) -> str:
    """Serialize and cap the per-filing outcome summary. Every field already in an outcome dict
    (cli._collect_and_extract_one's own return shape: cik, accession, status, reason, observation_id,
    candidate_ids) is already sanitized -- no raw evidence text, no exception message beyond a static
    CollectionError string or an exception TYPE name (see docs/v2/SEC_COLLECTION_SECURITY.md). Truncating here
    is a size bound, not a redaction -- redaction already happened upstream."""
    text = json.dumps(payload, default=_json_default)
    if len(text) <= MAX_RESULT_DETAIL_CHARS:
        return text
    return text[: MAX_RESULT_DETAIL_CHARS - 20] + '..."truncated"}'


def run_bounded_collection(
    engine,
    *,
    query: str,
    max_filings: int,
    trigger_type: CollectionTriggerType,
    triggered_by: str,
    job_name: str = DEFAULT_JOB_NAME,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    dry_run: bool = False,
) -> StoredCollectionRun:
    """One bounded collection attempt, start to finish, always returning a TERMINAL StoredCollectionRun (never
    leaves a row 'running'). Raises CollectionAlreadyRunningError immediately, before touching the network or
    creating a run row, if another run for this job_name is already active -- "no overlapping collection runs"
    enforced by the database, checked here first for a fast, clean refusal.

    Never promotes anything: exactly like collect-form-d-batch, this can only ever create untrusted candidates
    (via the existing extraction pipeline) -- no Company, FinancingEvent, or resolution decision is ever
    created here, scheduled or manual."""
    job_name = validate_job_name(job_name)

    # Best-effort, always-safe: free up any lock a crashed prior run left behind before trying to acquire it.
    # Never raises for "nothing to recover" -- an empty list is the normal case.
    recover_interrupted_runs(engine, job_name=job_name)

    run = start_run(  # raises CollectionAlreadyRunningError here if the lock is still held by a live run
        engine, job_name=job_name, trigger_type=trigger_type, triggered_by=triggered_by,
        query=query, max_filings=max_filings, lease_seconds=lease_seconds,
    )

    from app.v2.tools import cli  # local import: see module docstring -- keeps this the one-directional edge

    try:
        discovered = sec_form_d_collector.discover_form_d_filings(query, max_results=max_filings)
    except sec_form_d_collector.CollectionError as exc:
        return complete_run(
            engine, run.id, status=CollectionRunStatus.FAILED, discovered_count=0, collected_count=0,
            duplicate_count=0, failed_count=0, candidate_count=0,
            failure_detail=f"discovery_failed:{type(exc).__name__}",
        )

    if dry_run:
        return complete_run(
            engine, run.id, status=CollectionRunStatus.SUCCEEDED, discovered_count=len(discovered),
            collected_count=0, duplicate_count=0, failed_count=0, candidate_count=0,
            result_detail=_bounded_result_detail({"dry_run": True, "discovered": len(discovered)}),
        )

    outcomes = [cli._collect_and_extract_one(engine, d.cik, d.accession, dry_run=False) for d in discovered]

    collected = sum(1 for o in outcomes if o["status"] == "new")
    duplicate = sum(1 for o in outcomes if o["status"] == "duplicate")
    failed = sum(1 for o in outcomes if o["status"] == "failed")
    candidate_count = sum(len(o.get("candidate_ids") or []) for o in outcomes)

    if failed == 0:
        status = CollectionRunStatus.SUCCEEDED
    elif collected > 0 or duplicate > 0:
        status = CollectionRunStatus.PARTIAL
    else:
        status = CollectionRunStatus.FAILED

    failure_detail = None
    if failed > 0:
        failure_detail = f"{failed} of {len(discovered)} filing(s) failed collection or extraction"

    return complete_run(
        engine, run.id, status=status, discovered_count=len(discovered), collected_count=collected,
        duplicate_count=duplicate, failed_count=failed, candidate_count=candidate_count,
        failure_detail=failure_detail, result_detail=_bounded_result_detail({"discovered": len(discovered), "results": outcomes}),
    )


__all__ = ["DEFAULT_JOB_NAME", "run_bounded_collection", "CollectionAlreadyRunningError"]
