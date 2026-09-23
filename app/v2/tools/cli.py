#!/usr/bin/env python3
"""
VentureGPS V2 -- local operational CLI for Increment 18.2 (first real Robotics ingestion). See
docs/v2/RUNBOOK_18_2.md for the full walkthrough this was built to run.

SECURITY (Increment 18.2's own explicit requirements):
  - LOCAL ONLY. This is a command-line tool a human runs directly against a database THEY choose explicitly
    (--database-url is REQUIRED, with no environment-variable fallback and no default -- a human can never
    forget to point this somewhere safe). There is no HTTP server, no listening socket, no unauthenticated
    endpoint of any kind anywhere in this module.
  - Every command that would write a canonical fact (decide-company, decide-financing, classify) requires
    BOTH a --confirm flag AND, unless --confirm was given non-interactively, a typed "yes" at an interactive
    prompt that repeats back exactly what is about to happen. Read-only commands (list-*, show-*, verify)
    never prompt.
  - Every human decision requires --as ACTOR_ID (e.g. "admin:jerrod"), which becomes the Authority recorded on
    the decision. There is no default actor: omitting it is a usage error, not a silent guess.
  - This module parses no untrusted network input; `ingest` reads only a local file path the human supplies
    directly on the command line.

ARCHITECTURE (Increment 18.2.1): company-resolution decisions (decide-company) go through
app.v2.resolution.human_review, never app.v2.resolution.promotion directly -- see that module's own docstring
for why (the smallest defensible fix to a real architecture-boundary gap this CLI first exposed, not a broad
grant of promotion access to application/tooling code in general). Financing-resolution and classification
decisions call app.v2.financing_resolution.promotion / app.v2.classification.service directly, unchanged: no
equivalent single-caller restriction exists for either of those two (confirmed by inspection), so no equivalent
wrapper was needed for them.
"""

import argparse
import json
import sys
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.v2.candidates.evidence import verify_proposal
from app.v2.candidates.service import ProposerFailedError, persist_verified_candidates
from app.v2.db.engine import make_engine
from app.v2.domain.candidate import StoredCompanyCandidate
from app.v2.domain.financing import AmountSemantics, FinancingDateKind, FinancingEventCandidateProposal, StoredFinancingEventCandidate
from app.v2.domain.financing_resolution import FactSelection, NO_FACTS
from app.v2.domain.resolution import Authority, human_authority
from app.v2.domain.source import CollectionMethod, Source, SourceType
from app.v2.domain.taxonomy import ClassificationRole
from app.v2.domain.time import EventTime
from app.v2.domain.versions import make_version_id
from app.v2.financing_resolution import promotion as financing_promotion
from app.v2.ingestion.models import IngestionCommand
from app.v2.ingestion.service import ingest_evidence
from app.v2.classification.service import classify_company
from app.v2.observations.hashing import build_raw_payload
from app.v2.observations.media import sniff_media_type
from app.v2.repositories.company_candidates import get_company_candidate, list_company_candidates_for_observation
from app.v2.repositories.financing_event_candidates import get_financing_event_candidate, list_financing_event_candidates_for_observation
from app.v2.repositories.markets import get_market_by_slug, get_taxonomy_version, register_market, register_taxonomy_version
from app.v2.repositories.processing_attempts import get_processing_attempt, mark_failed, mark_processed, start_processing
from app.v2.repositories.raw_payloads import get_raw_payload
from app.v2.repositories.sources import get_source_by_key, register_source
from app.v2.resolution import human_review as company_promotion
from app.v2.domain.capital_signal import build_windows
from app.v2.repositories.capital_metrics import compute_capital_metrics_for_market
from app.v2.repositories.capital_signal import compute_capital_signal_for_market
from app.v2.tools import sec_form_d_collector
from app.v2.tools.form_d_company_proposer import FormDCompanyProposer
from app.v2.tools.form_d_financing_proposer import propose_financing_from_form_d
from app.v2.tools.form_d_xml import FormDParseError
from app.v2.tools.manual_fact import FactNotFoundError, build_manual_amount, build_manual_date, count_occurrences, locate_evidence

MAX_UPLOAD_BYTES = 1024 * 1024  # matches app.v2.ingestion.service's own 1 MiB limit; enforced again here so a
# clearly-oversized file is rejected before it is even read into memory


