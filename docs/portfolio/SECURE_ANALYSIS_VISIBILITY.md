# Secure Analysis Visibility

**Added:** Portfolio Release Task 3B, following Task 3A's read-only audit (`docs/portfolio/VENTUREGPS_READINESS_AUDIT.md`
and the Task 3A audit report — quoted evidence from an uploaded pitch deck could end up served, verbatim, by the
fully unauthenticated `GET /startup/{company_name}` endpoint).

**Corrected:** a final pre-commit security review found that Task 3B's first implementation still let an
approved startup member automatically read a *different* member's privately-submitted analysis of the same
startup — membership was a flat grant, not scoped to the submitter. This document describes the corrected,
two-tier policy actually enforced today; see "The correction" below for what changed and why.

## The decision

User-submitted analyses are **private by default**. No public/private toggle exists or was added — visibility is
computed deterministically from who submitted an analysis and who is an approved member of the associated startup,
never from a manually-set flag.

## The migration

One new, nullable, additive column, added via the same `add_*_columns()` pattern every other migration in this
codebase uses:

```sql
ALTER TABLE analyses ADD COLUMN submitted_by_user_id TEXT REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX analyses_submitted_by_user_id_idx ON analyses (submitted_by_user_id);
```

`app/database/db.py::add_analysis_submitted_by_column()`, called in `app/api.py`'s migration sequence immediately
after `create_users_table()` (its FK target). **Never backfilled** — every row that existed before this migration
has, and will always have, `submitted_by_user_id = NULL`. `POST /analyze` now passes `current_user.user_id` into
`save_analysis(..., submitted_by_user_id=...)` for every analysis it creates.

## The authorization rule

`app/database/db.py::_analysis_visibility_clause()` — one SQL boolean fragment, reused by every read path:

```sql
(
    :viewer_is_admin
    OR submitted_by_user_id = :viewer_user_id
    OR (
        submitted_by_user_id IS NULL
        AND startup_id IN (SELECT startup_id FROM startup_memberships WHERE user_id = :viewer_user_id)
    )
)
```

Two tiers, not a flat three-way grant:

1. **A new analysis** (`submitted_by_user_id` is a real Clerk user id) is visible only to **its submitter** or an
   **admin** (`app/auth.py::is_admin()`). Being an approved member of the same startup (`startup_memberships`) is
   **not** enough on its own — that was the bug this correction fixes (see "The correction" below).
2. **A historical analysis** (`submitted_by_user_id IS NULL` — every row that existed before this migration,
   forever, never backfilled) has no submitter to match, so membership is the only thing that can substitute:
   visible to an **approved member** of the associated startup or an **admin**. This preserves the pre-migration
   founder-access behavior exactly for rows that predate the concept of a submitter.

Saved startups, watchlists, and a matching company name are never a branch of this clause and never grant access
on their own — see "What changed, and where" below for the two surfaces (`/me/saved-startups`,
`/investor/workspace`) that had to be fixed to actually honor that.

Applied **inside** each query's `WHERE` clause, before any `ROW_NUMBER()`/`DISTINCT ON` "pick the latest" logic —
never as a post-fetch filter — so "the latest analysis" always means "the latest analysis this viewer is
authorized to see."

## The correction

A focused final security review, run before committing Task 3B, found that the rule above (in its first
implementation) let branch 2 apply **unconditionally** — to every row, not only `NULL`-owner ones:

```sql
-- Previous (incorrect) shape of branch 2 -- no submitted_by_user_id IS NULL guard:
OR startup_id IN (SELECT startup_id FROM startup_memberships WHERE user_id = :viewer_user_id)
```

Concretely: if Founder A and Founder B are both approved members of the same startup, and Founder A submits a
new analysis (`submitted_by_user_id = A`), Founder B — an approved member, but not the submitter — could still
read it in full, everywhere `_analysis_visibility_clause()` is used. That is a real cross-user confidentiality
gap: two co-founders of the same startup are not automatically entitled to see each other's private analysis
submissions. The fix adds the `submitted_by_user_id IS NULL` guard shown above, so membership only ever
substitutes for a *missing* submitter, never overrides a *real, different* one.

