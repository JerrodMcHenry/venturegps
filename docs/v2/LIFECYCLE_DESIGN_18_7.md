# Company lifecycle & identity history — design proposal (Increment 18.7)

**Status: proposed, not implemented.** No migration, model, endpoint or UI in this increment. No canonical
decision, no database write, anywhere in producing this document.

---

## Phase 1 — Read-only architecture audit

Real, current state, inspected directly against the repository and `venturegps_v2_dev_1801` (read-only).

### Gecko Robotics' identifier — confirmed live

```
company.id = b19376f7-8549-40db-828b-4444a4176f28
company_name:       "Gecko Robotics, Inc." (canonical, decision #1, candidate #1)
company_identifier: website_url "https://www.geckorobotics.com/" (decision #16, candidate #39)
resolution_decision #16: attach_to_company, human, decided_by_id = admin:user_3JjzlWNUJr2mVPI5a5r0Zgv2D3B
```

This is a **real human decision**, made through the review interface by your own authenticated session
(`admin:user_3Jjz...` is your Clerk `sub`, not a test fixture identity) — candidate #39 from Increment 18.6c
is genuinely attached. Confirmed unaffected by anything since.

### Existing support, by area

| Area | Current state |
|---|---|
| Canonical vs. historical names | `company_name` (append-only): `name_role ∈ {canonical, alias}` only. **`canonical` means "the name accepted when the company was created," permanently** — there is no operation anywhere that changes it after `create_company_from_candidate`. `alias` is added only by a human `attach` decision. **No concept of "this name was later replaced."** |
| Company identifiers / conflicts | `company_identifier`, `IdentifierConflictError` (an identifier already owned by a different company is refused, never merged). Solid, reusable as-is — no change needed here. |
| Acquisition / ownership relationships | **None exist.** No table, no domain type, no decision kind. Grepped the full `app/v2` tree for `acquisition`, `acquired`, `successor`, `lifecycle`, `renam*` — zero matches outside this design doc. |
| Operating status | **None exists.** `company_table` (`app/v2/db/tables.py`) is exactly `id` + `created_at` — "an opaque id and a database-owned creation time, nothing else" (its own docstring). No status field anywhere. |
| Company creation and attachment | `app.v2.resolution.promotion` (`create_company_from_candidate`, `attach_candidate_to_company`, `reject_candidate`, `defer_candidate`) — the only writer of canonical company tables, reached only through `app.v2.resolution.human_review` (CLI/legacy) or `app.v2.resolution.rules` (no rule currently registered). This is the pattern every new lifecycle write should reuse, not replace. |
| Immutable evidence and audit history | Every canonical/candidate/decision table except `source` and `collection_run` (while running) is database-trigger enforced append-only (`BEFORE UPDATE`/`BEFORE DELETE` raise). `LineageLink` already traces any accepted fact back through its decision → candidate → attempt → observation → payload → source. This is the exact trail a lifecycle fact needs too. |
| Review API / admin UI | `app/v2_review_api.py` (legacy-side, `RequireAdmin`-gated) + `dashboard/app/admin/v2-review/V2ReviewView.tsx`. Company/financing candidate review already has the queue/filter/evidence/decide shape a lifecycle candidate would need to mirror. |
| Public company/market API contracts | `app/v2/api.py` currently exposes **only markets and their Capital metrics/signal** (`GET /markets`, `/markets/{id}`, `.../capital/metrics`, `.../capital/signal`). **There is no public company endpoint of any kind today.** This materially simplifies Phase 4/5: there is no existing public contract to break, only a future one to design carefully. |

### Migrations and boundary rules

10 legacy-namespace migrations (0001–0010) + 0011 (Increment 18.5: `source.is_test`, `collection_run`). A
lifecycle migration would be **0012**, additive only, in the same `app/v2/migrations/versions/` sequence.

`app/v2/tests/architecture/boundary_rules.py` (unchanged by this proposal) already has the exact shape a new
canonical-writer package needs to fit:
- `canonical_writer_modules` — the only modules ever writing canonical tables (private `_writes.py` per
  domain: `resolution`, `financing_resolution`, `classification`). A `lifecycle` package would add its own
  private `app.v2.lifecycle._writes`, following this closed pattern exactly.
- `canonical_writer_importers` — the only modules allowed to import that private writer (`promotion.py` per
  domain). A `lifecycle` package's own `promotion.py` would be the fourth.