# ---------------------------------------------------------------- output helpers

def _json_default(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return str(value)


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=_json_default))


def _confirm(prompt: str, *, auto: bool) -> None:
    if auto:
        return
    print(prompt)
    answer = input('Type "yes" to proceed, anything else to cancel: ')
    if answer.strip() != "yes":
        print("Cancelled -- nothing was written.")
        raise SystemExit(1)


# ---------------------------------------------------------------- bootstrap

DEFAULT_TAXONOMY_VERSION = "venturegps_taxonomy.v1"
DEFAULT_ROBOTICS_SLUG = "robotics"
DEFAULT_ROBOTICS_NAME = "Robotics"
SOURCE_SEC_FORM_D = Source(
    source_key="sec_edgar_form_d", name="SEC EDGAR -- Form D filings", source_type=SourceType.GOVERNMENT_REGULATORY,
    collection_method=CollectionMethod.MANUAL_UPLOAD, url="https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets",
    is_active=True,
)
SOURCE_MEDIA_ANNOUNCEMENT = Source(
    source_key="media_funding_announcement", name="Reputable media funding announcement (manual upload)",
    source_type=SourceType.MEDIA_NEWS, collection_method=CollectionMethod.MANUAL_UPLOAD, url=None, is_active=True,
)
# Increment 18.3 -- a SEPARATE source from SOURCE_SEC_FORM_D (which stays MANUAL_UPLOAD, unchanged): this one's
# collection_method is honestly HTTP_FETCH, and keeping it a distinct source_key means every observation's
# provenance (manually uploaded in Increment 18.2 vs automatically collected from here on) stays visible from
# the source alone, not just a code comment.
SOURCE_SEC_FORM_D_AUTO = Source(
    source_key="sec_edgar_form_d_http", name="SEC EDGAR -- Form D filings (automated HTTP collection)",
    source_type=SourceType.GOVERNMENT_REGULATORY, collection_method=CollectionMethod.HTTP_FETCH,
    url="https://www.sec.gov/Archives/edgar/", is_active=True,
)


def cmd_bootstrap(args, engine) -> None:
    """Idempotent: registering an already-registered source/market/taxonomy version is a no-op (see each
    repository function's own duplicate-key handling), so this is always safe to re-run."""
    results = {}
    for source in (SOURCE_SEC_FORM_D, SOURCE_SEC_FORM_D_AUTO, SOURCE_MEDIA_ANNOUNCEMENT):
        existing = get_source_by_key(engine, source.source_key)
        if existing is not None:
            results[source.source_key] = {"already_registered": True, "id": existing.id}
            continue
        registration = register_source(engine, source)
        results[source.source_key] = {"already_registered": False, "id": registration.stored.id}

    existing_taxonomy = get_taxonomy_version(engine, args.taxonomy_version)
    if existing_taxonomy is not None:
        results["taxonomy_version"] = {"already_registered": True, "value": existing_taxonomy.taxonomy_version}
    else:
        taxonomy = register_taxonomy_version(engine, args.taxonomy_version)
        results["taxonomy_version"] = {"already_registered": False, "value": taxonomy.taxonomy_version}

    existing_market = get_market_by_slug(engine, args.market_slug)
    if existing_market is not None:
        results["market"] = {"already_registered": True, "id": str(existing_market.id), "slug": existing_market.slug}
    else:
        market = register_market(engine, args.market_slug, args.market_name)
        results["market"] = {"already_registered": False, "id": str(market.id), "slug": market.slug}

    _print(results)


# ---------------------------------------------------------------- ingest

