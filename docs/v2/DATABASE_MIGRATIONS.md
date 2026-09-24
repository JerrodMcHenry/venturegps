# VentureGPS V2 database migrations and test databases

Status: Phase 1, Increment 2. See ADR-0001 for the truth model.

## Architecture

| Piece | Location |
|---|---|
| Alembic config | `alembic.ini` (repo root; no database URL in it) |
| Environment | `app/v2/migrations/env.py` |
| Revisions | `app/v2/migrations/versions/` (numbered `0001_...`) |
| V2 config (lazy env reads) | `app/v2/config.py` |
| Engine factory (lazy, small pool) | `app/v2/db/engine.py` |
| Schema metadata | `app/v2/db/metadata.py` |
| Table definitions (shape only; one per increment) | `app/v2/db/tables.py` |
| Source persistence | `app/v2/repositories/sources.py` (+ `errors.py`) |
| Evidence persistence | `app/v2/repositories/raw_payloads.py`, `observations.py`, `sightings.py` |
| Candidate layer | `app/v2/candidates/` (`proposer.py`, `evidence.py`, `service.py`), `app/v2/repositories/company_candidates.py`, `app/v2/domain/candidate.py` |
| Processing history | `app/v2/repositories/processing_attempts.py`, `app/v2/domain/processing_attempt.py` |
| Evidence ingestion workflow | `app/v2/ingestion/` (`service.py`, `models.py`, `errors.py`) |
| What Alembic may see | `app/v2/db/scope.py` |
| Migration lock | `app/v2/db/locks.py` |

- **Schema `v2`, version table `v2.alembic_version`.** Never `public`.
- **Legacy is not adopted.** No baseline, no stamp, no conversion of legacy DDL.
  Legacy `add_*()` functions are frozen and untouched. V2 migrations do not depend
  on any legacy object existing.
- **Scoping is fail-closed and two-layered.** `include_name` stops Alembic from
  reflecting any schema except `v2` (including the default schema, where legacy
  tables live); `include_object` admits only objects belonging to a `v2` table.
  `alembic check` with legacy tables present reports no drift.
- **Never automatic.** Migrations do not run at import or FastAPI startup, and V2
  application code may not call `alembic.command` (enforced by a test).
- **The engine is lazy.** Importing `app.v2.config` / `app.v2.db.*` reads no
  environment, opens no connection and needs no AI configuration (tested in a clean
  subprocess with `create_engine` and `psycopg2.connect` booby-trapped).
  Pool: 2 + 2 overflow, `pool_pre_ping`, `application_name=venturegps-v2`.

### Bootstrap and teardown

Alembic creates its version table before running any revision, and that table lives
in `v2`, so the schema must already exist. `env.py` therefore runs
`CREATE SCHEMA IF NOT EXISTS v2` first, but only for commands that upgrade or stamp
to a revision. `current`, `heads`, `history` and `check` create nothing.

Revision `0001` records the namespace (idempotent `CREATE SCHEMA IF NOT EXISTS`
plus a comment on the schema) and creates no tables. Its downgrade removes the
comment. When a downgrade reverts everything to base, `env.py` then drops
`v2.alembic_version` and schema `v2` in the same transaction; `DROP SCHEMA` has no
`CASCADE`, so if anything else lives in `v2` the entire downgrade rolls back.

### Revision 0002: `v2.source`

The persisted form of the pure `Source` model (`app/v2/domain/source.py`). Identity is a
generated `id` plus the unique `source_key`; name and URL are data, never identity.

| Column | Type | Notes |
|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | primary key `pk_source` |
| `source_key` | `TEXT NOT NULL` | `uq_source_source_key`; shape check `^[a-z][a-z0-9_]{1,63}$` |
| `source_name` | `TEXT NOT NULL` | no surrounding spaces, 1-200 chars, no control characters |
| `source_type` | `TEXT NOT NULL` | `CHECK IN` the nine `SourceType` values |
| `collection_method` | `TEXT NOT NULL` | `CHECK IN` the five `CollectionMethod` values |
| `source_url` | `TEXT NULL` | null allowed; if set: <= 2048, printable ASCII, `http(s)://host`, no userinfo |
| `is_active` | `BOOLEAN NOT NULL` | no default: it must be stated |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | database-assigned, immutable |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | moves only when a mutable field changes |

Also `CHECK (updated_at >= created_at)`.

- **Enums are `TEXT` + named `CHECK`s, not PostgreSQL `ENUM` types.** Extending a vocabulary is
  one constraint swap in an ordinary transactional migration; `ENUM` values cannot be removed
  and `ADD VALUE` has transaction restrictions. The Python enums stay authoritative; the
  CHECKs guard integrity and are deliberately a subset of the domain rules (for example the
  database trims only spaces where the domain rejects any surrounding whitespace, so a row the
  database accepts can still be refused by the domain on load and is reported, not returned).
- **Immutable after insert: `id`, `source_key`, `source_type`, `collection_method`,
  `created_at`. Mutable: `source_name`, `source_url`, `is_active`.** One
  `BEFORE INSERT OR UPDATE` trigger (`v2.source_guard`) enforces this for every writer,
  including direct SQL, and rejects an update that bundles a legal change with an illegal one
  as a whole. It also owns the timestamps: `created_at` is always the database clock (a
  caller-supplied value is overwritten), and `updated_at` moves only when a mutable field
  actually changes (a no-op update, or a caller-supplied `updated_at`, does not).