- `no_network_packages` already includes `app.v2.repositories` and `app.v2.resolution` as prefixes — a new
  `app.v2.lifecycle` package should be added to this list explicitly (no network access, same as every other
  resolution boundary).
- `canonical_table_variables`/`canonical_table_names` — would gain the new lifecycle tables (Phase 4).

Nothing here requires changing `boundary_rules.py`'s *shape*, only extending its lists — exactly the kind of
change Increment 18.2.1's own precedent ("the smallest defensible fix," a two-module closed set) already
established as acceptable.

---

## Phase 2 — Minimal domain design

**One shared candidate/decision boundary, four narrow typed facts** — mirroring how `FinancingEventCandidateProposal`
already carries multiple optional typed sub-facts (`stage`, `financing_type`, `amounts`, `dates`) under one
candidate, with a human `FactSelection` choosing which to accept. This is deliberately **not** a generic
`CompanyEvent(event_type, payload_json)` table (explicitly ruled out) — each fact type below is its own typed
Pydantic model and its own narrow database table, exactly like financing's `financing_event_stage`/`_type`/
`_verified_round_amount`/`_date`.

### A. Legal name history

A **new, separate** table (`company_name_history`), not a change to `company_name`. `company_name`'s existing
`canonical` row for Gecko ("Gecko Robotics, Inc.") stays **exactly as recorded, forever** — nothing rewrites
it. A rename is a *new, dated, evidenced fact layered on top*:

```
company_id, former_name, new_name, effective (EventTime, precision-aware — "September 2024" is legitimate,
  not forced to a specific day), lifecycle_decision_id, candidate_id, created_at
```

"Current legal name" becomes a **derived read**: the most recent `company_name_history.new_name` for that
company, or the original `company_name` `canonical` row if no rename has been accepted. No existing reader of
`company_name` needs to change; a new `get_current_legal_name(company_id)` helper is additive.

### B. Acquisition

A **relationship fact between two distinct legal entities**, never a merge:

```
company_id (the acquired company — must already be canonical),
acquirer_company_id (nullable UUID — set ONLY if the acquirer is itself already a canonical VentureGPS
  company; e.g. Siemens Healthineers would need to exist as its own canonical company first),
acquirer_name (text, always present — the evidenced name, independent of whether it resolves to a company_id),
transaction_date (EventTime, nullable — a documented date may be unavailable),
lifecycle_decision_id, candidate_id, created_at
```

**Acquisition never implies dissolution or a legal merger by itself** — accepting an acquisition fact does
*not* automatically write an operating-status fact (C). A reviewer who has *both* pieces of evidence (an
acquisition announcement *and* independent confirmation of ceased independent operation) accepts both
separately, each under its own evidence. This directly satisfies "Acquisition must not imply a legal merger or
dissolution without evidence."

### C. Operating status

```
company_id, status ∈ {active, acquired, ceased_operations, unknown}, as_of (EventTime, nullable — some
  evidence states a status with no date), lifecycle_decision_id, candidate_id, created_at
```

`unknown` is a **legitimate, explicit accepted value** — not the absence of a row. (Absence of any status row
at all is the *true* unset state; a company with no accepted status fact is simply undescribed, which is
different from someone having evidenced "we could not determine current status.") **Current status** is the
most recent `as_of`-ordered row (ties broken by `created_at`) — append-only, so a status can be *updated* by
adding a newer row, never by rewriting an old one. A correction (evidence turns out to be wrong) is handled
the same way: a new row with a later `created_at`, with its own reason — see Phase 3's "corrections" section;
**the old, now-superseded row is never deleted**.

### D. Successor relationships

The most deliberately conservative of the four, per your explicit instruction:

```
company_id, related_company_id (nullable UUID — set only if the related entity is already canonical),
related_entity_name (text, always present), relationship_kind ∈ {possible_successor, confirmed_successor},
lifecycle_decision_id, candidate_id, created_at
```

Accepting a successor fact **never** copies, aliases, or transfers identifiers, financing history, or
classifications between the two `company_id`s — it is purely an annotation: "a human reviewed evidence and
recorded that these two entities may be/are related." The 3D Robotics / 3DR case (brand continuity, explicit
**first-party** disclaimer of legal continuity) is the canonical example this exists for: VentureGPS should be
able to say "these are related" without ever conflating their canonical identities, evidence, or metrics.
`possible_successor` vs. `confirmed_successor` gives a reviewer room to record a documented-but-uncertain
relationship (e.g., same founder, similar branding, no first-party statement either way) distinctly from a
company's own explicit statement (as 3DR's site itself provides for the *negative* case — "we are not the
same entity" is evidence for **not** recording a successor relationship at all, or recording `possible` with
that very disclaimer as the cited evidence and a clear negative gloss — a genuinely edge-of-scope case worth
flagging for your decision in Phase 6).