def cmd_ingest(args, engine) -> None:
    path = Path(args.file)
    if not path.is_file():
        print(f"error: no such file: {path}", file=sys.stderr)
        raise SystemExit(2)
    size = path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        print(f"error: file is {size} bytes, over the {MAX_UPLOAD_BYTES}-byte limit", file=sys.stderr)
        raise SystemExit(2)
    payload_bytes = path.read_bytes()

    event_time = None
    if args.event_date:
        y, m, d = (int(part) for part in args.event_date.split("-"))
        event_time = EventTime.of_day(y, m, d)

    command = IngestionCommand(
        source_key=args.source,
        source_record_identifier=args.record_id,
        observation_type=args.observation_type,
        event_time=event_time,
        observed_time=datetime.now(timezone.utc),
        collection_version=make_version_id("manual_upload", 1),
        collector_id=args.collector,
        declared_media_type=args.declared_media_type,
        payload_bytes=payload_bytes,
        acquisition_key=args.acquisition_key,
    )
    result = ingest_evidence(engine, command)
    _print({
        "observation_id": result.observation.id,
        "payload_created": result.payload_created,
        "observation_created": result.observation_created,
        "sighting_created": result.sighting_created,
        "is_replay": result.is_replay,
        "differences": list(result.differences),
        "sniffed_media_type": result.observation.observation.sniffed_media_type.value,
        "content_hash": result.observation.observation.content_hash,
    })


# ---------------------------------------------------------------- automated SEC collection (Increment 18.3)

def _collect_and_extract_one(engine, cik: str, accession: str, *, dry_run: bool) -> dict:
    """One filing, start to (candidate) finish: fetch -> ingest -> company-candidate extraction. Never resolves
    or promotes anything -- extraction only ever produces untrusted candidates, exactly as in Increment 18.2.
    Returns a status dict the CLI prints directly; never raises for a single filing's ordinary failure modes
    (network/parse/etc.) so a batch can report each item and keep going -- see cmd_collect_form_d_batch."""
    try:
        sec_form_d_collector.validate_cik(cik)
        sec_form_d_collector.validate_accession(accession)
    except sec_form_d_collector.CollectionError as exc:
        return {"cik": cik, "accession": accession, "status": "failed", "reason": str(exc)}

    url = sec_form_d_collector.form_d_primary_document_url(cik, accession)
    if dry_run:
        return {"cik": cik, "accession": accession, "status": "dry_run", "url": url}

    try:
        collected = sec_form_d_collector.collect_form_d_filing(cik, accession)
    except sec_form_d_collector.CollectionError as exc:
        return {"cik": cik, "accession": accession, "status": "failed", "reason": f"{type(exc).__name__}: {exc}"}

    command = IngestionCommand(
        source_key=SOURCE_SEC_FORM_D_AUTO.source_key, source_record_identifier=accession,
        observation_type="sec_form_d_filing", event_time=None, observed_time=collected.fetched_at,
        collection_version=make_version_id("sec_form_d_collector", 1), collector_id="sec_form_d_collector",
        declared_media_type=None, payload_bytes=collected.content,
        acquisition_key=f"sec_form_d_collector:{accession}:{collected.fetched_at.isoformat()}",
    )
    try:
        ingestion = ingest_evidence(engine, command)
    except Exception as exc:  # noqa: BLE001 - a single item's ingestion failure must not abort a batch
        return {"cik": cik, "accession": accession, "status": "failed", "reason": f"ingestion failed: {type(exc).__name__}"}

    observation_id = ingestion.observation.id
    from app.v2.repositories.processing_attempts import get_latest_attempt

    existing_attempt = get_latest_attempt(engine, observation_id, "form_d_company_extractor")
    if existing_attempt is not None and existing_attempt.status.value == "processed":
        existing_candidates = list_company_candidates_for_observation(engine, observation_id)
        return {
            "cik": cik, "accession": accession, "status": "duplicate", "observation_id": observation_id,
            "reason": "already ingested and extracted", "candidate_ids": [c.id for c in existing_candidates],
        }
    if existing_attempt is not None and existing_attempt.status.value == "processing":
        return {"cik": cik, "accession": accession, "status": "failed", "observation_id": observation_id,
                "reason": "an extraction attempt for this observation is already in progress"}

    attempt = start_processing(engine, observation_id, processor_id="form_d_company_extractor",
                               processor_version=make_version_id("form_d_company_extractor", 1))
    try:
        result = persist_verified_candidates(engine, attempt.id, FormDCompanyProposer())
    except ProposerFailedError as exc:
        mark_failed(engine, attempt.id, reason_code="proposer_failed", detail_code=exc.exception_type)
        return {"cik": cik, "accession": accession, "status": "failed", "observation_id": observation_id,
                "reason": f"extraction failed: {exc.exception_type}"}
    mark_processed(engine, attempt.id)

    status = "duplicate" if ingestion.is_replay else "new"
    return {
        "cik": cik, "accession": accession, "status": status, "observation_id": observation_id,
        "candidate_ids": [c.id for c in result.candidates], "pending_review": result.created_count > 0,
    }