**A second instance of the identical bug was found and fixed in the same review**, in a code path that doesn't
use `_analysis_visibility_clause()` at all: `app/database/db.py::get_founder_startup_workspace()` (Founder
Workspace, `GET /founder/startups/{startup_id}`, gated by `RequireStartupMember`) picked the latest analysis for
a `startup_id` with no reference to `submitted_by_user_id` whatsoever — so an approved member could read another
member's private analysis of the same startup there too, both the current methodology and the SPS history. Fixed
the same way, inlined rather than via the shared clause (membership is already an established precondition of
reaching this function, so there's no need to re-derive it with a `startup_memberships` subquery):
`submitted_by_user_id = :user_id OR submitted_by_user_id IS NULL`. Dedicated regression coverage:
`test_approved_member_cannot_read_another_members_private_analysis`,
`test_submitting_founder_still_sees_their_own_report_via_workspace`,
`test_approved_member_still_sees_historical_null_owner_analysis` in `app/tests/test_founder_workspace.py`.

The submitting user's own access is unaffected by either fix — `submitted_by_user_id = :viewer_user_id` (or
`= :user_id` in Founder Workspace) always matches their own row, regardless of who else is an approved member.

## What changed, and where

| Layer | Change |
|---|---|
| `GET /startup/{company_name}` | Was fully public. Now `RequireAuth` + the visibility rule. An unauthorized-but-signed-in caller gets the same `has_analysis: false` shape a genuinely-unanalyzed company gets — see "Known, accepted residual disclosure" below — never a distinguishing 403/leak. |
| `GET /startup/{company_name}/sps-history` | Same treatment. |
| `GET /analyses/search`, `/rankings`, `/discover`, `/discover/filter-options`, `/compare` | Were fully public. Now `RequireAuth`, scoped to the caller's own authorized analyses (approved decision — **no public scores-only exception**). `/compare`'s explicit `startup_id`s resolve to nothing if the caller isn't authorized for them — never a leak via a guessed/known ID. |
| `GET /score-history/{name}`, `/startup-trends/{name}`, `/top-startups`, `/top-improving-startups`, `/analytics` | Same scoping. `score_history` (legacy, dead-write-path) has no `startup_id`/owner of its own — scoped via a `JOIN` to `analyses` on `analysis_id`. |
| `GET /me/saved-startups` | **Second, more severe instance of the same gap**, found during this task's own audit (not in the original Task 3A report): `get_saved_startups_for_user()`'s `LEFT JOIN LATERAL` had no visibility filter at all — any bookmarked startup's score/industry/stage leaked regardless of who submitted it. Fixed the same way. |
| `GET /investor/workspace` | **Third instance, the most severe** — `get_watchlist_startups_for_user()` returned the **full methodology JSONB** (not just a score) for any watched startup, no filter. Fixed the same way; dedicated regression test added (`test_watching_without_authorization_shows_no_intelligence`, `app/tests/test_investor_workspace.py`). |
| `/analyses`, `/analyses/{id}`, `/analyses/{id}/pdf` | Unchanged — already `RequireAdmin`-gated, already correct. |
| `/ventures/share/{public_id}` (Idea Lab) | Audited, confirmed unrelated — a separate subsystem with its own explicit, user-initiated share toggle, no path into `analyses`. |
| `GET /founder/startups/{startup_id}` (+ `/fundraising`) | **Fourth instance, found during this correction's own review** — already `RequireStartupMember`-gated (never public), but `get_founder_startup_workspace()` picked the latest analysis for a startup with no `submitted_by_user_id` check at all, so one approved member could read another's private analysis. Fixed with an inline `submitted_by_user_id = :user_id OR submitted_by_user_id IS NULL` filter — see "The correction" above. |

Frontend: `dashboard/app/startup/[id]/page.tsx`, `app/rankings/page.tsx`, `app/search/page.tsx`,
`app/compare/page.tsx` all now call `auth.protect()`. `/startup/[id]` stays a Server Component (Clerk's server-side
`auth().getToken()`); `/rankings`/`/search`/`/compare` use the same client-side `useAuth().getToken()` pattern
`AnalyzeStartupForm.tsx` already established, since their existing interactive loading/error state genuinely needs
to run client-side. `AnalyzeStartupForm.tsx` now discloses "Private by default" near submission. `proxy.ts`'s
route matcher (a UX-only optimizer, never the real boundary) extended to match.

## Company-name collisions

Two users analyzing a company with the same name already coexisted as separate `analyses` rows sharing one
`startup_id` (`get_or_create_startup()`) — unchanged. What changed: every "pick the latest" query now applies the
visibility filter **before** picking latest, so each user sees their own latest **authorized** analysis, never a
stranger's newer, inaccessible one silently taking priority. Verified directly:
`test_company_name_collision_each_user_sees_only_their_own`,
`test_company_name_collision_db_layer_authorization_before_latest_pick`.