**Explicitly not built**: no generic "relationship type" enum meant to cover future cases (spin-offs, mergers
of equals, rebrand-without-acquisition, etc.) — those are different facts with different evidence shapes and
should each get their own narrow addition when a real case actually needs one, not a speculative generic slot
now.

---

## Phase 3 — Evidence and human authority

**Reuses, unchanged**: source registration, `ingest`, `EvidenceLocator`/byte-exact verification
(`app.v2.candidates.evidence`-style — a **new**, small `app.v2.lifecycle.evidence.verify_lifecycle_proposal`
following the exact structure of `verify_financing_proposal`, not a rewrite of the mechanism itself), the
`processing_attempt` lifecycle (start/mark_processed/mark_failed), `Authority`/`human_authority` (human-only —
**no rule authority registered for lifecycle decisions, ever, at launch**, mirroring financing's own
`FINANCING_RULE_AUTHORITY = {}` stance: lifecycle identity claims are exactly the kind of judgment call 18.2.1
already decided rules aren't safe for).

### Lifecycle candidate → decision, concretely

```
LifecycleEventCandidateProposal:
  company_id: UUID                       # the EXISTING canonical company this evidence is about
  event_evidence: EvidenceLocator        # proves *something* lifecycle-relevant is being discussed
  name_change: ProposedNameChange | None
  operating_status: ProposedOperatingStatus | None
  acquisition: ProposedAcquisition | None
  successor: ProposedSuccessorRelationship | None
  # at least one of the four must be present -- an empty candidate is meaningless, refused at construction
```

Persisted through a new `store_lifecycle_candidates` (mirrors `persist_financing_event_candidates` exactly:
verify every proposal's evidence against the immutable payload before writing any, atomic batch, identity =
`(processing_attempt_id, candidate_ordinal)`, `on_conflict_do_nothing` replay-idempotent).

**Decision**: a `LifecycleFactSelection(name_change: bool, operating_status: bool, acquisition: bool,
successor: bool)` — exactly `FactSelection`'s shape — lets a human accept *some* of a candidate's proposed
facts and not others (e.g., accept the acquisition, defer the status question). No create/attach split is
needed here (unlike financing) — a lifecycle fact annotates an *already-canonical* company directly; there is
no new entity being created. Decision kinds: `accept_lifecycle_event` (with a `FactSelection`),
`reject_candidate`, `defer_candidate` — accept is final only insofar as *that candidate* is resolved; it does
**not** prevent a *later, independently evidenced* candidate from adding a newer fact (a second acquisition
announcement, a later status correction) — see below.

### Duplicate / conflicting event handling

- **Duplicate candidate** (same observation, same fact type re-submitted): handled exactly like Increment
  18.6c's `add-identity-candidate` — reported, not re-created, via the same "already processed for this
  observation" check.
- **Conflicting facts** (two *different* observations propose different things — e.g., one says "acquired by
  Siemens," another says "still independent"): **both candidates persist independently** (evidence is never
  discarded); a human decides which (if either) to accept. Accepting one does not retroactively invalidate the
  other candidate's *evidence* — it remains in the system, inspectable, just not accepted.
- **Corrections / superseding evidence**: append a **new** accepted fact with a later `created_at` (and,
  ideally, a `reason_code` explaining the correction, reusing `validate_reason_code`). The old fact is never
  deleted or rewritten — "current" is always a derived read (latest by date), so a correction is just a new,
  more-recent row. This is the same posture Increment 18.5's `collection_run` already uses for job history
  (append rows, derive "current," never mutate).

### What stays append-only, unchanged

Every new table is append-only from the start (mirrors every other canonical/decision table): a
`trg_*_guard` `BEFORE UPDATE` refusal, `BEFORE DELETE` refusal, matching `financing_resolution_decision`'s own
pattern exactly.

### Historical SEC filings keep their filed name

**No change needed anywhere.** `company_candidate.proposed_name` is already immutable, per-candidate, never
rewritten — ReWalk's 2019–2021 Form D candidates already, permanently, say "ReWalk Robotics Ltd." (or whatever
the filing itself said), regardless of any later rename fact accepted on the canonical company. This is a
consequence of the existing architecture, not something Increment 18.7 has to build.