def cmd_collect_form_d(args, engine) -> None:
    outcome = _collect_and_extract_one(engine, args.cik, args.accession, dry_run=args.dry_run)
    _print(outcome)
    if outcome["status"] == "failed":
        raise SystemExit(1)


def cmd_discover_form_d(args, engine) -> None:
    try:
        results = sec_form_d_collector.discover_form_d_filings(args.query, max_results=args.max_results)
    except sec_form_d_collector.CollectionError as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    _print([{"cik": r.cik, "accession": r.accession, "display_name": r.display_name, "file_date": r.file_date} for r in results])


def cmd_collect_form_d_batch(args, engine) -> None:
    try:
        discovered = sec_form_d_collector.discover_form_d_filings(args.query, max_results=args.max_results)
    except sec_form_d_collector.CollectionError as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from None

    outcomes = [_collect_and_extract_one(engine, d.cik, d.accession, dry_run=args.dry_run) for d in discovered]
    summary = {"new": 0, "duplicate": 0, "failed": 0, "dry_run": 0}
    for outcome in outcomes:
        summary[outcome["status"]] = summary.get(outcome["status"], 0) + 1
    _print({"query": args.query, "discovered": len(discovered), "summary": summary, "results": outcomes})


# ---------------------------------------------------------------- company extraction

def cmd_extract_company(args, engine) -> None:
    attempt = start_processing(engine, args.observation_id, processor_id="form_d_company_extractor",
                               processor_version=make_version_id("form_d_company_extractor", 1))
    try:
        result = persist_verified_candidates(engine, attempt.id, FormDCompanyProposer())
    except ProposerFailedError as exc:
        mark_failed(engine, attempt.id, reason_code="proposer_failed", detail_code=exc.exception_type)
        print(f"error: proposer failed ({exc.exception_type}); attempt {attempt.id} marked failed", file=sys.stderr)
        raise SystemExit(1) from None
    mark_processed(engine, attempt.id)
    _print({
        "attempt_id": attempt.id,
        "candidates_created": result.created_count,
        "candidate_ids": [c.id for c in result.candidates],
    })


def _print_company_candidate(c: StoredCompanyCandidate) -> None:
    _print({
        "id": c.id, "processing_attempt_id": c.processing_attempt_id, "candidate_ordinal": c.candidate_ordinal,
        "proposed_name": c.proposal.proposed_name, "identifiers": [i.model_dump(mode="json") for i in c.proposal.identifiers],
        "created_at": c.created_at.isoformat(),
    })


def cmd_list_company_candidates(args, engine) -> None:
    candidates = list_company_candidates_for_observation(engine, args.observation_id)
    for c in candidates:
        _print_company_candidate(c)


def cmd_show_company_candidate(args, engine) -> None:
    c = get_company_candidate(engine, args.candidate_id)
    if c is None:
        print("no such candidate", file=sys.stderr)
        raise SystemExit(1)
    payload = get_raw_payload(engine, _observation_content_hash_for_company_candidate(engine, c), verify=True)
    _print_company_candidate(c)
    print("--- name evidence (exact bytes) ---")
    span = c.proposal.name_evidence
    print(payload.payload_bytes[span.byte_start:span.byte_end].decode("utf-8", errors="replace"))


def _observation_content_hash_for_company_candidate(engine, candidate: StoredCompanyCandidate) -> str:
    from app.v2.repositories.company_candidates import load_proposal_context  # only usable while PROCESSING; fine for a just-read attempt in this local tool
    attempt = get_processing_attempt(engine, candidate.processing_attempt_id)
    from app.v2.repositories.observations import get_observation_by_id
    observation = get_observation_by_id(engine, attempt.observation_id)
    return observation.observation.content_hash