- **Repository semantics.** `register_source` is create-only with idempotent replay: a new key
  is created; an existing key with the same `source_type` and `collection_method` returns the
  existing Source unchanged (registration never rewrites name/url/is_active); a different
  `source_type` or `collection_method` raises `ConflictError`. There is no delete operation:
  a Source is deactivated (`is_active = false`), which keeps the row and changes nothing else.

### Revision 0003: `v2.raw_payload` and `v2.observation` (immutable evidence)

Storage and integrity only. Ingestion, sightings and processing state come in later increments.

**`v2.raw_payload`**: the exact received bytes, content-addressed.

| Column | Type | Notes |
|---|---|---|
| `content_hash` | `TEXT` | primary key: `sha256(bytes)`, lowercase hex |
| `storage_kind` | `TEXT NOT NULL` | `CHECK IN ('inline')`; leaves room for external storage later |
| `size_bytes` | `BIGINT NOT NULL` | `0 <= size <= 1048576` (1 MiB, `MAX_INLINE_PAYLOAD_BYTES`) |
| `payload_bytes` | `BYTEA` | present iff `storage_kind = 'inline'`; length must equal `size_bytes` |

A CHECK recomputes `sha256(payload_bytes)` and compares it to the key, so the database itself
refuses bytes that do not match their hash. The repository computes the hash; a caller never
supplies one. Identical bytes are stored once. Reads verify the hash and size and raise
`InvariantViolationError` on a mismatch (corrupted evidence fails loudly and is never repaired).
The 1 MiB limit is defined once in `app/v2/domain/payload.py`; the migration carries the literal
(migrations are frozen snapshots) and a test asserts they agree. Oversize is rejected, never truncated.

**`v2.observation`**: "this Source exposed these bytes at this observed time". Evidence only.

| Column | Notes |
|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` |
| `source_id` | FK to `v2.source(id)`, `ON DELETE RESTRICT` |
| `source_record_identifier` | nullable; 1-512 chars, no control characters |
| `observation_type` | slug shape |
| `event_time`, `event_time_precision` | both NULL (unknown) or both set; precision in `instant/day/month/year`; a CHECK forbids a start with finer detail than its precision |
| `observed_time` | `NOT NULL`, caller-supplied |
| `recorded_time` | `NOT NULL`, **assigned by a trigger** (`clock_timestamp()`), never by the caller |
| `collection_version`, `collector_id` | shape-checked |
| `content_hash` | FK to `v2.raw_payload`, `ON DELETE RESTRICT` |
| `declared_media_type` | nullable; normalized `type/subtype` shape |
| `sniffed_media_type` | one of the five stored values (`unknown` included) |

There is no status, AI, company or interpretation column, and media agreement is **derived** from
declared and sniffed (not stored). No ordering between `event_time` and `observed_time` is enforced.

- **Dedup identity** is `(source_id, source_record_identifier, content_hash)`, where "no record
  identifier" is a value. Ordinary `UNIQUE` treats NULLs as distinct, and `UNIQUE NULLS NOT
  DISTINCT` needs PostgreSQL 15, so identity is two partial unique indexes:
  `uq_observation_dedup_with_record_id` (identifier present) and
  `uq_observation_dedup_without_record_id` (`(source_id, content_hash)` where it is absent).
  Storing an existing identity returns the existing, unmodified Observation (a later increment
  records a re-acquisition as a sighting).
- **Append-only, for every writer:** `UPDATE`, `DELETE` and `TRUNCATE` on both tables are rejected
  by trigger (`restrict_violation`), including no-op updates and `INSERT ... ON CONFLICT DO UPDATE`.
  Both foreign keys are `RESTRICT`, so a Source or payload that evidence references cannot be
  removed. (A superuser who disables triggers or drops constraints can still defeat this; that is an
  operator action, not a normal path.)
- **Downgrade** from 0003 removes only these objects and **refuses to run while either table holds
  rows**: back the evidence up and drop the tables by hand if you truly mean to discard it.

### Revision 0004: `v2.observation_sighting` (acquisition history)

An Observation says "this Source exposed this evidence record". A **Sighting** says "VentureGPS
acquired (saw) it at this time". Only the second distinguishes "we checked and saw the same
evidence again" from "we did not check", which later coverage measurement depends on.

| Column | Notes |
|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` |
| `observation_id` | `NOT NULL`, FK to `v2.observation(id)` `ON DELETE RESTRICT` |
| `observed_time` | `NOT NULL`: when THIS acquisition happened (includes the first acquisition) |
| `recorded_time` | `NOT NULL`, assigned by trigger, never by the caller |
| `collector_id`, `collection_version` | shape-checked, same rules as `v2.observation` |
| `acquisition_key` | `NOT NULL`, 1-128 chars from `A-Za-z0-9_.:@/=+-` |

No payload bytes, Source fields, status, AI or interpretation columns.