---

## Phase 4 — Data model and migration plan (proposed, not created)

One new migration, **0012**, purely additive (new tables + one new `company` read helper function, no
`ALTER` on any existing table, no existing primary key touched).

| Object | Why necessary | Why existing structures can't already represent it |
|---|---|---|
| `v2.lifecycle_event_candidate` (+ 4 typed fact tables: `_name_change`, `_operating_status`, `_acquisition`, `_successor`) | The untrusted-proposal layer for lifecycle facts | `company_candidate` only ever proposes a *new* company's identity (name+identifiers); it has no concept of an event *about* an already-canonical company |
| `v2.lifecycle_resolution_decision` | The human accept/reject/defer boundary, mirroring `financing_resolution_decision` | `resolution_decision` is scoped to *creating/attaching* a company from a candidate — it has no `accept_lifecycle_event` concept and adding one would blur "company came into existence" with "a fact about an existing company," two different things |
| `v2.company_name_history` | Derivable "current legal name" without ever touching `company_name` | `company_name`'s `canonical` role is defined, today, as permanent and singular; overloading it would be a breaking semantic change to existing rows, forbidden by your "do not rewrite historical records" instruction |
| `v2.company_operating_status` | Dated, evidenced, append-only status history | No status concept exists at all today (`company_table` is `id` + `created_at` only) |
| `v2.company_acquisition` | A typed relationship between two distinct `company_id`s (one nullable) | No relationship concept between companies exists at all today |
| `v2.company_successor_relationship` | Same as acquisition, deliberately weaker semantics (`possible`/`confirmed`, never implies transfer) | Same — nothing today distinguishes "these might be related" from any other fact |