def cmd_decide_company(args, engine) -> None:
    authority: Authority = human_authority(args.as_actor)
    action_label = {"create": "CREATE a new canonical Company from", "attach": f"ATTACH to existing company {args.company_id} the",
                    "reject": "REJECT", "defer": "DEFER"}[args.action]
    _confirm(f"About to {action_label} candidate {args.candidate_id}, as {args.as_actor}.", auto=args.confirm)

    if args.action == "create":
        result = company_promotion.create_company_from_candidate(engine, args.candidate_id, authority)
    elif args.action == "attach":
        if not args.company_id:
            print("error: --company-id is required for --action attach", file=sys.stderr)
            raise SystemExit(2)
        result = company_promotion.attach_candidate_to_company(engine, args.candidate_id, uuid.UUID(args.company_id), authority)
    elif args.action == "reject":
        result = company_promotion.reject_candidate(engine, args.candidate_id, authority, args.reason)
    else:
        result = company_promotion.defer_candidate(engine, args.candidate_id, authority, args.reason)

    _print({"decision_id": result.decision.id, "decision_kind": result.decision.decision_kind.value,
           "company_id": str(result.company_id) if result.company_id else None})


# ---------------------------------------------------------------- financing extraction (Form D)

def cmd_extract_financing(args, engine) -> None:
    attempt = start_processing(engine, args.observation_id, processor_id="form_d_financing_extractor",
                               processor_version=make_version_id("form_d_financing_extractor", 1))
    from app.v2.repositories.observations import get_observation_by_id
    observation = get_observation_by_id(engine, args.observation_id)
    payload = get_raw_payload(engine, observation.observation.content_hash, verify=True)
    try:
        proposals: list[FinancingEventCandidateProposal] = propose_financing_from_form_d(payload, uuid.UUID(args.company_id))
    except FormDParseError as exc:
        mark_failed(engine, attempt.id, reason_code="proposer_failed", detail_code="FormDParseError")
        print(f"error: {exc}; attempt {attempt.id} marked failed", file=sys.stderr)
        raise SystemExit(1) from None

    from app.v2.repositories.financing_event_candidates import persist_financing_event_candidates
    result = persist_financing_event_candidates(engine, attempt.id, proposals)
    mark_processed(engine, attempt.id)
    _print({"attempt_id": attempt.id, "candidates_created": result.created_count, "candidate_ids": [c.id for c in result.candidates]})


# ---------------------------------------------------------------- financing extraction (manual / announcement)

def cmd_add_announcement_candidate(args, engine) -> None:
    """A human-guided financing candidate from a SECOND observation (see manual_fact.py's own docstring) --
    NOT automated extraction. `--find` names the exact substring stating the round amount; `--event-find`
    (defaults to the same substring) names the span that shows a financing occurrence is being discussed at
    all."""
    attempt = start_processing(engine, args.observation_id, processor_id="manual_fact_entry",
                               processor_version=make_version_id("manual_fact_entry", 1))
    from app.v2.repositories.observations import get_observation_by_id
    observation = get_observation_by_id(engine, args.observation_id)
    payload = get_raw_payload(engine, observation.observation.content_hash, verify=True)
    raw = payload.payload_bytes

    event_find = args.event_find or args.find
    occurrences = count_occurrences(raw, args.find)
    print(f'"{args.find}" appears {occurrences} time(s) in this payload; using occurrence {args.occurrence}.')

    try:
        amount = build_manual_amount(raw, semantics=AmountSemantics.ANNOUNCED_ROUND_AMOUNT, amount=args.amount,
                                     currency_code=args.currency, evidence_substring=args.find, occurrence=args.occurrence)
        event_evidence = locate_evidence(raw, event_find, occurrence=args.event_occurrence)
        dates = ()
        if args.date and args.date_find:
            dates = (build_manual_date(raw, kind=FinancingDateKind.ANNOUNCEMENT_DATE, iso_date=args.date,
                                       evidence_substring=args.date_find, occurrence=args.date_occurrence),)
    except FactNotFoundError as exc:
        mark_failed(engine, attempt.id, reason_code="proposer_failed", detail_code="FactNotFoundError")
        print(f"error: {exc}; attempt {attempt.id} marked failed", file=sys.stderr)
        raise SystemExit(1) from None

    proposal = FinancingEventCandidateProposal(
        company_id=uuid.UUID(args.company_id), event_evidence=event_evidence, amounts=(amount,), dates=dates,
    )
    from app.v2.repositories.financing_event_candidates import persist_financing_event_candidates
    result = persist_financing_event_candidates(engine, attempt.id, [proposal])
    mark_processed(engine, attempt.id)
    _print({"attempt_id": attempt.id, "candidates_created": result.created_count, "candidate_ids": [c.id for c in result.candidates]})