- **Idempotency: `UNIQUE (observation_id, acquisition_key)`.** The key identifies one acquisition
  *event* and is chosen by the collector boundary (for example from its run and fetch identity). It
  must not be generated randomly inside a retry, or replays would stop being idempotent. It is unique
  *per Observation*, not globally, so one collection run may reuse a single key across many records.
  The same Observation seen at 10:00 and 11:00 (two keys) yields two sightings; replaying the 10:00
  command yields none. Neither `observation_id` nor `(observation_id, observed_time)` is unique.
- **Append-only** reuses the 0003 functions `v2.forbid_evidence_change()` (row-level UPDATE/DELETE and
  statement-level TRUNCATE) and `v2.observation_stamp()` (database-owned `recorded_time`); no new function.
- **Downgrade** removes only this table and refuses to run while it holds rows.

**Temporal semantics.** `Observation.observed_time` is the FIRST time VentureGPS observed this exact
Observation identity and is never rewritten. `ObservationSighting.observed_time` is each acquisition,
including the first. **Out-of-order sightings are recorded as-is** (policy A): a delayed collector's
sighting may be earlier than the Observation's `observed_time`, and neither the Observation nor any
earlier sighting is rewritten. Sightings are listed by `(observed_time, id)`.

### Evidence ingestion (`ingest_evidence`)

`ingest_evidence(db, IngestionCommand)` is the only workflow in this increment: bytes already supplied
by a trusted collector boundary become RawPayload + Observation + Sighting, atomically. No network, no
scheduling, no AI, no processing.

1. resolve the Source (missing: `NotFoundError`); 2. require it active (`SourceInactiveError`; ingestion
*policy*, not a table constraint, so deactivating a Source never touches existing evidence);
3. validate size and hash the exact bytes (over 1 MiB: `UnsupportedInputError`, nothing truncated);
4. sniff the media type from the bytes; 5. normalize the declared type (malformed: `InvalidInputError`);
6. build the Observation (agreement is derived; a declared/sniffed **conflict is persisted, never a reason
to reject**, and unknown media is valid evidence); 7. store or reuse the payload; 8. store or reuse the
Observation (identity: source, record identifier including "none", content hash); 9. store or reuse the
Sighting (identity: observation + `acquisition_key`).

The command carries no `content_hash`, `sniffed_media_type`, `recorded_time`, status, AI output or company
identity, and its model rejects them. Everything runs in one transaction (a SAVEPOINT when handed a
Connection), so a failure leaves no partial payload, observation or sighting; PostgreSQL constraints are the
final authority under concurrency. A repeat acquisition of identical evidence reuses the payload and the
Observation and adds a Sighting; if the repeat's non-identity metadata differs, the existing Observation stays
canonical and the difference is reported in `IngestionResult.differences`, never stored.

### Revision 0005: `v2.processing_attempt` (processing history)

A ProcessingAttempt records "VentureGPS attempted to process this immutable Observation using this
versioned processor". It is operational history: not evidence, canonical truth, an Observation status, an
AI result or a candidate. **Observations never change and hold no processing status; "collected but not
processed" is the absence of any attempt** (`list_unprocessed_observation_ids`), never a stored state.