**Constraints and uniqueness** (sketched, not final DDL): `lifecycle_event_candidate` gets the same
`(processing_attempt_id, candidate_ordinal)` unique identity every candidate table already has. Each fact
table's row is `FOREIGN KEY (lifecycle_decision_id) REFERENCES lifecycle_resolution_decision(id) ON DELETE
RESTRICT` and `FOREIGN KEY (company_id) REFERENCES company(id) ON DELETE RESTRICT`, matching every existing
canonical fact table. **No uniqueness constraint forces "only one accepted status/name/acquisition ever"** —
by design, since a correction is a new row, not a replacement (Phase 3). `lifecycle_resolution_decision` gets
the same `uq_..._one_final` **per lifecycle candidate** partial-unique pattern `resolution_decision` already
uses, so a given lifecycle candidate can't be decided twice.

**Evidence and decision references**: every fact table carries both `lifecycle_decision_id` (who decided,
when, under what authority) and `candidate_id` (which evidence supported it) — the exact two-hop provenance
`LineageLink` already threads for names/identifiers; a `LifecycleLineageLink` would be the natural read-side
addition, same shape.

**Migration and rollback safety**: additive-only forward migration (new tables, `CREATE FUNCTION`/`CREATE
TRIGGER` for the append-only guards, matching 0011's own structure exactly). Downgrade refuses while any
lifecycle history exists, matching every prior migration's `REFUSE_IF_HISTORY_EXISTS` pattern.

**Impact on existing canonical companies**: **zero** for any company with no lifecycle facts accepted — every
existing read (`get_company`, `list_company_names`, `list_company_identifiers`, `get_company_lineage`) is
completely unchanged; Gecko Robotics' current state is unaffected unless someone later, explicitly, proposes
and accepts a lifecycle fact about it.

**Impact on public API contracts**: **none today** (Phase 1 finding — no public company endpoint exists yet).
Whenever one is built, it should read current name/status/acquisition through the same "latest wins, evidence
attached" derivation this design already specifies, from day one — not retrofitted later.

---

## Phase 5 — Review and public presentation

### Admin review UI (minimal addition, mirrors the existing candidate panels exactly)

A **third candidate type** in the existing review shape (`CompanyCandidatePanel`/`FinancingCandidatePanel` →
add `LifecycleCandidatePanel`), not a new page or a new interaction paradigm. A reviewer sees, per candidate:
- The proposed fact(s) (which of name/status/acquisition/successor this candidate carries), each with its own
  evidence excerpt + provenance (source, accession/URL, retrieval time) — identical `Evidence` component
  already built for company/financing candidates.
- **Existing company matches**: the `company_id` the candidate is about (always known, since lifecycle facts
  are about an already-canonical company) plus, for acquisition/successor, whether `acquirer_company_id`/
  `related_company_id` resolves to an existing canonical company (shown plainly; never auto-linked if absent).
- **Conflicts and uncertainty**: if another *pending or accepted* lifecycle candidate already proposes a
  different value for the same fact type on the same company, show both side by side — never auto-resolved.
- **Consequences of approval**: a plain-language preview ("Accepting this will record Gecko Robotics'
  operating status as `active`, effective evidence dated 2026-…") before the same explicit
  confirm-checkbox pattern every other decide action already uses.

### Public presentation (described, not built)

A future public company profile should show: the **current** legal name with **former name(s) and their
effective dates** listed beneath it (never silently replacing the history); an **operating-status badge**
(`active`/`acquired`/`ceased operations`) with its evidence date; for `acquired`, the **acquirer**, linked
only if it is itself a published canonical company, otherwise shown as evidenced text; **successor
relationships** shown as a distinct, clearly-labeled section ("possibly related to…" / "successor of…"),
**never** as if the two were the same entity, and never merging their financing history, classification, or
Capital Signal contribution — 3D Robotics (2012–2016) and any later 3DR entity would always be two separate
profiles, cross-referenced, never one.

---

## Phase 6 — Case validation

| Case | What's already evidenced in V2 | What still needs ingesting | Records/decisions this design would need |
|---|---|---|---|
| **1. ReWalk → Lifeward** | 4 Form D candidates (#31–#33, #37), same CIK 1607962, each still correctly saying "ReWalk Robotics Ltd." — unaffected by anything below. **No canonical company created yet.** | The GlobeNewswire rename release (18.6b) and SEC's own former-names record are *research*, not yet ingested as evidence in V2. | (a) Resolve identity first — `create`/`attach` the 4 candidates into one canonical company (existing mechanism, no lifecycle involvement). (b) Ingest the rename announcement as a `first_party_company` or `media_news` source. (c) One `lifecycle_event_candidate` proposing `name_change` (ReWalk Robotics Ltd. → Lifeward Ltd., effective 2024-09-13, cited to the announcement). (d) Human `accept_lifecycle_event`. |
| **2. Corindus** | 4 Form D candidates (#30, #34, #35, #38), CIK 1528557, correctly all "Corindus Vascular Robotics, Inc." **No canonical company created yet.** | The Siemens Healthineers press releases (18.6b) are research, not ingested. Siemens Healthineers itself does not exist as a canonical V2 company. | (a) Resolve Corindus identity (create/attach the 4 candidates). (b) Ingest the acquisition press release. (c) A `lifecycle_event_candidate` proposing `acquisition` (`acquirer_name="Siemens Healthineers AG"`, `acquirer_company_id=None` unless/until Siemens Healthineers is separately onboarded as its own canonical company, `transaction_date≈2019-10-29`). (d) Separately, if independently evidenced, an `operating_status` proposal (`acquired`) — **not automatically implied** by accepting the acquisition fact, per Phase 2. (e) Human decisions for each. |
| **3. Historical 3D Robotics vs. 3DR** | 1 Form D candidate (#36), CIK 1561997, "3D Robotics, Inc." **No canonical company created yet.** | The 3dr.com disclaimer text (18.6b) is research, not ingested; the 2024-era "3DR Inc." entity has no CIK identified yet and does not exist as a candidate or company in V2 at all. | (a) Resolve historical 3D Robotics identity (create from #36). (b) **Do not** create a "3DR Inc." company from name similarity alone — it would need its own, separately sourced identity evidence first (its own Form D or first-party page, its own CIK if it has one). (c) Once (if) both exist as canonical companies, a `successor_relationship` candidate citing the 3dr.com disclaimer — and given that disclaimer's own wording, the *evidenced, correct* fact to accept may be closer to "explicitly NOT a continuation" than `possible_successor`; **flagging this for your decision**, not resolving it here (see Open Decisions below). |
| **4. Gecko Robotics** | Canonical company exists, one verified financing event ($125M), one verified `website_url` identifier (real, your own decision, confirmed in Phase 1). | Nothing lifecycle-related has been researched or claimed about Gecko — it has not been renamed, acquired, or linked to any successor. | **None.** This design adds new tables and new candidate types; it changes no existing read path for a company with zero lifecycle facts. Gecko remains exactly as it is unless someone later proposes and a human accepts a lifecycle fact about it specifically. |

---

## Phase 7 — Test strategy

All against an **explicitly attested disposable** V2 test database only (`venturegps_v2_test_*`, the same
`guard.py` fail-closed mechanism every prior increment's DB tests already use) — never `venturegps_v2_dev_1801`
for anything destructive.

| Scenario | What it proves |
|---|---|
| Same-entity rename accepted | `name_change` fact recorded; original `company_name` `canonical` row provably unchanged; "current legal name" read returns the new name |
| Distinct-entity acquisition accepted | `acquisition` fact recorded on the acquired company only; no new `company_name`/`company_identifier` row is created on either company; accepting it does **not** also write an `operating_status` row |
| Unconfirmed successor relationship | `possible_successor` accepted; confirms no identifier/financing/classification data moved between the two `company_id`s |
| Conflicting identifiers | Reuses the **existing, unmodified** `IdentifierConflictError` path — a lifecycle-driven identifier claim (if this design is later extended to propose identifiers, which it does not today) would hit the same check; for 18.7 specifically, prove a lifecycle candidate never bypasses it because lifecycle facts don't touch `company_identifier` at all |
| Duplicate lifecycle candidates | Same-observation resubmission reported as duplicate, not re-created (18.6c's own pattern) |
| Missing or ambiguous evidence | `FactNotFoundError`/occurrence-out-of-range refused before persistence, exactly like every other manual-evidence command |
| Unauthorized approvals | Unauthenticated → 401; authenticated non-admin → 403; identical to every existing review endpoint — no new auth mechanism, so this is a regression check, not new logic |
| Append-only audit history | `UPDATE`/`DELETE` on any new table refused by its own guard trigger, proven directly against the database (mirrors this session's own migration-0011 trigger tests) |
| Preservation of historical financing | Accepting any lifecycle fact on a company leaves its existing `financing_event`/accepted facts byte-for-byte unchanged |
| Unchanged Capital Signal behavior | Full existing Capital Signal test suite re-run with zero modification to `app.v2.domain.capital_signal`/`capital_metrics` — this design touches neither module; a lifecycle status of `acquired` does **not**, by itself, remove a company from Capital metrics (a separate, **not** decided, product question flagged below) |
| Existing Gecko Robotics regression | `get_company`, `list_company_names`, `list_company_identifiers`, `get_company_lineage` for Gecko's real `company_id` return byte-identical results before and after this feature exists, with zero lifecycle facts accepted about it |

---

## Open decisions requiring your approval before implementation

1. **Table shape**: one shared `lifecycle_event_candidate` + 4 typed fact tables (as designed above), vs. four
   fully separate candidate/decision boundaries. I recommend the shared version (mirrors financing's own
   internal structure) — smaller, but means one candidate can carry multiple fact types at once, which is a
   real modeling choice you should confirm you want.
2. **Does `acquired` status remove a company from Capital Signal/Capital Metrics?** Not decided or implied by
   this design. If yes, that's a **methodology-adjacent** decision (Capital Signal is explicitly off-limits to
   change without your separate sign-off) that would need its own careful review — my default recommendation
   is **no automatic effect**: an acquired company's *historical* financing remains real historical financing;
   whether current-period aggregate metrics should exclude it is a product question, not an evidence question.
3. **3D Robotics vs. 3DR**: given the 3dr.com disclaimer's own wording, should the evidenced fact even be a
   `successor_relationship` at all, or does a genuine "explicitly not the same entity" case need its own third
   `relationship_kind` (e.g. `explicitly_distinct`) rather than being shoehorned into `possible_successor`? I
   lean toward adding that third value now, while the real case is in front of us, rather than later — your
   call.
4. **Acquirer/successor as free text vs. requiring onboarding first**: this design allows recording an
   acquirer/successor by name alone, with a nullable `company_id` link only when that entity is *already*
   canonical in VentureGPS (Siemens Healthineers is not, today). Confirm this is the right default rather than
   requiring the acquirer to be onboarded first.
5. **Public presentation** (Phase 5) is described only — confirm the general shape (former names listed,
   status badge, acquirer linked only if published, successors never merged) before any future increment
   builds it.

---

Nothing was implemented. No migration file, model, endpoint, or UI change exists from this increment. No
canonical decision was made and no existing record (including Gecko's real, already-attached identifier) was
touched in producing this document. Not deployed, committed, or pushed.