# ---------------------------------------------------------------- financing candidate inspection / decision

def _print_financing_candidate(c: StoredFinancingEventCandidate) -> None:
    _print({
        "id": c.id, "processing_attempt_id": c.processing_attempt_id, "company_id": str(c.proposal.company_id),
        "stage": c.proposal.stage_value.value, "financing_type": c.proposal.financing_type_value.value,
        "amounts": [{"semantics": a.semantics.value, "money": f"{a.money.currency_code} {a.money.minor_units}"} for a in c.proposal.amounts],
        "dates": [{"kind": d.kind.value, "time": d.time.start.isoformat(), "precision": d.time.precision.value} for d in c.proposal.dates],
    })


def cmd_list_financing_candidates(args, engine) -> None:
    for c in list_financing_event_candidates_for_observation(engine, args.observation_id):
        _print_financing_candidate(c)


def cmd_show_financing_candidate(args, engine) -> None:
    c = get_financing_event_candidate(engine, args.candidate_id)
    if c is None:
        print("no such candidate", file=sys.stderr)
        raise SystemExit(1)
    _print_financing_candidate(c)


_FACT_FIELDS = {"stage", "financing_type", "verified_round_amount", "first_sale_date", "filing_date", "announcement_date"}
_DATE_KIND_BY_NAME = {"first_sale_date": FinancingDateKind.FIRST_SALE_DATE, "filing_date": FinancingDateKind.FILING_DATE,
                      "announcement_date": FinancingDateKind.ANNOUNCEMENT_DATE}


def _parse_facts(spec: str | None) -> FactSelection:
    if not spec:
        return NO_FACTS
    names = {n.strip() for n in spec.split(",") if n.strip()}
    unknown = names - _FACT_FIELDS
    if unknown:
        raise SystemExit(f"error: unknown fact name(s): {sorted(unknown)}; valid: {sorted(_FACT_FIELDS)}")
    return FactSelection(
        stage="stage" in names, financing_type="financing_type" in names, verified_round_amount="verified_round_amount" in names,
        dates=tuple(_DATE_KIND_BY_NAME[n] for n in names if n in _DATE_KIND_BY_NAME),
    )


def cmd_decide_financing(args, engine) -> None:
    authority = human_authority(args.as_actor)
    facts = _parse_facts(args.facts)
    action_label = {"create-event": "CREATE a new canonical FinancingEvent from", "attach-to-event": f"ATTACH to event {args.event_id} the",
                    "reject": "REJECT", "defer": "DEFER"}[args.action]
    _confirm(f"About to {action_label} financing candidate {args.candidate_id}, accepting facts {sorted(f for f in _FACT_FIELDS if getattr(facts, f, False) or (f in _DATE_KIND_BY_NAME and _DATE_KIND_BY_NAME[f] in facts.dates))}, as {args.as_actor}.", auto=args.confirm)

    if args.action == "create-event":
        result = financing_promotion.create_event_from_candidate(engine, args.candidate_id, authority, facts)
    elif args.action == "attach-to-event":
        if not args.event_id:
            print("error: --event-id is required for --action attach-to-event", file=sys.stderr)
            raise SystemExit(2)
        result = financing_promotion.attach_candidate_to_event(engine, args.candidate_id, uuid.UUID(args.event_id), authority, facts)
    elif args.action == "reject":
        result = financing_promotion.reject_candidate(engine, args.candidate_id, authority, args.reason)
    else:
        result = financing_promotion.defer_candidate(engine, args.candidate_id, authority, args.reason)

    _print({
        "decision_id": result.decision.id if result.decision else None, "financing_event_id": str(result.financing_event_id) if result.financing_event_id else None,
        "accepted_stage": result.accepted_stage, "accepted_financing_type": result.accepted_financing_type,
        "accepted_verified_round_amount": result.accepted_verified_round_amount, "accepted_dates": [d.value for d in result.accepted_dates],
    })