| Column | Notes |
|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` |
| `observation_id` | `NOT NULL`, FK `ON DELETE RESTRICT` |
| `processor_id` | slug, 2-64 chars; identifies the processing implementation (no registry) |
| `processor_version` | `VersionId` whose name must equal `processor_id` (`fin_extractor.v2` for `fin_extractor`) |
| `attempt_number` | `INTEGER >= 1`, linear per `(observation_id, processor_id)` **regardless of version** |
| `status` | `processing / processed / failed / quarantined` (`TEXT` + `CHECK`; no stored "collected") |
| `started_at` | database clock, set by trigger on insert |
| `finished_at` | NULL while processing; database clock, set by trigger on the transition |
| `lease_expires_at` | NOT NULL while processing, NULL once terminal |
| `reason_code`, `detail_code` | bounded machine codes (`^[a-z][a-z0-9_]{1,63}$`); reason required for failed/quarantined, absent otherwise |

- **Legal state combinations** are one CHECK: processing = no finish, a lease, no failure metadata;
  processed = finished, no lease, no failure metadata; failed/quarantined = finished, no lease, reason required.
- **Attempt numbers and concurrency.** `UNIQUE (observation_id, processor_id, attempt_number)` and a partial
  unique index `(observation_id, processor_id) WHERE status = 'processing'` are the final authority. The
  repository also serialises starts by locking the Observation row `FOR NO KEY UPDATE` (a lock, never a
  write), so a losing concurrent start gets a clean `ConflictError(attempt_already_active)`, not an error.
- **Lifecycle trigger** (`v2.processing_attempt_guard`, specific to this table): inserts must be `processing`
  with a database `started_at`; `id`, `observation_id`, `processor_id`, `processor_version`, `attempt_number`
  and `started_at` never change; a terminal row is immutable; a processing row may renew its lease (forward
  only) or make one transition to a terminal state, when `finished_at` becomes the database clock. `DELETE` and
  `TRUNCATE` are rejected (history is never removed) by reusing `v2.forbid_evidence_change()`.
- **Leases.** A lease is a duration chosen by the caller (1 s to 24 h, default 300 s); all timestamps are the
  database's. An expired lease is **not** a state change: the attempt stays `processing` until
  `fail_expired_attempt` marks it `failed` with reason `lease_expired`. It is refused if the lease is still live
  or the attempt is already terminal. A lease can be renewed while `processing` (expired or not) and is never
  shortened. `as_of` lets tests supply the clock; workers should use the default database clock.
- **Retry and reprocessing policy** (`check_may_start_attempt`): none yet -> attempt 1; `processing` -> conflict;
  `failed` -> retry under any version; `processed` or `quarantined` -> only a **later** processor version
  (never automatically for the same or an older one). A retry is always a NEW attempt; nothing goes back to
  `processing`.
- **Failure metadata never carries payload excerpts, exception text, stack traces, prompts or AI output.**
- **Downgrade** removes only this table and function and refuses to run while any attempt exists.

### Revision 0006: `v2.company_candidate` and `v2.company_candidate_identifier` (untrusted proposals)

```
Source -> RawPayload -> Observation -> ProcessingAttempt -> Candidate -> [future validation / resolution / promotion] -> canonical truth
```

A **Candidate is a proposal**: "processor attempt X proposed that this evidence may describe company Y,
here are the exact immutable bytes supporting that". It is **not** canonical truth, a Company, a claim, a
classification or an accepted AI answer, and **nothing in this increment can promote one**: no canonical,
resolution or claim table exists at this revision (revision 0007 adds the explicit resolution boundary), and the
candidate layer may not import a resolution/promotion package (architecture-tested). The tables carry table comments
saying UNTRUSTED.

- **Shape.** A candidate belongs to exactly one ProcessingAttempt (which already identifies the Observation,
  processor, version and attempt number, so none of that is duplicated). Identity is
  `(processing_attempt_id, candidate_ordinal)`: the ordinal is the proposal's position in the proposer's
  output, so replays are idempotent and a **name is never identity**. One Observation may yield zero, one or
  many candidates, and later attempts/versions add history without touching earlier candidates. Identifiers
  (`domain`, `website_url` only) live in `company_candidate_identifier`. `created_at` is the database's; there is
  no `updated_at`; there are no confidence, model, provider, prompt or canonical columns.
- **Evidence locator** (on every proposed value, so a value cannot exist without one): `byte_start`, `byte_end`
  (half-open, at most 4096 bytes) and `evidence_hash` = sha256 of exactly those bytes of the immutable payload.
  Byte offsets only: character offsets are never used. Evidence is restricted to **text-like** payloads
  (`text/plain`, `text/html`, `application/json`); binary/PDF evidence is refused (no OCR, no PDF parsing).
- **Verification** (`app.v2.candidates.evidence`, pure, before anything is stored): media type is text-like;
  the span lies inside the payload; the exact bytes hash to `evidence_hash`; and the proposed value literally
  appears in those bytes (a domain is compared ASCII-case-insensitively). Nothing is repaired or fuzzy-matched.
  "Validated" means the proposal is well-formed and its cited evidence exists and contains the value, **not** that
  the proposed company is real.
- **Database backstop** (`BEFORE INSERT` triggers): the attempt must be `processing` (row-locked `FOR SHARE`, so it
  cannot finish underneath the write), and the evidence span must lie inside the observation's stored payload and hash
  to the stored `evidence_hash` (via `substring`/`sha256` over the exact bytes). `UPDATE`/`DELETE`/`TRUNCATE` are
  rejected on both tables (reusing `v2.forbid_evidence_change()`); FKs are `RESTRICT`.
- **Workflow** (`persist_verified_candidates`): require a PROCESSING attempt, load the verified immutable evidence,
  call the `CandidateProposer` with only the `Observation` and `RawPayload` (never a database handle), validate the
  schema, verify every proposal's evidence, persist all atomically (one bad proposal rejects the whole batch), return
  them. It does **not** mark the attempt processed: completion stays explicit. A proposer exception leaves no rows and
  surfaces as `ProposerFailedError` with a static message (the exception text may contain evidence and is never copied).
- **Downgrade** removes only these objects and refuses to run while any candidate exists.

### Revision 0007: `v2.resolution_decision`, `v2.company`, `v2.company_name`, `v2.company_identifier` (the resolution boundary)

```
Observation -> ProcessingAttempt -> CompanyCandidate [UNTRUSTED] -> ResolutionDecision [rule or human] -> Company [TRUSTED IDENTITY]
```

Four distinct concepts. **AI may propose. AI may not decide. AI may not promote.** A candidate becomes canonical
identity only through a `ResolutionDecision` made by a deterministic **rule** or a **human**; validation, a high
confidence or agreement between models is never a reason. There is no AI authority to misuse: `decided_by_kind` is
CHECKed to `rule | human` (no enum, no third value, no AI table), actor ids are bounded shapes (`admin:jerrod`,
`exact_identifier_match.v1`), and ids that name an AI system are refused in Python and in the database.

- **`resolution_decision`** (append-only): `candidate_id`, `decision_kind` (`create_company` | `attach_to_company` |
  `reject_candidate` | `defer_candidate`), `company_id` (required for create/attach, forbidden otherwise), `decided_by_kind`,
  `decided_by_id`, `reason_code` (required for reject/defer), database-owned `created_at`. A **rule may only attach**
  (CHECK), and the insert trigger re-verifies that the candidate's identifiers exactly match ONE company. At most one
  **final** decision (create/attach/reject) exists per candidate (partial unique index), and nothing may follow a final
  decision (the trigger row-locks the candidate, then looks). `defer` is recorded but not final. A Company has at most
  one `create_company` decision.
- **`company`**: a bare anchor, `id UUID` (database-generated; a writer-supplied id is overwritten) and `created_at`.
  Identity is not a name, domain, URL, candidate id or model id, so it survives renames and domain changes, and names are
  not unique. A **deferred constraint trigger** refuses to commit a Company without a `create_company` decision and a
  canonical name, so even direct SQL cannot mint a Company with no provenance.
- **`company_name`** (`canonical` | `alias`) and **`company_identifier`** (`domain` | `website_url`): accepted facts, each
  naming the decision that accepted it and the candidate (identifier) it came from. Only a **human** decision can accept
  facts (a rule accepts nothing new). One canonical name per company. `(identifier_type, identifier_value)` is unique
  across all companies: a canonical identifier can never belong to two Companies, and there is no merge.
- **Normalization** (policy in `app.v2.domain.company`; identical SQL twin `v2.normalize_company_identifier`, parity-tested;
  identifiers are stored only in normalized form): domains are lowercased, lose one trailing dot and ONE leading `www.`
  (only while two labels remain); URLs lowercase scheme and host, drop the default port and the fragment, and an empty path
  becomes `/`. http vs https, www in URLs, query strings and path case are NOT collapsed. No DNS, network or AI. Names are
  never normalized into identity (`normalize_name_for_blocking` is a search aid only).
- **Write surface.** Canonical tables are written only by the private `app.v2.resolution._writes`, imported only by
  `app.v2.resolution.promotion` (`create_company_from_candidate`, `attach_candidate_to_company`, `reject_candidate`,
  `defer_candidate`), which the single rule `app.v2.resolution.rules.resolve_by_exact_identifier` also uses. There is no
  generic `create_company`. Reads (`app.v2.repositories.companies`) are unrestricted. Architecture tests fail if any other
  module writes those tables or if `app.v2.ai` / the candidate layer imports the boundary.
- **Atomicity.** create = decision + Company + canonical name + identifiers in one transaction (a SAVEPOINT when the
  caller passes a Connection); attach = decision + newly accepted facts. A conflicting identifier raises
  `IdentifierConflictError` and rolls everything back. Candidates, attempts and evidence are never modified: resolution
  state is derived from decision history.
- **Downgrade** removes only these objects and **refuses** to run while any company, decision, name or identifier exists.

### Revision 0008: `v2.financing_event_candidate` (+ `_amount`, `_date`) (untrusted Capital proposals)

```
Observation -> ProcessingAttempt -> FinancingEventCandidate [UNTRUSTED] -> (future) validation/resolution -> canonical FinancingEvent [not built]
```

A **FinancingEventCandidate is a proposal** about what evidence appears to say concerning a startup financing. It is not a
verified financing, a "venture round", a funding amount or a metric, and **nothing can promote one**: there is no canonical
`financing_event` table, no promotion/resolution function, and no collector, metric, signal or Market Pulse code. Tables carry
comments saying UNTRUSTED. It concerns exactly one canonical Company (real FK to `v2.company`; never a name/domain/URL: a candidate
about an unknown company must wait for company resolution) and belongs to exactly one ProcessingAttempt (nothing about the
Observation or Source is duplicated). Persisting a candidate requires the attempt to be PROCESSING and never modifies the attempt,
the Company or any evidence.

- **Schema.** `financing_event_candidate`: `(processing_attempt_id, candidate_ordinal)` identity, `company_id`, mandatory
  **event-level evidence** (a bare "$5 million" with no financing evidence cannot be stored), `stage`, `financing_type`
  (each `unknown` by default, with its own evidence columns that exist iff the value is not `unknown`), database `created_at`, no
  `updated_at`. `financing_event_candidate_amount`: at most one row per **semantics**. `financing_event_candidate_date`: at most one
  row per **date kind**. (Two small typed child tables, deliberately not a generic fact/EAV system.)
- **Amounts** keep three different meanings and never collapse: `offering_amount` (Form D "total offering amount": what may be
  offered), `amount_sold` (Form D "total amount sold": what HAS been sold), `announced_round_amount` (an announcement's stated round).
  There is no `verified_round_amount`, no generic `amount`, no `funding_amount`; verification belongs to a later layer. Money is exact:
  `amount_minor_units BIGINT` (cents for USD, whole yen for JPY) with an explicit `currency_code` (CHECK `^[A-Z]{3}$`; the domain
  allows only an explicit ISO-4217 allowlist with each currency's exponent). Never a float, never an assumed USD, no FX. **Currency
  policy:** an amount without an established currency is not proposed at all; an amount with finer precision than the currency's minor
  unit is refused, not rounded.
- **Dates** keep three kinds (`first_sale_date`, `filing_date`, `announcement_date`) and their **precision** (`instant|day|month|year`,
  CHECKed so a year cannot carry a March start). There is no generic event_date, and `observed_time` (when WE saw it) stays on the Observation.
- **Unknown stays unknown.** Stage vocabulary `pre_seed|seed|series_a|series_b|growth|unknown`; financing type
  `equity|convertible|debt|other|unknown`. Absence is `unknown`; a value exists only if its evidence states it, and is never inferred from
  an amount, age, investor or headcount.
- **Evidence** is the byte-exact locator from revision 0006 (half-open byte range + sha256 of exactly those bytes, text-like payloads
  only, no OCR/PDF, no fuzzy matching), reused via `verify_locator`. On top of "the bytes exist" (`app.v2.candidates.financing_evidence`):
  a stage/type must be *stated* in its span (explicit phrase tables), and an amount/date span must contain a digit. This checks
  consistency, **not** arithmetic or classification: "$20 million == 2,000,000,000 minor units" and "this is the first-sale date" are not
  verified here. The database re-verifies attempt state and every span (`v2.evidence_span_matches`).
- **Idempotency.** Identity is `(processing_attempt_id, candidate_ordinal)`. Replaying an identical batch (even with facts listed in a
  different order) returns the stored candidates with `created=False`; a different proposal at that ordinal is a `ConflictError`. The ordinal
  is stable only while proposers are deterministic and **must be reconsidered when a real probabilistic proposer exists.**
- **Atomicity.** Whole batch atomic (Engine: one transaction; Connection: a SAVEPOINT). Conflicting candidates from different observations
  are stored side by side; nothing is merged.
- **Downgrade** removes only these objects and refuses to run while any financing candidate exists.

### Revision 0009: `v2.financing_event` + `v2.financing_resolution_decision` (+ `_stage`, `_type`, `_verified_round_amount`, `_date`) (the financing resolution boundary)

```
FinancingEventCandidate(s) [UNTRUSTED] -> FinancingResolutionDecision [human; rule vocabulary exists, none enabled] -> FinancingEvent [TRUSTED]
```

The central requirement: **multiple candidates from different sources may describe ONE real-world financing.**
A Form D, a company announcement and a news article each produce their own `FinancingEventCandidate`; a human decides
whether they are the same financing (`create_event` once, then `attach_to_event` for the rest) -- nothing is ever
merged, copied or deleted, and each candidate's evidence stays exactly where it was proposed. This is a DELIBERATELY
SEPARATE model from Company resolution (revision 0007): financing-event identity has different semantics (many
candidates -> one event; facts are *selected*, never blindly copied), so it is its own package
(`app.v2.financing_resolution`), not a generalisation.

- **`financing_event`**: a bare anchor -- `id UUID` (database-generated), `company_id` (the ONE canonical Company;
  never a name/domain/URL/candidate id), `created_at`. A **deferred constraint trigger** refuses to commit an event
  without a `create_event` decision, so even direct SQL cannot mint one with no provenance.
- **`financing_resolution_decision`** (append-only): `candidate_id`, `decision_kind` (`create_event` |
  `attach_to_event` | `reject_candidate` | `defer_candidate`), `financing_event_id` (required for create/attach,
  forbidden otherwise), `decided_by_kind` (`rule | human`, CHECKed; there is no third value), `decided_by_id`,
  `reason_code` (required for reject/defer). **Every `rule` decision is refused by the insert trigger, unconditionally**
  -- `FINANCING_RULE_AUTHORITY` (the Python registry) is deliberately empty: financing-event deduplication is harder
  than an exact company identifier, and no rule is safe enough yet. At most one FINAL decision (create/attach/reject)
  per candidate (partial unique index; nothing may follow one); a candidate may only resolve into an event of **its
  own Company** (checked in the trigger); an `attach_to_event` requires the target event to already have a
  `create_event` decision.
- **Canonical facts are separate, append-only, one-row-per-fact(-kind)-per-event tables**: `financing_event_stage`,
  `financing_event_type`, `financing_event_verified_round_amount`, `financing_event_date`. Each names the human
  decision that accepted it and the exact candidate (fact) it came from, and the insert trigger (`v2.financing_fact_
  candidate` + a per-table guard) re-verifies that the decision (a) is human, (b) resolved that exact candidate into
  that exact event, and (c) the accepted value matches the candidate's own row bit-for-bit. A canonical fact is
  **never overwritten**: a second attempt at the same fact kind on the same event hits the unique constraint
  (`FactAlreadyAcceptedError`); conflicting values stay as candidate-level history, not canonical truth. **`verified_
  round_amount`** means only "VentureGPS explicitly accepted this amount as the round amount, under an authoritative
  decision" -- it can come ONLY from a candidate's `announced_round_amount`, and only under HUMAN authority (checked
  in Python; `offering_amount`/`amount_sold` can never become it, and there is no path that would let them).
- **Fact selection**: `FactSelection` (`stage`, `financing_type`, `verified_round_amount`, `dates: tuple[...]`) is a
  small closed set, not a patch language. `create_event`/`attach_to_event` accept **zero facts by default**; nothing
  is copied implicitly. Selecting a fact the resolved candidate never proposed (with evidence) is
  `FactNotAvailableError`.
- **Write surface**: canonical financing tables are written only by the private `app.v2.financing_resolution._writes`,
  imported only by `app.v2.financing_resolution.promotion` (`create_event_from_candidate`, `attach_candidate_to_event`,
  `reject_candidate`, `defer_candidate`). There is no generic `create_financing_event`. Reads
  (`app.v2.repositories.financing_events`) are unrestricted. Architecture tests fail if any other module writes those
  tables or if `app.v2.ai` / the candidate layer imports the boundary.
- **Atomicity**: create = decision + event + selected facts, one transaction (a SAVEPOINT on a Connection); attach =
  decision + selected facts. A failed fact selection rolls back the whole operation.
- **Downgrade** removes only these objects and **refuses** to run while any canonical financing or resolution history
  exists.

### Revision 0010: `v2.taxonomy_version`, `v2.market`, `v2.company_market_classification` (Capital attribution)

```
canonical Company -> versioned Company/Market classification -> canonical FinancingEvent -> Capital metrics (computed, not persisted)
```

The minimum structure needed to answer "how much observable financing activity occurred in VentureGPS Market X
during period Y?" from canonical FinancingEvents. No Capital metric is persisted: `app.v2.repositories.capital_metrics`
queries canonical data and hands it to the pure engine (`app.v2.domain.capital_metrics`) at request time.

- **`v2.taxonomy_version`**: a registered version id (e.g. `venturegps_taxonomy.v1`). Classification always names the
  version it was made under; a methodology change is a NEW version with new rows, never a silent rewrite of an old
  classification.
- **`v2.market`**: a bare taxonomy-node identity -- `id UUID` (database-generated), a unique routing `slug`, and a
  `display_name` (**NOT** identity: two different Markets may share a display name). No description/icon/score/
  summary fields. **Registered directly, like `v2.source`** -- a Market is a taxonomy definition VentureGPS makes,
  not evidence-derived truth about the world, so it is not behind a candidate/resolution boundary and is not in the
  canonical-writer registry. Append-only (no rename operation exists yet; see design decisions).
- **`v2.company_market_classification`**: the explicit, append-only, authoritative fact "under this taxonomy
  version, this Company was classified into this Market with this role, by this authority." `decided_by_kind` is
  CHECKed to `rule | human`; every `rule` decision is refused by the insert trigger, unconditionally -- no
  classification rule is safe/enabled yet (same company/name/sector guess is not sufficient identity). Role is
  `primary` (owns Capital attribution) or `secondary` (discovery/context only; **never** attributes Capital, so the
  same financing can never be double-counted across two Markets). At most one `primary` per (Company, taxonomy
  version) (partial unique index); a Company may hold any number of `secondary` classifications, but never the same
  (Company, Market, taxonomy version) twice. Write surface: the private `app.v2.classification._writes`, reached
  only through `app.v2.classification.service.classify_company`.
- **Attribution is derived, never stored**: there is no `financing_event.market_id`, and never will be --
  `app.v2.repositories.capital_metrics` joins FinancingEvent -> Company -> **primary** classification -> Market at
  query time.
- **Capital metric date policy**: a FinancingEvent's metric date is chosen by precedence -- `announcement_date` (the
  most durable public signal), then `first_sale_date` (legally precise but often absent), then `filing_date`
  (administrative, last resort). `Observation.observed_time` is never used. An event with none of the three has no
  metric date and is excluded from every period-based metric (never fabricated), which is visible in
  `CapitalMetrics.diagnostics`.
- **Capital Deployed** sums only canonical `verified_round_amount` (never `offering_amount`/`amount_sold`/
  `announced_round_amount`), by currency (no FX; currencies are never summed together). **Capital Concentration** is
  `largest / total` verified capital per currency, kept exact (`largest_minor_units`/`total_minor_units`, not a
  rounded ratio); a currency with no verified capital has no entry (never a divide-by-zero). **Stage Distribution**
  is counts only, by canonical accepted `Stage` (including `unknown`); candidate-only stage is never counted.
- **All three tables are append-only** (UPDATE/DELETE/TRUNCATE rejected), `created_at` is the database's clock, FKs
  are `ON DELETE RESTRICT`.
- **Downgrade** removes only these objects and **refuses** to run while any taxonomy version, market or
  classification exists.

### Revision 0011: `v2.source.is_test` + `v2.collection_run` (scheduled collection & review-queue operations)

Two independent, additive changes for Increment 18.5, bundled in one revision because both are small and both
support the same operational goal (a reliable, bounded, observable SEC collection workflow with a clean review
queue).

- **`v2.source.is_test`** (new column, `BOOLEAN NOT NULL DEFAULT false`): marks a Source's evidence as synthetic/
  test rather than real. Defaults false -- every existing row and every ordinarily-`register_source`d row stays
  real, zero code change at any existing call site. The `v2.source_guard()` trigger function is replaced
  (`CREATE OR REPLACE`, same signature) to treat `is_test` as mutable alongside `source_name`/`source_url`/
  `is_active`. The ONLY application code path that ever sets it True is
  `app.v2.repositories.sources.mark_source_as_test(db, source_key, authority)`, gated on a human `Authority`;
  there is no rule authority for it and no HTTP endpoint calls it -- the sole caller is the `mark-source-test`
  CLI command, an explicit administrative procedure. See "Marking a source as test" in
  `docs/v2/RUNBOOK_18_5.md` for how to actually use it, including on an existing database whose synthetic
  evidence predates this revision (never reclassified automatically by the migration itself).
- **`v2.collection_run`**: an operational job-history record for one bounded collection attempt against the
  EXISTING, unmodified collection pipeline (`app.v2.tools.sec_form_d_collector` + `app.v2.tools.cli`). Not
  evidence, not a candidate, not a canonical fact. Mutable while `status='running'` (progress is written as it
  happens); frozen (`UPDATE` and `DELETE` both refused by `v2.collection_run_guard()`) once it reaches any
  terminal status (`succeeded | failed | partial | interrupted`). A partial unique index
  (`uq_collection_run_one_active_per_job`, on `job_name` `WHERE status = 'running'`) is the single-active-run
  lock "no overlapping collection runs" needs -- enforced by Postgres itself, so it holds across process
  crashes and concurrent CLI/API invocations, not just within one Python process's memory. `max_filings` is
  CHECKed to 1-25, matching `app.v2.tools.sec_form_d_collector.MAX_DISCOVERY_RESULTS` exactly (no separate
  bound to drift out of sync). `lease_expires_at` + `app.v2.repositories.collection_runs.recover_interrupted_runs`
  is the crash-recovery mechanism: a run whose lease passed without completing is moved to the terminal
  `interrupted` status, never silently retried and never left "running" forever.
- **Downgrade** removes only these objects and **refuses** to run while any `collection_run` row exists, or
  while any source is marked `is_test`.

### Concurrency

A PostgreSQL session-level advisory lock (`MIGRATION_LOCK_KEY`) is held for the whole
run. It is try-lock plus polling with a timeout (default 30s), so a stuck migrator
produces a clear `MigrationLockError` instead of an indefinite wait.

### Rollback policy

`downgrade` is supported and tested for disposable, dev and test databases. Once V2
contains real evidence, destructive production downgrades are not the recovery
strategy: back up first and prefer forward fixes (expand/contract). No backup
infrastructure exists yet.

## Running the V2 database tests

`python -m pytest` runs the whole V2 suite. Tests marked `db` need a disposable
PostgreSQL database and are **skipped** when `V2_TEST_DATABASE_URL` is unset
(**failed** when `V2_REQUIRE_DB_TESTS=1`, which CI should set).

### The exact safety rule

A database may be used by V2 DB tests only if **all** of these hold
(`app/v2/tests/db/guard.py`, tested in `test_database_guard.py`):

1. `V2_TEST_DATABASE_URL` is set. **There is no fallback** to `DATABASE_URL`,
   `V2_DATABASE_URL` or anything else. V2 tests also remove those two variables
   from the process environment, so nothing they start can inherit a production URL.
2. It is a PostgreSQL URL (`postgresql` / `postgresql+psycopg2`).
3. The database **name** matches `^venturegps_v2_test(_[a-z0-9]+)?$`
   (for example `venturegps_v2_test`, `venturegps_v2_test_w1`).
4. The host is loopback (`localhost`, `127.0.0.1`, `::1`), a unix-socket path, or
   listed exactly in `V2_TEST_DATABASE_ALLOWED_HOSTS` (comma-separated). Loopback
   alone is not enough (rules 3 and 6 still apply), and a remote host needs an
   explicit opt-in.
5. The database name differs from the name in `DATABASE_URL` / `V2_DATABASE_URL`,
   whatever host they use.
6. Before any destructive statement, the **server** attests that it is disposable:
   `current_database()` equals the URL's database and the database comment is
   exactly `VENTUREGPS_V2_DISPOSABLE_TEST_DB`.

An unset URL skips. An unsafe URL **fails loudly** (`REFUSING to run V2 database
tests: ...`); it is never skipped, corrected or retried. Error messages never
contain the URL. Test cleanup only drops schema `v2` and the `legacy_probe_*` /
`public.alembic_version` decoy objects that the tests themselves create.

### Creating a test database

```bash
createdb venturegps_v2_test
psql -d venturegps_v2_test -c "COMMENT ON DATABASE venturegps_v2_test IS 'VENTUREGPS_V2_DISPOSABLE_TEST_DB'"
export V2_TEST_DATABASE_URL='postgresql://localhost/venturegps_v2_test'
V2_REQUIRE_DB_TESTS=1 python -m pytest
```

Use a dedicated database (or a throwaway cluster on another port). Do not reuse a
database that holds anything you care about; the tests drop schema `v2` in it.

### What the DB tests prove

Upgrade base to head (and each revision stepwise), downgrade head to base, upgrade again, idempotent upgrade;
the version table is `v2.alembic_version` and never `public`; a `public.alembic_version`
decoy and representative legacy tables (data, indexes, constraints, sequences, a view)
are byte-for-byte unchanged across upgrade, downgrade and re-upgrade; `alembic check`
sees no legacy drift; the filters (not luck) are what exclude legacy tables; downgrade
refuses to drop a schema holding foreign objects and rolls back completely; the advisory
lock makes a second migrator fail fast, and four concurrent `alembic upgrade head`
processes serialize with exactly one applying the revision.