## Known, accepted residual disclosure

`GET /startup/{company_name}` for an unauthorized-but-signed-in caller returns `200` with `has_analysis: false`,
**not** a bare `404` matching a genuinely nonexistent company. This is the pre-existing Phase 37E fallback (honest
"exists, not yet analyzed" vs. "doesn't exist at all") correctly still finding the real `startups` row — it
confirms a canonical record for this company **name** exists (not confidential — the caller already knows the
name, since they searched for it) while disclosing **zero** analysis content. A genuinely nonexistent company (no
`startups` row) still gets a real `404`. Accepted as low-severity; not changed in this task.

## Tests

`app/tests/test_analysis_visibility.py` (14 tests) is the authoritative, dedicated coverage for the rule itself:
anonymous/owner/unrelated-user/admin access, historical `NULL`-owner records (including that they are never
deleted or rewritten), company-name collisions (HTTP and DB layer), and indirect disclosure through
search/rankings/compare. Its approved-member coverage now asserts the **corrected** behavior —
`test_approved_member_cannot_access_analysis_they_did_not_submit` (an approved member gets the same non-leaking
`has_analysis: false` shape an unrelated caller gets for another member's private analysis) and
`test_submitter_can_still_access_their_own_analysis_when_other_members_exist` (the submitter keeps their own
access regardless of who else is a member) — replacing the earlier version's now-incorrect
`test_approved_member_can_access_analysis_they_did_not_submit`, which asserted the behavior this correction
removed. `test_historical_null_owner_record_accessible_only_to_member_or_admin` is unchanged and still correct —
membership still grants access to a `NULL`-owner row, exactly as designed.

`app/tests/test_founder_workspace.py` (14 tests, pre-existing from Phase 7.2) gained three new regression tests
for the second gap this review found and fixed —
`test_approved_member_cannot_read_another_members_private_analysis`,
`test_submitting_founder_still_sees_their_own_report_via_workspace`,
`test_approved_member_still_sees_historical_null_owner_analysis` — covering `get_founder_startup_workspace()`'s
own, separate, non-`_analysis_visibility_clause()` authorization path (Founder Workspace,
`GET /founder/startups/{startup_id}`).

`dashboard/tests/analysisVisibility.test.ts` (16 tests) covers the frontend side: pages call `auth.protect()`,
API client functions require a token, client components use a real Clerk token, the disclosure text exists,
`proxy.ts` is in sync, and My Startups/Saved don't render analysis content inline. No frontend changes were
required by this correction (it is a backend SQL/query fix only) — the suite was re-run to confirm.

Fixing the rule broke several **pre-existing** tests that asserted the old public/unscoped behavior — all updated
to assert the new, correct behavior (never silently deleted): `test_backend_authentication.py`,
`test_saved_startups.py`, `test_security_hardening.py`, `test_discovery.py`, `test_compare.py`,
`test_founder_missions.py`, `test_idea_structuring.py`, `test_startup_claims.py`, `test_idea_lab.py`,
`test_investor_workspace.py`, `test_startup_entity_migration.py` (all admin-bypass fixture updates, unrelated to
the rule itself, except the three files above with dedicated new coverage). All re-run for this correction and
still pass unchanged — none of them asserted the now-removed "any approved member sees any member's analysis"
behavior in the first place.

**Not yet in CI**: `test_founder_workspace.py` is not one of the files `.github/workflows/ci.yml`'s
`backend-legacy-core-journey` job runs (it predates Task 3B and was never added). Its three new tests above are
real regression coverage for a confidentiality fix in this same review, so it's a reasonable follow-up to add —
flagged here rather than added unilaterally, since it wasn't part of this task's own scope.

## Not fixed / out of scope

- `GET /analyses/search`'s legacy `company_text ILIKE` matching still runs against text the caller is now
  correctly scoped to — the narrow "does phrase X exist somewhere" probing risk Task 3A flagged as low-severity is
  now moot for anyone outside the authorized set (they get zero rows to probe against).
- `GET /analytics/industries`, `/analytics/sps-v3` remain unscoped — pure platform-wide **counts**, no per-company
  name/score/text, audited and judged a materially different, lower-risk category (same call made in Task 3A).
- Historical `NULL`-owner rows are permanently member/admin-only, by design — no backfill mechanism exists or was
  added.