# ---------------------------------------------------------------- classification

def cmd_classify(args, engine) -> None:
    authority = human_authority(args.as_actor)
    market = get_market_by_slug(engine, args.market_slug)
    if market is None:
        print(f"error: no market registered with slug {args.market_slug!r} (run bootstrap first)", file=sys.stderr)
        raise SystemExit(1)
    role = ClassificationRole(args.role)
    _confirm(f"About to classify company {args.company_id} into market {args.market_slug!r} ({role.value}) under taxonomy {args.taxonomy_version!r}, as {args.as_actor}.", auto=args.confirm)
    result = classify_company(engine, uuid.UUID(args.company_id), market.id, args.taxonomy_version, role, authority)
    _print({"classification_id": result.classification.id, "company_id": str(result.classification.company_id),
           "market_id": str(result.classification.market_id), "role": result.classification.role.value})


# ---------------------------------------------------------------- verify

def cmd_verify(args, engine) -> None:
    market = get_market_by_slug(engine, args.market_slug)
    if market is None:
        print(f"error: no market registered with slug {args.market_slug!r}", file=sys.stderr)
        raise SystemExit(1)
    if args.as_of:
        y, m, d = (int(part) for part in args.as_of.split("-"))
        as_of = datetime(y, m, d, tzinfo=timezone.utc)
    else:
        as_of = datetime.now(timezone.utc)
    current_window, _historical = build_windows(as_of)
    metrics = compute_capital_metrics_for_market(engine, market.id, args.taxonomy_version, current_window[0], current_window[1])
    signal = compute_capital_signal_for_market(engine, market.id, args.taxonomy_version, as_of)
    _print({"market": {"id": str(market.id), "slug": market.slug, "display_name": market.display_name}, "metrics": metrics, "signal": signal})


# ---------------------------------------------------------------- argparse wiring

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="v2-cli", description=__doc__)
    parser.add_argument("--database-url", required=True, help="the V2 Postgres database to operate on (REQUIRED, no default, no env fallback)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("bootstrap", help="idempotently register the sources, taxonomy version and Robotics market")
    p.add_argument("--taxonomy-version", default=DEFAULT_TAXONOMY_VERSION)
    p.add_argument("--market-slug", default=DEFAULT_ROBOTICS_SLUG)
    p.add_argument("--market-name", default=DEFAULT_ROBOTICS_NAME)
    p.set_defaults(func=cmd_bootstrap)

    p = sub.add_parser("ingest", help="ingest a local evidence file")
    p.add_argument("--source", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--record-id", default=None)
    p.add_argument("--observation-type", required=True)
    p.add_argument("--event-date", default=None, help="YYYY-MM-DD, if known")
    p.add_argument("--collector", default="venturegps_v2_cli")
    p.add_argument("--declared-media-type", default=None)
    p.add_argument("--acquisition-key", required=True)
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("collect-form-d", help="fetch one real Form D filing from SEC EDGAR and run it through ingestion + company-candidate extraction")
    p.add_argument("--cik", required=True)
    p.add_argument("--accession", required=True, help="NNNNNNNNNN-NN-NNNNNN")
    p.add_argument("--dry-run", action="store_true", help="validate and print the URL that would be fetched; no network, no database writes")
    p.set_defaults(func=cmd_collect_form_d)

    p = sub.add_parser("discover-form-d", help="bounded search of SEC EDGAR's own full-text search API for candidate Form D filings (read-only, never collects)")
    p.add_argument("--query", required=True)
    p.add_argument("--max-results", type=int, default=sec_form_d_collector.MAX_DISCOVERY_RESULTS)
    p.set_defaults(func=cmd_discover_form_d)

    p = sub.add_parser("collect-form-d-batch", help="bounded discovery + collection: discover, then collect+extract each result, reporting new/duplicate/failed")
    p.add_argument("--query", required=True)
    p.add_argument("--max-results", type=int, default=sec_form_d_collector.MAX_DISCOVERY_RESULTS)
    p.add_argument("--dry-run", action="store_true", help="discover and report what would be collected; no network fetch of any filing, no database writes")
    p.set_defaults(func=cmd_collect_form_d_batch)

    p = sub.add_parser("extract-company", help="run the Form D company proposer against an observation")
    p.add_argument("--observation-id", type=int, required=True)
    p.set_defaults(func=cmd_extract_company)

    p = sub.add_parser("list-company-candidates")
    p.add_argument("--observation-id", type=int, required=True)
    p.set_defaults(func=cmd_list_company_candidates)

    p = sub.add_parser("show-company-candidate")
    p.add_argument("candidate_id", type=int)
    p.set_defaults(func=cmd_show_company_candidate)

    p = sub.add_parser("decide-company", help="human decision on a company candidate")
    p.add_argument("candidate_id", type=int)
    p.add_argument("--action", required=True, choices=["create", "attach", "reject", "defer"])
    p.add_argument("--company-id", default=None)
    p.add_argument("--reason", default=None)
    p.add_argument("--as", dest="as_actor", required=True, help='human actor id, e.g. "admin:jerrod"')
    p.add_argument("--confirm", action="store_true", help="skip the interactive yes/no prompt")
    p.set_defaults(func=cmd_decide_company)

    p = sub.add_parser("extract-financing", help="run the Form D financing proposer against an observation for an ALREADY-canonical company")
    p.add_argument("--observation-id", type=int, required=True)
    p.add_argument("--company-id", required=True)
    p.set_defaults(func=cmd_extract_financing)

    p = sub.add_parser("add-announcement-candidate", help="human-guided financing candidate from a second (non-Form-D) observation")
    p.add_argument("--observation-id", type=int, required=True)
    p.add_argument("--company-id", required=True)
    p.add_argument("--amount", required=True, help="decimal amount, e.g. 125000000")
    p.add_argument("--currency", default="USD")
    p.add_argument("--find", required=True, help="exact substring the announcement states the amount in")
    p.add_argument("--occurrence", type=int, default=0)
    p.add_argument("--event-find", default=None, help="defaults to --find")
    p.add_argument("--event-occurrence", type=int, default=0)
    p.add_argument("--date", default=None, help="YYYY-MM-DD announcement date, if adding one")
    p.add_argument("--date-find", default=None)
    p.add_argument("--date-occurrence", type=int, default=0)
    p.set_defaults(func=cmd_add_announcement_candidate)

    p = sub.add_parser("list-financing-candidates")
    p.add_argument("--observation-id", type=int, required=True)
    p.set_defaults(func=cmd_list_financing_candidates)

    p = sub.add_parser("show-financing-candidate")
    p.add_argument("candidate_id", type=int)
    p.set_defaults(func=cmd_show_financing_candidate)

    p = sub.add_parser("decide-financing", help="human decision on a financing candidate")
    p.add_argument("candidate_id", type=int)
    p.add_argument("--action", required=True, choices=["create-event", "attach-to-event", "reject", "defer"])
    p.add_argument("--event-id", default=None)
    p.add_argument("--facts", default=None, help="comma-separated: stage,financing_type,verified_round_amount,first_sale_date,filing_date,announcement_date")
    p.add_argument("--reason", default=None)
    p.add_argument("--as", dest="as_actor", required=True)
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=cmd_decide_financing)

    p = sub.add_parser("classify", help="human decision: classify a company into a market")
    p.add_argument("--company-id", required=True)
    p.add_argument("--market-slug", default=DEFAULT_ROBOTICS_SLUG)
    p.add_argument("--taxonomy-version", default=DEFAULT_TAXONOMY_VERSION)
    p.add_argument("--role", default="primary", choices=["primary", "secondary"])
    p.add_argument("--as", dest="as_actor", required=True)
    p.add_argument("--confirm", action="store_true")
    p.set_defaults(func=cmd_classify)

    p = sub.add_parser("verify", help="print Capital Metrics + Capital Signal for a market (read-only, proves the end-to-end result)")
    p.add_argument("--market-slug", default=DEFAULT_ROBOTICS_SLUG)
    p.add_argument("--taxonomy-version", default=DEFAULT_TAXONOMY_VERSION)
    p.add_argument("--as-of", default=None, help="YYYY-MM-DD, defaults to today")
    p.set_defaults(func=cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    engine = make_engine(args.database_url, pooled=False)
    try:
        args.func(args, engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
