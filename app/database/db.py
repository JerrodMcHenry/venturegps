import os
import json
import hashlib
import secrets
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

# P0 Product Trust Cleanup: reuse the single source of truth for "what
# counts as the current canonical methodology" rather than hardcoding the
# version string a second time here. sie_v2_methodology.py has no
# project-internal imports of its own, so this does not introduce a
# circular import or any real import cost.
from app.ai.sie_v2_methodology import METHODOLOGY_VERSION



load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

# Phase 10.1A -- Critical Security/Runtime Hardening: pool_pre_ping=True
# issues a cheap "SELECT 1"-style liveness check before handing out a
# pooled connection, transparently discarding and replacing one a
# managed Postgres provider has silently closed server-side (e.g. after
# an idle timeout) instead of letting the caller's next real query fail
# with a raw OperationalError. Pool size/overflow/recycle are left at
# SQLAlchemy's defaults -- nothing in this codebase holds a connection
# open for the duration of an LLM call (every DB interaction is a short
# engine.begin() block), so the default pool is sufficient for expected
# beta load and there is no evidence of an actual sizing problem to fix.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)



def create_tables():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS analyses (
                id SERIAL PRIMARY KEY,
                company_text TEXT NOT NULL,
                summary TEXT NOT NULL,
                risk_analysis TEXT NOT NULL,
                competitor_analysis TEXT,
                memo TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                structured_analysis TEXT,
                investment_score TEXT,
                founder_analysis TEXT,
                market_analysis TEXT,
                sources TEXT,
                traction_analysis TEXT
            )
        """))

    print("PostgreSQL tables created successfully.")


def add_analysis_columns():
    columns = [
        "sources TEXT",
        "traction_analysis TEXT",
    ]

    for column in columns:
            column_name = column.split()[0]

            try:
                with engine.begin() as connection:
                    connection.execute(text(
                        f"ALTER TABLE analyses ADD COLUMN {column}"
                ))
                print(f"{column_name} column added")
            except Exception as e:
                print(f"{column_name} migration skipped", e)


def add_scoring_columns():
    columns = [
        "market_score INTEGER",
        "team_score INTEGER",
        "product_score INTEGER",
        "competition_score INTEGER",
        "traction_score INTEGER",
        "financial_score INTEGER",
        "overall_score INTEGER",
        "recommendation TEXT",

    ]

    for column in columns:
            column_name = column.split()[0]

            try:
                with engine.begin() as connection:
                    connection.execute(text(
                    f"ALTER TABLE analyses ADD COLUMN {column}"
                ))
                print(f"{column_name} column added")
            except Exception as e:
                print(f"{column_name} migration skipped", e)

def add_benchmarking_columns():
    columns = [
        "industry TEXT",
        "stage TEXT",
        "business_model TEXT"

    ]

    for column in columns:
        column_name = column.split()[0]

        try:
            with engine.begin() as connection:
                connection.execute(text(
                    f"ALTER TABLE analyses ADD COLUMN {column}"
                ))
                print(f"{column_name} column added")
        except Exception as e:
            print(f"{column_name} migration skipped", e)

def add_company_name_column():
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                ALTER TABLE analyses ADD COLUMN company_name TEXT
            """))
            print("company_name column added")
    except Exception as e:
        print("company_name migration skipped", e)


def add_readiness_columns():
    columns = [
        "readiness_score INTEGER",
        "readiness_summary TEXT"
    ]

    for column in columns:
        column_name = column.split()[0]

        try:
            with engine.begin() as connection:
                connection.execute(text(
                    f"ALTER TABLE analyses ADD COLUMN {column}"
                ))
            print(f"{column_name} column added")

        except Exception as e:
            print(f"{column_name} migration skipped", e)


def create_score_history_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS score_history (
                id SERIAL PRIMARY KEY,
                analysis_id INTEGER REFERENCES analyses(id) ON DELETE CASCADE,
                company_name TEXT,
                industry TEXT,
                stage TEXT,
                business_model TEXT,
                market_score INTEGER,
                team_score INTEGER,
                product_score INTEGER,
                competition_score INTEGER,
                traction_score INTEGER,
                financial_score INTEGER,
                overall_score INTEGER,
                readiness_score INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

    print("score_history table created successfully.")


# ---------------------------------------------------------------------------
# SIE Accounts & Ownership -- Canonical Startup Entity (first implementation
# slice; see the accompanying architecture design). This introduces a real
# `startups` row as the stable identity every canonical query (get_rankings,
# search_analyses, get_startup_by_name, get_sps_history,
# get_top_improving_startups) has always re-derived ad hoc via
# LOWER(TRIM(company_name)) grouping, instead of storing it anywhere.
#
# Foundation only in this slice: create_users_table() /
# create_startup_memberships_table() / create_saved_startups_table() exist
# so the schema is in place, but nothing populates them yet -- no
# authentication, no ownership assignment, no Saved Startups behavior.
# Every startup created by backfill_startup_ids() below is unowned by
# construction (it never touches startup_memberships), per the explicit
# product decision that analysis and ownership are separate concepts and
# analyzing a startup must never grant membership.
#
# None of the existing canonical read queries are migrated to use
# startup_id in this slice -- they are left completely untouched so this
# migration's correctness can be verified independently of any product
# behavior change (see the test suite and the stabilization report this
# slice produces).
# ---------------------------------------------------------------------------

def create_startups_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS startups (
                id SERIAL PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

    print("startups table created successfully.")


def add_startup_id_column():
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE analyses ADD COLUMN startup_id INTEGER REFERENCES startups(id)"
            ))
        print("startup_id column added")
    except Exception as e:
        print("startup_id migration skipped", e)


def add_analysis_submitted_by_column():
    """
    Portfolio Release Task 3B -- Secure Analysis Visibility. Nullable,
    additive, same pattern as every other add_*_column() here. References
    users(id) (ON DELETE SET NULL, not CASCADE -- a deleted user's past
    analyses stay in place, they simply lose their recorded submitter,
    same end state as any other historical NULL row below).

    MUST run after create_users_table() (the FK target) -- see the call
    order in app/api.py's migration sequence.

    Deliberately never backfilled: every row that existed before this
    migration has, and will always have, submitted_by_user_id = NULL.
    That is not a bug to fix later -- app/auth.py's analysis-visibility
    rule (see user_can_view_analysis()) treats a NULL-owner row as visible
    only to an approved startup_memberships holder or an admin, never to
    an unauthenticated caller and never to an arbitrary signed-in
    "submitter" match (there is no submitter recorded to match). No
    existing row is deleted, rewritten, or reinterpreted -- this migration
    only adds a column that future INSERTs populate.

    The accompanying index exists because every read path this task adds
    (GET /startup/{name}, rankings, discovery, comparison, search, score
    history) now filters on this column (see
    app/database/db.py's _analysis_visibility_clause()) in addition to
    startup_id, which already had its own FK (and therefore implicit)
    index-friendly access pattern from get_or_create_startup().
    """
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE analyses ADD COLUMN submitted_by_user_id TEXT REFERENCES users(id) ON DELETE SET NULL"
            ))
        print("submitted_by_user_id column added")
    except Exception as e:
        print("submitted_by_user_id migration skipped", e)

    try:
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS analyses_submitted_by_user_id_idx "
                "ON analyses (submitted_by_user_id)"
            ))
        print("analyses_submitted_by_user_id_idx index created")
    except Exception as e:
        print("analyses_submitted_by_user_id_idx migration skipped", e)


def create_users_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

    print("users table created successfully.")


def get_or_create_user(user_id: str, email: str | None = None) -> None:
    """
    SIE Authentication Phase 2 -- lazy users-table synchronization. Called
    by app/auth.py's get_current_user() dependency on every successfully
    authenticated request. Idempotent: ON CONFLICT DO NOTHING, so a
    user's first authenticated request creates their row and every
    request after that is a safe no-op -- never a duplicate, never an
    error, no explicit "does this user already exist" check needed first.

    Deliberately does not update email on conflict: Clerk is the actual
    identity source of truth (see the SIE Accounts & Ownership
    architecture design) -- this table exists only so
    startup_memberships/saved_startups have a stable local foreign-key
    target, not to mirror a Clerk profile. Whatever email was present (or
    not) on a user's first authenticated request is what's stored;
    keeping it in sync with Clerk on every change is explicitly out of
    scope here (no webhook infrastructure, per that design).

    This function creates ONLY a users row. It never touches
    startup_memberships or saved_startups -- authentication means "this
    user exists," never "this user owns a startup."
    """
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO users (id, email)
            VALUES (:id, :email)
            ON CONFLICT (id) DO NOTHING
        """), {"id": user_id, "email": email})


def create_startup_memberships_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS startup_memberships (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                startup_id INTEGER NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
                role TEXT NOT NULL DEFAULT 'owner',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT startup_memberships_user_startup_key UNIQUE (user_id, startup_id)
            )
        """))

    print("startup_memberships table created successfully.")


# ---------------------------------------------------------------------------
# Phase 7.1A -- Startup Claim & Membership backend lifecycle.
#
# CORE INVARIANT, stated once here as the single source of truth: the
# ONLY code path in this entire application allowed to INSERT INTO
# startup_memberships is approve_startup_claim() below, and it only ever
# does so for a claim that was, at the instant of that same transaction,
# genuinely status='pending'. Submitting a claim, viewing a claim,
# rejecting a claim, and cancelling a claim all create ZERO membership
# rows -- this is enforced by construction (those functions simply never
# contain an INSERT INTO startup_memberships statement), not by a runtime
# check. Analyzing a startup, saving a startup, and creating a modeled
# venture have never touched this table and still don't -- see
# get_or_create_startup()'s, save_startup_for_user()'s, and
# create_modeled_venture()'s own docstrings.
#
# role is ALWAYS 'member' on approval, regardless of claim order. Phase
# 7.1's original design considered auto-assigning 'owner' to the first
# approved claimant; that was explicitly corrected before implementation
# -- approval order is not proof of superior ownership authority. Owner
# elevation is deferred to a future, intentionally-designed member-
# administration feature. startup_memberships.role's column/default are
# unchanged; every INSERT below simply specifies role='member' explicitly.
# ---------------------------------------------------------------------------

class StartupClaimError(Exception):
    """Base class for clean, application-level claim failures -- never a
    raw IntegrityError/psycopg2 exception surfacing to app/api.py."""


class StartupNotFoundError(StartupClaimError):
    pass


class DuplicatePendingClaimError(StartupClaimError):
    pass


class AlreadyMemberError(StartupClaimError):
    """Raised when the claimant already has an approved membership for
    this startup -- Part 3's 'an existing membership should prevent
    unnecessary duplicate claiming'."""


def create_startup_claims_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS startup_claims (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                startup_id INTEGER NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
                verification_method TEXT NOT NULL DEFAULT 'manual_review',
                justification TEXT,
                contact_email TEXT,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP,
                reviewed_by TEXT REFERENCES users(id),
                rejection_reason TEXT
            )
        """))

    with engine.begin() as connection:
        # Partial unique index: at most one PENDING claim per
        # (user_id, startup_id) -- a rejected or cancelled prior claim
        # does NOT count toward this, so resubmission is always possible
        # (Part 6/9's explicit "rejected claim can be resubmitted").
        connection.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS startup_claims_one_pending_per_user_startup
            ON startup_claims (user_id, startup_id)
            WHERE status = 'pending'
        """))

    print("startup_claims table created successfully.")


def create_startup_claim(
    user_id: str,
    startup_id: int,
    justification: str,
    contact_email: str | None,
    verification_method: str = "manual_review",
) -> int:
    """
    Creates exactly one pending startup_claims row. Never touches
    startup_memberships -- see this section's own module-level comment.

    `verification_method` defaults to 'manual_review' -- the exact
    previous, hardcoded value -- so every existing caller is byte-for-byte
    unaffected. Phase 31 -- Venture -> Startup Graduation V1 -- is the one
    new caller passing 'venture_graduation' instead: a claim whose
    provenance is unambiguous (the startup row was just created, in the
    same request, from this exact user's own venture, so there is no
    possibility of a competing/false claim the way there is for a
    pre-existing Analyze-created startup) and is therefore immediately
    self-approved rather than queued for human review -- see
    create_venture_graduation()'s own docstring for the full reasoning.
    This column has no CHECK constraint (unlike `status`), so this is a
    purely additive, non-breaking parameter.

    Raises:
        StartupNotFoundError -- startup_id doesn't exist.
        AlreadyMemberError -- the caller already has an approved
            membership for this startup; a new claim would be redundant.
        DuplicatePendingClaimError -- the caller already has a pending
            claim for this startup (checked explicitly, then re-checked
            via the partial unique index itself as a race-safe fallback
            if two concurrent requests both pass the initial check).
    """
    with engine.begin() as connection:
        startup_exists = connection.execute(
            text("SELECT 1 FROM startups WHERE id = :startup_id"),
            {"startup_id": startup_id},
        ).scalar()

        if startup_exists is None:
            raise StartupNotFoundError(f"Startup {startup_id} does not exist")

        already_member = connection.execute(text("""
            SELECT 1 FROM startup_memberships
            WHERE user_id = :user_id AND startup_id = :startup_id
        """), {"user_id": user_id, "startup_id": startup_id}).scalar()

        if already_member is not None:
            raise AlreadyMemberError(
                f"User {user_id} is already a member of startup {startup_id}"
            )

        already_pending = connection.execute(text("""
            SELECT 1 FROM startup_claims
            WHERE user_id = :user_id AND startup_id = :startup_id AND status = 'pending'
        """), {"user_id": user_id, "startup_id": startup_id}).scalar()

        if already_pending is not None:
            raise DuplicatePendingClaimError(
                f"User {user_id} already has a pending claim for startup {startup_id}"
            )

        try:
            result = connection.execute(text("""
                INSERT INTO startup_claims (
                    user_id, startup_id, status, verification_method,
                    justification, contact_email
                )
                VALUES (
                    :user_id, :startup_id, 'pending', :verification_method,
                    :justification, :contact_email
                )
                RETURNING id
            """), {
                "user_id": user_id,
                "startup_id": startup_id,
                "verification_method": verification_method,
                "justification": justification,
                "contact_email": contact_email,
            })
        except IntegrityError as error:
            # Race-safe fallback: two concurrent requests could both pass
            # the already_pending check above before either commits: the
            # partial unique index itself is the final authority.
            raise DuplicatePendingClaimError(
                f"User {user_id} already has a pending claim for startup {startup_id}"
            ) from error

        return result.scalar()


def list_startup_claims_for_user(user_id: str):
    """Only the caller's OWN claims -- see GET /me/startup-claims in
    app/api.py. Deliberately excludes justification/contact_email (not
    part of Part 4's required field list for this endpoint) and every
    other user's data by construction (the WHERE clause is the only
    thing that can ever match a row)."""
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT
                sc.id AS id,
                sc.startup_id AS startup_id,
                s.canonical_name AS canonical_name,
                sc.status AS status,
                sc.verification_method AS verification_method,
                sc.submitted_at AS submitted_at,
                sc.reviewed_at AS reviewed_at,
                sc.rejection_reason AS rejection_reason
            FROM startup_claims sc
            JOIN startups s ON s.id = sc.startup_id
            WHERE sc.user_id = :user_id
            ORDER BY sc.submitted_at DESC
        """), {"user_id": user_id})

        return [dict(row) for row in result.mappings().all()]


def get_startup_claim_status_for_user(user_id: str, startup_id: int):
    """
    Smallest useful helper for Phase 7.1B's future 'Claim this startup'
    control: the caller's own most recent claim for this one startup, or
    None if they've never claimed it. Never reveals whether anyone ELSE
    has claimed or been approved for this startup -- scoped to user_id in
    the SQL itself, same discipline as every other per-user query in this
    file.

    Phase 32A -- Trust-State Consistency: verification_method now
    selected alongside status -- the same column list_startup_claims_for_
    user() already reads two functions below, just missing here. Every
    startup_memberships row was created by approve_startup_claim() acting
    on some startup_claims row (this table's own core invariant, stated
    at create_startup_memberships_table()'s section comment), and
    AlreadyMemberError prevents a second claim once membership exists --
    so "the caller's most recent claim for this startup" is always the
    one claim whose verification_method actually explains how they got
    (or are trying to get) access, never an unrelated stale row.
    """
    with engine.begin() as connection:
        row = connection.execute(text("""
            SELECT id, status, verification_method, submitted_at, reviewed_at, rejection_reason
            FROM startup_claims
            WHERE user_id = :user_id AND startup_id = :startup_id
            ORDER BY submitted_at DESC
            LIMIT 1
        """), {"user_id": user_id, "startup_id": startup_id}).mappings().first()

        return dict(row) if row is not None else None


def list_pending_startup_claims_for_admin():
    """
    Admin-only READ -- authorization (RequireAdmin) is enforced entirely
    at the API layer in app/api.py, matching this file's existing
    convention that DB functions implement queries, not access control
    (e.g. get_saved_startups_for_user() doesn't re-check auth either; the
    endpoint does). This function has no per-user filter by design --
    an admin legitimately needs to see every pending claim.

    existing_member_count gives the reviewer context (Part 4/6: "already
    has a member" is information for the human, never a submission
    blocker) without a second round trip.
    """
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT
                sc.id AS id,
                sc.startup_id AS startup_id,
                s.canonical_name AS canonical_name,
                sc.user_id AS user_id,
                u.email AS user_email,
                sc.contact_email AS contact_email,
                sc.justification AS justification,
                sc.submitted_at AS submitted_at,
                (
                    SELECT COUNT(*) FROM startup_memberships sm
                    WHERE sm.startup_id = sc.startup_id
                ) AS existing_member_count
            FROM startup_claims sc
            JOIN startups s ON s.id = sc.startup_id
            JOIN users u ON u.id = sc.user_id
            WHERE sc.status = 'pending'
            ORDER BY sc.submitted_at ASC
        """))

        return [dict(row) for row in result.mappings().all()]


def approve_startup_claim(claim_id: int, admin_user_id: str):
    """
    THE ONLY function in this entire codebase that may INSERT INTO
    startup_memberships. Fully atomic in one transaction:

    1. SELECT ... FOR UPDATE locks this specific claim row for the
       duration of the transaction -- a concurrent second approval
       attempt on the SAME claim_id blocks here until this transaction
       commits or rolls back, then re-reads status and correctly finds
       it's no longer 'pending' (Part 9's "approval race cannot create
       duplicate memberships").
    2. If the claim doesn't exist or isn't currently pending (already
       approved/rejected/cancelled, or a concurrent approval already won
       the race), this returns None and writes NOTHING -- not an error,
       just "nothing to do".
    3. Otherwise: insert the membership (role ALWAYS 'member' -- see this
       section's own module-level comment), with ON CONFLICT DO NOTHING
       as a second, independent layer of duplicate protection (the
       existing UNIQUE(user_id, startup_id) constraint on
       startup_memberships), then mark the claim approved with
       reviewed_at/reviewed_by.

    Because both writes happen inside the same engine.begin() block, a
    failure in either one rolls back both -- an approved claim can never
    exist without its membership, and a failed claim-status update can
    never leave an unauthorized membership behind.
    """
    with engine.begin() as connection:
        claim = connection.execute(text("""
            SELECT id, user_id, startup_id, status
            FROM startup_claims
            WHERE id = :claim_id
            FOR UPDATE
        """), {"claim_id": claim_id}).mappings().first()

        if claim is None or claim["status"] != "pending":
            return None

        connection.execute(text("""
            INSERT INTO startup_memberships (user_id, startup_id, role)
            VALUES (:user_id, :startup_id, 'member')
            ON CONFLICT (user_id, startup_id) DO NOTHING
        """), {"user_id": claim["user_id"], "startup_id": claim["startup_id"]})

        connection.execute(text("""
            UPDATE startup_claims
            SET status = 'approved',
                reviewed_at = CURRENT_TIMESTAMP,
                reviewed_by = :admin_user_id
            WHERE id = :claim_id
        """), {"claim_id": claim_id, "admin_user_id": admin_user_id})

        return {
            "claim_id": claim_id,
            "user_id": claim["user_id"],
            "startup_id": claim["startup_id"],
        }


def reject_startup_claim(claim_id: int, admin_user_id: str, rejection_reason: str) -> bool:
    """Only a currently-pending claim transitions to rejected -- the
    WHERE status = 'pending' guard makes this a safe no-op (0 rows
    affected) against an already-decided or concurrently-decided claim.
    Creates zero startup_memberships rows, always."""
    with engine.begin() as connection:
        result = connection.execute(text("""
            UPDATE startup_claims
            SET status = 'rejected',
                reviewed_at = CURRENT_TIMESTAMP,
                reviewed_by = :admin_user_id,
                rejection_reason = :rejection_reason
            WHERE id = :claim_id AND status = 'pending'
        """), {
            "claim_id": claim_id,
            "admin_user_id": admin_user_id,
            "rejection_reason": rejection_reason,
        })

        return result.rowcount > 0


def cancel_startup_claim(user_id: str, claim_id: int) -> bool:
    """Claimant-only (WHERE user_id = :user_id), own-claim-only, and only
    a currently-pending claim can be cancelled. Zero membership effect."""
    with engine.begin() as connection:
        result = connection.execute(text("""
            UPDATE startup_claims
            SET status = 'cancelled'
            WHERE id = :claim_id AND user_id = :user_id AND status = 'pending'
        """), {"claim_id": claim_id, "user_id": user_id})

        return result.rowcount > 0


# ---------------------------------------------------------------------------
# Phase 7.1C -- Founder Membership Authorization Foundation. Purely
# additive reads: no new table, no new INSERT path. startup_memberships
# remains write-once via approve_startup_claim() above -- that function's
# own module-level comment is still the single source of truth for "the
# only place this table is ever written."
#
# The distinction these two functions exist to enforce, ahead of Phase
# 7.2 Founder Workspace: an approved startup_claims row is historical
# evidence that approval happened once; a live startup_memberships row is
# the ONLY current authorization truth. Neither function below ever
# consults startup_claims, saved_startups, or modeled_ventures -- so if a
# membership-removal path is ever added in the future, these functions
# correctly stop authorizing access the instant the row is gone, even
# though the original claim would still read 'approved' forever (claims
# are an immutable historical record; see approve_startup_claim()'s own
# docstring -- it never rewrites a claim once decided).
# ---------------------------------------------------------------------------

def get_startup_memberships_for_user(user_id: str):
    """
    Every canonical startup this user currently has authorized access to
    -- one row per startup_memberships relationship belonging to them,
    derived from that table alone. A user with memberships at several
    startups gets one row each (no assumption anywhere that a user
    belongs to at most one startup); a startup with several members
    likewise has one independent row per member here, scoped by user_id
    in the WHERE clause the same way get_saved_startups_for_user() and
    list_startup_claims_for_user() are scoped.

    Deliberately does not join in SPS/industry/stage/or any other
    intelligence field -- see this section's own module-level comment.
    A future founder surface that needs current intelligence per startup
    should join out to canonical analyses via startup_id at read time,
    the same "join, don't copy" principle get_saved_startups_for_user()
    already applies.

    Phase 37B: additionally exposes `linked_venture_id` -- the same
    ownership-checked resolution resolve_linked_venture_for_owned_startup()
    performs for a single startup, batched here as one extra LEFT JOIN
    rather than N follow-up calls (Section 23/24's own "avoid an extra
    network request per startup" instruction). The second LEFT JOIN's own
    `mv.user_id = sm.user_id` condition is what makes this fail closed:
    since this whole query is already scoped to `sm.user_id = :user_id`,
    that condition is equivalent to checking the linked venture's owner
    against the current caller -- if a venture_graduations row exists but
    points at a venture owned by someone else, `mv.id` (and therefore
    `linked_venture_id`) comes back NULL, never that other user's row.
    """
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT
                sm.id AS membership_id,
                sm.startup_id AS startup_id,
                s.canonical_name AS canonical_name,
                sm.role AS role,
                sm.created_at AS created_at,
                mv.id AS linked_venture_id
            FROM startup_memberships sm
            JOIN startups s ON s.id = sm.startup_id
            LEFT JOIN venture_graduations vg ON vg.startup_id = sm.startup_id
            LEFT JOIN modeled_ventures mv ON mv.id = vg.venture_id AND mv.user_id = sm.user_id
            WHERE sm.user_id = :user_id
            ORDER BY sm.created_at ASC
        """), {"user_id": user_id})

        return [dict(row) for row in result.mappings().all()]


def _analysis_visibility_clause(table_alias: str = "") -> str:
    """
    Portfolio Release Task 3B -- Secure Analysis Visibility. A SQL boolean
    condition: TRUE iff the analysis row (from `table_alias` or bare
    `analyses` if no alias) is visible to the calling viewer. Every query
    that uses this must bind two parameters alongside its own:
    :viewer_user_id (the caller's verified Clerk user_id -- every route
    that reaches these functions is RequireAuth-gated, so this is never
    NULL in practice) and :viewer_is_admin (a plain bool, from
    app.auth.is_admin(current_user.user_id) at the call site).

    CORRECTED (final security review, before commit): approved startup
    membership is NOT a general grant. It only ever substitutes for a
    missing submitter on a historical row. A live analysis someone else
    submitted stays private to that submitter -- being an approved member
    of the same startup is not enough to read it. Two tiers:

      1. the analysis's own submitter (submitted_by_user_id = :viewer_user_id)
         always sees it, regardless of anyone else's membership.
      2. a row with submitted_by_user_id IS NULL (every analysis that
         existed before this migration -- see
         add_analysis_submitted_by_column(), never backfilled) has no
         submitter to match, so it falls back to the pre-migration rule:
         visible to an approved member of the associated startup (a live
         startup_memberships row for (:viewer_user_id, this row's
         startup_id)). This is what "preserving existing founder access"
         means -- it applies ONLY to NULL-owner rows, never to a row with
         a real submitted_by_user_id that isn't :viewer_user_id.
      3. an admin (:viewer_is_admin) always sees it, bypassing 1 and 2.

    The previous version of this clause let branch 2 (membership) apply
    unconditionally to every row, submitter or not -- meaning any approved
    member of a startup could read a private analysis a *different* member
    submitted about that same startup. That was the cross-user
    confidentiality bug this correction fixes. Saved startups, watchlists,
    and company-name matches were never and are still never a branch of
    this clause -- they carry no visibility grant of their own.

    This clause is deliberately placed INSIDE each query's own WHERE
    clause, before any ROW_NUMBER()/DISTINCT ON "pick the latest" logic --
    never applied as a post-fetch filter in Python -- so "the latest
    analysis" always means "the latest analysis this viewer is authorized
    to see," not "the globally latest one, access-checked afterward" (the
    latter would incorrectly hide a viewer's own analysis behind a
    stranger's newer, inaccessible one for the same company).
    """
    prefix = f"{table_alias}." if table_alias else ""
    return f"""(
        :viewer_is_admin
        OR {prefix}submitted_by_user_id = :viewer_user_id
        OR (
            {prefix}submitted_by_user_id IS NULL
            AND {prefix}startup_id IN (
                SELECT startup_id FROM startup_memberships WHERE user_id = :viewer_user_id
            )
        )
    )"""


def user_has_startup_membership(user_id: str, startup_id: int) -> bool:
    """
    The single question every founder-only authorization check reduces
    to: does a live startup_memberships row exist for this exact
    (user_id, startup_id) pair? No claim history, no client-supplied
    role, no other table is ever consulted here -- see RequireStartupMember
    in app/auth.py, the intended caller for Phase 7.2's founder-only
    routes.
    """
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT 1 FROM startup_memberships
            WHERE user_id = :user_id AND startup_id = :startup_id
        """), {"user_id": user_id, "startup_id": startup_id})

        return result.first() is not None


# ---------------------------------------------------------------------------
# Phase 7.2 -- Founder Workspace V1. One read-only function, no new table,
# no new write path. Authorization for who may call this is entirely the
# caller's job (RequireStartupMember in app/auth.py) -- this function
# itself trusts startup_id unconditionally, same division of
# responsibility list_pending_startup_claims_for_admin() already
# documents for RequireAdmin.
# ---------------------------------------------------------------------------

def get_founder_startup_workspace(startup_id: int, user_id: str):
    """
    Everything Founder Workspace V1's default view needs for one startup,
    in one read: the canonical identity (from startups itself, so this
    resolves even for a startup with zero analyses yet), its latest
    canonical intelligence, and its full SPS history.

    Deliberately resolves the latest analysis by the real startup_id FK
    (analyses.startup_id) rather than by company_name string-matching --
    a stricter, more correct key than get_startup_by_name() uses, made
    possible here because the caller always already has a real startup_id
    (from startup_memberships, via RequireStartupMember) rather than a
    URL-provided name. Uses the exact same "methodology IS NOT NULL"
    filter as get_startup_by_name() (no additional methodology_version
    gate), so this always reports the same current SPS as the public
    Startup Profile for the same startup -- the two are never allowed to
    disagree about "what is this company's current intelligence".

    methodology/created_at are None when no canonical analysis exists yet
    for this startup -- never fabricated to a placeholder score. Returns
    None only if startup_id itself doesn't resolve to a real startups
    row, which should never happen once RequireStartupMember has already
    passed (a membership row can't exist for a startup_id that isn't
    real, per the FK), but is still checked so this function is safe to
    call on its own.

    Phase 37B: `user_id` (the already-authenticated, already-membership-
    checked caller) is used ONLY to resolve `linked_venture_id` via
    resolve_linked_venture_for_owned_startup() -- the ownership-checked
    routing signal, distinct from the unfiltered `graduated_from_venture`
    acknowledgment below. Never used to re-check startup membership
    itself (that remains RequireStartupMember's job).

    CORRECTED (final security review, before commit): `user_id` is now
    ALSO used to filter which analyses this function will ever return.
    Before this fix, both queries below selected across every analysis
    for this startup_id with no owner check at all -- so an approved
    member (RequireStartupMember only confirms membership, not submitter
    identity) could see another member's privately-submitted analysis
    just by opening Founder Workspace for a shared startup, the exact
    cross-user confidentiality bug this review targets, via a path that
    doesn't go through _analysis_visibility_clause() at all. The filter
    mirrors that clause's own two tiers, inlined rather than reused,
    because membership is already an established precondition of reaching
    this function (RequireStartupMember already ran) so there's no need
    to re-derive it with a startup_memberships subquery here:
    submitted_by_user_id = :user_id (their own submission) OR
    submitted_by_user_id IS NULL (a historical row -- preserved,
    unchanged, exactly "existing founder access"). A row another member
    submitted is skipped by both queries, same as everywhere else this
    policy applies.
    """
    with engine.begin() as connection:
        startup_row = connection.execute(text("""
            SELECT id, canonical_name FROM startups WHERE id = :startup_id
        """), {"startup_id": startup_id}).mappings().first()

        if startup_row is None:
            return None

        analysis_row = connection.execute(text("""
            SELECT id, created_at, methodology
            FROM analyses
            WHERE startup_id = :startup_id
              AND methodology IS NOT NULL
              AND (submitted_by_user_id = :user_id OR submitted_by_user_id IS NULL)
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """), {"startup_id": startup_id, "user_id": user_id}).mappings().first()

        history_rows = connection.execute(text("""
            SELECT
                id,
                created_at,
                methodology->>'startup_intelligence_score' AS sps
            FROM analyses
            WHERE startup_id = :startup_id
              AND methodology IS NOT NULL
              AND (submitted_by_user_id = :user_id OR submitted_by_user_id IS NULL)
            ORDER BY created_at ASC, id ASC
        """), {"startup_id": startup_id, "user_id": user_id}).mappings().all()

    methodology = None
    created_at = None

    if analysis_row is not None:
        created_at = analysis_row["created_at"]
        methodology = analysis_row["methodology"]

        if isinstance(methodology, str):
            methodology = json.loads(methodology)

    # Phase 31 -- Venture -> Startup Graduation V1, Part 11. A second,
    # independent read (get_venture_graduation_by_startup() opens its own
    # connection) rather than folding into the transaction above -- this
    # is a rare, tiny lookup (at most one row ever exists per startup_id,
    # per that table's own UNIQUE(venture_id) -- not per-startup, but a
    # given startup can only ever be the *target* of one graduation
    # relationship in practice for V1's single-founder-initiated flow) and
    # keeping it separate means a future change to either function never
    # risks the other's transaction boundary.
    graduated_from_venture = get_venture_graduation_by_startup(startup_row["id"])
    linked_venture_id = resolve_linked_venture_for_owned_startup(user_id, startup_row["id"])

    return {
        "startup_id": startup_row["id"],
        "canonical_name": startup_row["canonical_name"],
        "created_at": created_at,
        "methodology": methodology,
        "sps_history": [
            {
                "analysis_id": row["id"],
                "created_at": row["created_at"],
                "startup_intelligence_score": (
                    float(row["sps"]) if row["sps"] is not None else None
                ),
            }
            for row in history_rows
        ],
        "graduated_from_venture": (
            {
                "venture_id": graduated_from_venture["venture_id"],
                "venture_name": graduated_from_venture["venture_name"],
            }
            if graduated_from_venture is not None
            else None
        ),
        "linked_venture_id": linked_venture_id,
    }


FOUNDER_ACTION_STATUSES = ("todo", "in_progress", "completed", "dismissed")
FOUNDER_ACTION_SOURCES = ("sie_recommendation", "founder_created")
FOUNDER_ACTION_PILLARS = (
    "market", "team", "product", "execution", "traction", "financial_health",
)


class FounderActionError(Exception):
    """Base class for clean, application-level founder-action failures --
    never a raw IntegrityError/psycopg2 exception surfacing to app/api.py.
    Mirrors StartupClaimError's own role for the claims section above."""


class FounderActionNotFoundError(FounderActionError):
    pass


# ---------------------------------------------------------------------------
# Phase 7.3 -- Founder Progress & Improvement V1. founder_actions is a
# dedicated, purely additive table -- it is NEVER read by, written by, or
# joined into anything in the scoring/methodology path (analyses,
# startup_intelligence_score, PillarAnalysis, VPS, calibration). It holds
# workflow state ONLY: what a founder intends to do or has done, never
# evidence and never a score. See this section's own tests
# (test_founder_actions.py) for the code-level audit proving that
# no function here ever writes analyses.methodology, any *_score column,
# or startup_memberships.
#
# Shared per-startup, not per-member (explicit product decision, Part 11):
# every list/update function below is scoped by startup_id alone --
# created_by_user_id is recorded for provenance/attribution only, never
# used to filter what a member can see or move between statuses. Any
# verified member of a startup sees and can act on the same plan.
# ---------------------------------------------------------------------------

def create_founder_actions_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS founder_actions (
                id SERIAL PRIMARY KEY,
                startup_id INTEGER NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
                created_by_user_id TEXT NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                description TEXT,
                related_pillar TEXT,
                status TEXT NOT NULL DEFAULT 'todo'
                    CHECK (status IN ('todo', 'in_progress', 'completed', 'dismissed')),
                -- Phase 8 added 'fundraising_gap' alongside the original
                -- two values (see
                -- add_fundraising_gap_source_to_founder_actions() below
                -- for the matching migration on a database that already
                -- has this table) -- backward compatible, existing rows
                -- are untouched either way.
                source TEXT NOT NULL
                    CHECK (source IN ('sie_recommendation', 'founder_created', 'fundraising_gap')),
                -- Dedup key for non-founder-authored actions (see
                -- create_founder_action()'s own docstring) -- always NULL
                -- for founder_created, so the partial unique index below
                -- never constrains founder-authored text at all.
                source_ref TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """))

        # Scoped to (startup_id, source_ref), not globally -- the exact
        # same recommendation/gap text for a DIFFERENT startup is a
        # distinct, legitimate row; only a second copy of the SAME
        # recommendation/gap for the SAME startup is blocked.
        # WHERE source <> 'founder_created' covers both
        # 'sie_recommendation' and Phase 8's 'fundraising_gap' (and any
        # future non-founder-authored source) with one predicate, while
        # founder_created rows (whose source_ref is always NULL) are
        # never constrained by it at all -- see create_founder_action()'s
        # own docstring for why founder-authored text is deliberately
        # never deduplicated.
        connection.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS founder_actions_dedup_sie_recommendation
            ON founder_actions (startup_id, source_ref)
            WHERE source <> 'founder_created'
        """))

    print("founder_actions table created successfully.")


def add_fundraising_gap_source_to_founder_actions():
    """
    Phase 8 migration for a database where founder_actions already
    exists from Phase 7.3/CREATE TABLE IF NOT EXISTS never re-runs the
    body above. Idempotent: DROP ... IF EXISTS + CREATE, safe to call on
    every startup. Widens the CHECK constraint to allow 'fundraising_gap'
    and widens the dedup index's predicate to match (see
    create_founder_actions_table()'s own comment for why
    `source <> 'founder_created'` is the correct predicate for both).
    Never touches existing rows.
    """
    with engine.begin() as connection:
        connection.execute(text("""
            ALTER TABLE founder_actions DROP CONSTRAINT IF EXISTS founder_actions_source_check
        """))
        connection.execute(text("""
            ALTER TABLE founder_actions ADD CONSTRAINT founder_actions_source_check
            CHECK (source IN ('sie_recommendation', 'founder_created', 'fundraising_gap'))
        """))
        connection.execute(text("""
            DROP INDEX IF EXISTS founder_actions_dedup_sie_recommendation
        """))
        connection.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS founder_actions_dedup_sie_recommendation
            ON founder_actions (startup_id, source_ref)
            WHERE source <> 'founder_created'
        """))

    print("founder_actions.source migrated to include fundraising_gap.")


def list_founder_actions_for_startup(startup_id: int):
    """Every action for this startup, regardless of who created it or its
    current status -- the frontend groups by status client-side (Next Up
    / In Progress / Completed / dismissed items simply omitted from the
    default view). Authorization (RequireStartupMember) is enforced
    entirely at the API layer, matching this file's existing convention
    (e.g. list_pending_startup_claims_for_admin()'s own docstring)."""
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT
                id, startup_id, created_by_user_id, title, description,
                related_pillar, status, source, source_ref,
                created_at, updated_at, completed_at
            FROM founder_actions
            WHERE startup_id = :startup_id
            ORDER BY created_at ASC
        """), {"startup_id": startup_id})

        return [dict(row) for row in result.mappings().all()]


def create_founder_action(
    startup_id: int,
    created_by_user_id: str,
    title: str,
    description: str | None,
    related_pillar: str | None,
    source: str,
):
    """
    Creates one founder_actions row, OR -- for a non-founder-authored
    action (source='sie_recommendation' or, since Phase 8,
    'fundraising_gap') whose exact title already exists for this startup
    -- returns the existing row untouched instead of erroring or
    creating a duplicate. This is the "Add to Plan" idempotency guarantee
    (Part 13/Phase 8 Part 16): clicking it twice on the same suggested
    recommendation or fundraising gap is a safe no-op, never a second
    row, never a 409 the frontend has to explain.

    source_ref (the dedup key) is derived HERE from title, never accepted
    from the caller -- there is no client-supplied identity field to
    spoof or collide. founder_created rows always get source_ref=None,
    so two founder-authored actions with coincidentally identical text
    are both kept -- see this function's own module-level comment for why
    that's deliberate (founder text is not deduplicated).

    Existing-row lookup on conflict is a second, separate SELECT rather
    than relying on RETURNING (which is empty on an ON CONFLICT DO
    NOTHING no-op) -- both happen inside the same transaction, so this
    is still atomic with respect to a concurrent identical insert.
    """
    source_ref = title.strip() if source != "founder_created" else None

    with engine.begin() as connection:
        result = connection.execute(text("""
            INSERT INTO founder_actions (
                startup_id, created_by_user_id, title, description,
                related_pillar, status, source, source_ref
            )
            VALUES (
                :startup_id, :created_by_user_id, :title, :description,
                :related_pillar, 'todo', :source, :source_ref
            )
            ON CONFLICT (startup_id, source_ref)
                WHERE source <> 'founder_created'
                DO NOTHING
            RETURNING
                id, startup_id, created_by_user_id, title, description,
                related_pillar, status, source, source_ref,
                created_at, updated_at, completed_at
        """), {
            "startup_id": startup_id,
            "created_by_user_id": created_by_user_id,
            "title": title,
            "description": description,
            "related_pillar": related_pillar,
            "source": source,
            "source_ref": source_ref,
        })

        row = result.mappings().first()

        if row is not None:
            return dict(row)

        # Conflict: an sie_recommendation with this exact title already
        # exists for this startup -- return it as-is (see this function's
        # own docstring; never revives a dismissed one, never duplicates).
        existing = connection.execute(text("""
            SELECT
                id, startup_id, created_by_user_id, title, description,
                related_pillar, status, source, source_ref,
                created_at, updated_at, completed_at
            FROM founder_actions
            WHERE startup_id = :startup_id AND source_ref = :source_ref
        """), {"startup_id": startup_id, "source_ref": source_ref}).mappings().first()

        return dict(existing)


def update_founder_action_status(startup_id: int, action_id: int, new_status: str):
    """
    Returns the updated row, or None if this action_id doesn't exist for
    this exact startup_id (never revealing whether it exists for a
    DIFFERENT startup -- the WHERE clause is what makes a cross-startup
    update structurally impossible, not a check performed after the
    fact, same discipline as update_modeled_venture_for_user()'s own
    user_id-scoped WHERE clause).

    completed_at is set to NOW() only on a transition INTO 'completed',
    and cleared back to NULL on any transition AWAY from it (the
    "reopen" case) -- never touched for a lateral move between the other
    three statuses. updated_at always advances.
    """
    with engine.begin() as connection:
        result = connection.execute(text("""
            UPDATE founder_actions
            SET status = :new_status,
                updated_at = CURRENT_TIMESTAMP,
                completed_at = CASE
                    WHEN :new_status = 'completed' THEN CURRENT_TIMESTAMP
                    ELSE NULL
                END
            WHERE id = :action_id AND startup_id = :startup_id
            RETURNING
                id, startup_id, created_by_user_id, title, description,
                related_pillar, status, source, source_ref,
                created_at, updated_at, completed_at
        """), {"new_status": new_status, "action_id": action_id, "startup_id": startup_id})

        row = result.mappings().first()
        return dict(row) if row is not None else None


FOUNDER_UPDATE_TYPES = (
    "customer", "revenue", "product", "team", "fundraising",
    "partnership", "validation", "operations", "other",
)
MILESTONE_STATUSES = ("planned", "in_progress", "achieved", "cancelled")

FOUNDER_UPDATE_COLUMNS = """
    id, startup_id, created_by_user_id, update_type, title, description,
    related_pillar, metric_name, metric_value, metric_unit,
    occurred_at, created_at, updated_at
"""

MILESTONE_COLUMNS = """
    id, startup_id, created_by_user_id, title, description,
    related_pillar, status, target_date, completed_at,
    created_at, updated_at
"""

# ---------------------------------------------------------------------------
# Phase 7.4 -- Founder Evidence + Milestones V1. Two dedicated, purely
# additive tables -- founder_updates and startup_milestones -- neither
# ever read by, written by, or joined into anything in the scoring/
# methodology path (analyses, startup_intelligence_score, PillarAnalysis,
# VPS, calibration). Both hold FOUNDER-REPORTED operational record only,
# same "workflow state, never evidence, never a score" boundary
# founder_actions established in Phase 7.3 -- see this section's own
# tests (test_founder_updates.py, test_startup_milestones.py) for the
# code-level audit.
#
# Distinct from app/models/evidence.py's Evidence model on purpose: that
# Evidence is CANONICAL pillar-analysis evidence (LLM-extracted, embedded
# in PillarAnalysis.evidence, assessed against Public/Inferred/Private
# rules) -- a completely different epistemic standard from "a founder
# typed a sentence into a form." founder_updates rows are never inserted
# into methodology.evidence, and no function in this file ever performs
# that conversion. A founder update becomes part of canonical evidence
# only if the founder separately, deliberately re-analyzes and mentions
# it in what they submit -- exactly like any other self-reported fact
# fed into the existing pipeline, no different or more privileged than
# before this phase existed.
#
# Shared per-startup, not per-member (same Part 11 decision Phase 7.3
# made for founder_actions): every function below is scoped by
# startup_id alone -- created_by_user_id is attribution only.
# ---------------------------------------------------------------------------

def create_founder_updates_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS founder_updates (
                id SERIAL PRIMARY KEY,
                startup_id INTEGER NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
                created_by_user_id TEXT NOT NULL REFERENCES users(id),
                update_type TEXT NOT NULL CHECK (update_type IN (
                    'customer', 'revenue', 'product', 'team', 'fundraising',
                    'partnership', 'validation', 'operations', 'other'
                )),
                title TEXT NOT NULL,
                description TEXT,
                related_pillar TEXT,
                -- Optional structured metric (Part 9) -- deliberately just
                -- three plain nullable columns, no metrics platform, no
                -- separate metrics table, no charting. All three are
                -- either all present or all absent; enforced at the API
                -- layer (CreateFounderUpdateRequest), not here, matching
                -- this file's existing convention that DB functions
                -- implement writes, not validation.
                metric_name TEXT,
                metric_value NUMERIC,
                metric_unit TEXT,
                occurred_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

    print("founder_updates table created successfully.")


def list_founder_updates_for_startup(startup_id: int):
    """Every update for this startup, regardless of who recorded it --
    newest-first by occurred_at (the founder-chosen "when did this
    happen" date, not necessarily when the row was inserted), which is
    what a Recent Updates timeline actually wants. Authorization
    (RequireStartupMember) is enforced entirely at the API layer, same
    convention as list_founder_actions_for_startup()."""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {FOUNDER_UPDATE_COLUMNS}
            FROM founder_updates
            WHERE startup_id = :startup_id
            ORDER BY occurred_at DESC, created_at DESC
        """), {"startup_id": startup_id})

        return [dict(row) for row in result.mappings().all()]


def create_founder_update(
    startup_id: int,
    created_by_user_id: str,
    update_type: str,
    title: str,
    description: str | None,
    related_pillar: str | None,
    occurred_at,
    metric_name: str | None = None,
    metric_value: float | None = None,
    metric_unit: str | None = None,
):
    """No deduplication of any kind -- unlike founder_actions' SIE-
    recommendation dedup, every founder update is a genuinely distinct
    reported event even if the text happens to repeat (a founder may
    legitimately report "Signed a new customer" multiple times)."""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            INSERT INTO founder_updates (
                startup_id, created_by_user_id, update_type, title,
                description, related_pillar, metric_name, metric_value,
                metric_unit, occurred_at
            )
            VALUES (
                :startup_id, :created_by_user_id, :update_type, :title,
                :description, :related_pillar, :metric_name, :metric_value,
                :metric_unit, :occurred_at
            )
            RETURNING {FOUNDER_UPDATE_COLUMNS}
        """), {
            "startup_id": startup_id,
            "created_by_user_id": created_by_user_id,
            "update_type": update_type,
            "title": title,
            "description": description,
            "related_pillar": related_pillar,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "metric_unit": metric_unit,
            "occurred_at": occurred_at,
        })

        return dict(result.mappings().first())


def update_founder_update(
    startup_id: int,
    update_id: int,
    update_type: str,
    title: str,
    description: str | None,
    related_pillar: str | None,
    occurred_at,
    metric_name: str | None = None,
    metric_value: float | None = None,
    metric_unit: str | None = None,
):
    """Full-field correction, not a partial patch -- same shape as
    update_modeled_venture_for_user()'s own precedent (every editable
    field is supplied on every call, avoiding the ambiguity of "field
    absent" vs. "field explicitly cleared"). Returns None if this
    update_id doesn't exist for this exact startup_id -- same
    non-leaking, WHERE-clause-scoped discipline as
    update_founder_action_status()."""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            UPDATE founder_updates
            SET update_type = :update_type,
                title = :title,
                description = :description,
                related_pillar = :related_pillar,
                metric_name = :metric_name,
                metric_value = :metric_value,
                metric_unit = :metric_unit,
                occurred_at = :occurred_at,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :update_id AND startup_id = :startup_id
            RETURNING {FOUNDER_UPDATE_COLUMNS}
        """), {
            "update_type": update_type,
            "title": title,
            "description": description,
            "related_pillar": related_pillar,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "metric_unit": metric_unit,
            "occurred_at": occurred_at,
            "update_id": update_id,
            "startup_id": startup_id,
        })

        row = result.mappings().first()
        return dict(row) if row is not None else None


def create_startup_milestones_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS startup_milestones (
                id SERIAL PRIMARY KEY,
                startup_id INTEGER NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
                created_by_user_id TEXT NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                description TEXT,
                related_pillar TEXT,
                status TEXT NOT NULL DEFAULT 'planned'
                    CHECK (status IN ('planned', 'in_progress', 'achieved', 'cancelled')),
                target_date DATE,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

    print("startup_milestones table created successfully.")


def list_startup_milestones_for_startup(startup_id: int):
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {MILESTONE_COLUMNS}
            FROM startup_milestones
            WHERE startup_id = :startup_id
            ORDER BY created_at ASC
        """), {"startup_id": startup_id})

        return [dict(row) for row in result.mappings().all()]


def create_startup_milestone(
    startup_id: int,
    created_by_user_id: str,
    title: str,
    description: str | None,
    related_pillar: str | None,
    target_date,
):
    """New milestones always start 'planned' -- no other status is ever
    accepted at creation time, matching create_founder_action()'s own
    "status always starts at the initial value" discipline."""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            INSERT INTO startup_milestones (
                startup_id, created_by_user_id, title, description,
                related_pillar, status, target_date
            )
            VALUES (
                :startup_id, :created_by_user_id, :title, :description,
                :related_pillar, 'planned', :target_date
            )
            RETURNING {MILESTONE_COLUMNS}
        """), {
            "startup_id": startup_id,
            "created_by_user_id": created_by_user_id,
            "title": title,
            "description": description,
            "related_pillar": related_pillar,
            "target_date": target_date,
        })

        return dict(result.mappings().first())


def update_startup_milestone_status(startup_id: int, milestone_id: int, new_status: str):
    """Same completed_at discipline as update_founder_action_status():
    set to NOW() only on a transition INTO 'achieved', cleared back to
    NULL on any transition away from it (the "reopen" case). Marking a
    milestone 'achieved' or 'cancelled' never touches analyses,
    methodology, or any *_score column -- see this section's own
    module-level comment and test_startup_milestones.py's static audit."""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            UPDATE startup_milestones
            SET status = :new_status,
                updated_at = CURRENT_TIMESTAMP,
                completed_at = CASE
                    WHEN :new_status = 'achieved' THEN CURRENT_TIMESTAMP
                    ELSE NULL
                END
            WHERE id = :milestone_id AND startup_id = :startup_id
            RETURNING {MILESTONE_COLUMNS}
        """), {"new_status": new_status, "milestone_id": milestone_id, "startup_id": startup_id})

        row = result.mappings().first()
        return dict(row) if row is not None else None


def create_saved_startups_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS saved_startups (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                startup_id INTEGER NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT saved_startups_user_startup_key UNIQUE (user_id, startup_id)
            )
        """))

    print("saved_startups table created successfully.")


# ---------------------------------------------------------------------------
# Saved Startups / Watchlist -- Phase 1. saved_startups is a pure
# relationship table (user_id, startup_id) -- see create_saved_startups_table()
# above. These four functions are the ONLY code that reads or writes it.
#
# Deliberately does NOT copy SPS, company_name, industry, stage, or any
# other intelligence field into saved_startups at save time -- a saved
# startup points at startups.id only, and get_saved_startups_for_user()
# below joins out to the LATEST canonical (methodology_version-matching)
# analysis for that startup_id every time it's called, so a user's
# watchlist always reflects current intelligence, never a stale snapshot
# frozen at save time. This is the same "join out to current state, don't
# copy" principle get_rankings()/search_analyses() already use for
# "latest analysis per startup" -- applied here across a relationship
# table instead of within analyses itself.
#
# None of these functions ever touch startup_memberships. Saving a
# startup is a bookmark, not a claim of ownership -- see the SIE Accounts
# & Ownership architecture design and get_or_create_user()'s own
# docstring for the same principle applied to authentication.
# ---------------------------------------------------------------------------

def save_startup_for_user(user_id: str, startup_id: int) -> bool:
    """
    Idempotent: ON CONFLICT (user_id, startup_id) DO NOTHING means saving
    an already-saved startup is a safe no-op, never a duplicate row and
    never an error. Returns True if a new row was created, False if the
    startup was already saved (both are success outcomes to the caller;
    see app/api.py's save endpoint).

    Raises ValueError for a startup_id that doesn't exist in startups --
    saved_startups.startup_id has a real FK constraint, so this always
    fails cleanly (never a half-written row) on an invalid id; the FK
    violation is caught here and translated into a clean, callable-facing
    error rather than leaking a raw IntegrityError/psycopg2 exception up
    to app/api.py.
    """
    try:
        with engine.begin() as connection:
            result = connection.execute(text("""
                INSERT INTO saved_startups (user_id, startup_id)
                VALUES (:user_id, :startup_id)
                ON CONFLICT (user_id, startup_id) DO NOTHING
            """), {"user_id": user_id, "startup_id": startup_id})

            return result.rowcount > 0
    except IntegrityError as error:
        raise ValueError(f"Startup {startup_id} does not exist") from error


def unsave_startup_for_user(user_id: str, startup_id: int) -> bool:
    """
    Idempotent: deleting a row that isn't there deletes zero rows, not an
    error -- unsaving an already-unsaved (or never-saved) startup is
    always safe. Returns True if a row was actually removed, False if
    there was nothing to remove.
    """
    with engine.begin() as connection:
        result = connection.execute(text("""
            DELETE FROM saved_startups
            WHERE user_id = :user_id AND startup_id = :startup_id
        """), {"user_id": user_id, "startup_id": startup_id})

        return result.rowcount > 0


def is_startup_saved_by_user(user_id: str, startup_id: int) -> bool:
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT 1 FROM saved_startups
            WHERE user_id = :user_id AND startup_id = :startup_id
        """), {"user_id": user_id, "startup_id": startup_id})

        return result.first() is not None


def get_saved_startups_for_user(user_id: str, viewer_is_admin: bool = False):
    """
    One row per startup this user has saved, most-recently-saved first.
    Each row's intelligence fields (industry, stage, overall_score,
    latest_analysis_at) come from a LEFT JOIN LATERAL that independently
    resolves that startup's own latest canonical (methodology_version ==
    current) analysis via analyses.startup_id -- the real FK written by
    get_or_create_startup()/save_analysis(), not a re-derivation via
    company_name normalization the way get_rankings() still does (see
    that function's own docstring for why it hasn't been migrated to the
    FK) -- so this always reflects current intelligence, never a snapshot
    from whenever the startup was saved.

    LEFT (not INNER) JOIN LATERAL deliberately: a startup a user saved
    can, in principle, currently have zero canonical analyses (e.g. its
    only analysis predates Methodology v2, or predates the write path and
    was never backfilled with a matching canonical row). That startup
    still appears in the list -- with null intelligence fields -- rather
    than silently vanishing from a list the user explicitly built. No
    field here is ever fabricated to fill the gap.

    Portfolio Release Task 3B: saving/bookmarking a startup is NOT
    ownership and must not grant report access (approved decision, item
    5) -- the LATERAL subquery below is scoped by
    _analysis_visibility_clause() to THIS user (the viewer, who is also
    `user_id` here -- this endpoint only ever lists the caller's own saved
    list), so a startup someone else privately analyzed more recently than
    any analysis the viewer can see now correctly falls back to the
    viewer's own latest AUTHORIZED analysis (or null intelligence fields,
    same as the "zero canonical analyses" case above) instead of silently
    surfacing another user's private score/industry/stage. Before this
    fix, the LATERAL subquery had no visibility filter at all and always
    picked the platform-wide latest analysis regardless of who submitted
    it -- a real, separate leak from the one GET /startup/{name} closes.
    """
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT
                ss.startup_id AS startup_id,
                ss.created_at AS saved_at,
                startups.canonical_name AS company_name,
                latest.industry AS industry,
                latest.stage AS stage,
                latest.overall_score AS overall_score,
                latest.created_at AS latest_analysis_at
            FROM saved_startups ss
            JOIN startups ON startups.id = ss.startup_id
            LEFT JOIN LATERAL (
                SELECT
                    industry,
                    stage,
                    (methodology->>'startup_intelligence_score')::float AS overall_score,
                    created_at
                FROM analyses
                WHERE analyses.startup_id = ss.startup_id
                  AND methodology IS NOT NULL
                  AND methodology->'analysis_context'->>'methodology_version' = :methodology_version
                  AND {_analysis_visibility_clause()}
                ORDER BY created_at DESC, id DESC
                LIMIT 1
            ) latest ON true
            WHERE ss.user_id = :user_id
            ORDER BY ss.created_at DESC
        """), {
            "user_id": user_id,
            "methodology_version": METHODOLOGY_VERSION,
            "viewer_user_id": user_id,
            "viewer_is_admin": viewer_is_admin,
        })

        rows = result.mappings().all()

    return [dict(row) for row in rows]


def backfill_startup_ids():
    """
    One-time (but safely re-runnable) data migration: creates exactly one
    startups row per LOWER(TRIM(company_name)) identity already implicitly
    used as "startup identity" by every canonical read query in this file
    -- the EXACT same normalization rule those queries already use, not a
    new or improved one, so this migration cannot silently redefine what
    "the same startup" means. Rows with no company_name (NULL, or blank
    after trim) are skipped entirely and get no startup_id, exactly as
    those same canonical queries already exclude them from grouping (see
    search_analyses()/get_rankings()'s own "company_name IS NOT NULL AND
    TRIM(company_name) <> ''" filters) -- they are never merged into one
    fake shared identity.

    canonical_name is taken from the most recent matching analysis
    (ORDER BY created_at DESC, id DESC), the same "latest wins" tie-break
    get_rankings()/get_startup_by_name() already use for "which row
    represents this startup right now".

    Idempotent: the UNIQUE constraint on startups.normalized_name makes
    the insert step a safe no-op for identities already present (ON
    CONFLICT DO NOTHING); the update step only ever touches
    analyses.startup_id IS NULL rows, so re-running this after some rows
    are already backfilled changes nothing further and is always safe to
    call at every startup alongside the other migrations.

    Creates ONLY startups rows and analyses.startup_id values -- never
    touches startup_memberships or saved_startups. Every startup created
    here is unowned by construction; no ownership is fabricated for
    historical analyses.
    """
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO startups (canonical_name, normalized_name)
            SELECT DISTINCT ON (LOWER(TRIM(company_name)))
                company_name,
                LOWER(TRIM(company_name))
            FROM analyses
            WHERE company_name IS NOT NULL
              AND TRIM(company_name) <> ''
            ORDER BY LOWER(TRIM(company_name)), created_at DESC, id DESC
            ON CONFLICT (normalized_name) DO NOTHING
        """))

        result = connection.execute(text("""
            UPDATE analyses
            SET startup_id = startups.id
            FROM startups
            WHERE analyses.startup_id IS NULL
              AND analyses.company_name IS NOT NULL
              AND TRIM(analyses.company_name) <> ''
              AND LOWER(TRIM(analyses.company_name)) = startups.normalized_name
        """))

    print(f"startup backfill complete: {result.rowcount} analyses linked to startups")


def save_score_history(
    analysis_id,
    company_name,
    industry,
    stage,
    business_model,
    market_score,
    team_score,
    product_score,
    competition_score,
    traction_score,
    financial_score,
    overall_score,
    readiness_score
):
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO score_history (
                analysis_id,
                company_name,
                industry,
                stage,
                business_model,
                market_score,
                team_score,
                product_score,
                competition_score,
                traction_score,
                financial_score,
                overall_score,
                readiness_score
            )
            VALUES (
                :analysis_id,
                :company_name,
                :industry,
                :stage,
                :business_model,
                :market_score,
                :team_score,
                :product_score,
                :competition_score,
                :traction_score,
                :financial_score,
                :overall_score,
                :readiness_score
            )
        """), {
            "analysis_id": analysis_id,
            "company_name": company_name,
            "industry": industry,
            "stage": stage,
            "business_model": business_model,
            "market_score": market_score,
            "team_score": team_score,
            "product_score": product_score,
            "competition_score": competition_score,
            "traction_score": traction_score,
            "financial_score": financial_score,
            "overall_score": overall_score,
            "readiness_score": readiness_score,
        })

    print("Score history saved successfully.")


def get_score_history(company_name: str, viewer_user_id: str, viewer_is_admin: bool):
    """
    Portfolio Release Task 3B: score_history has no ownership of its own
    (it's legacy, dead-write-path data -- nothing has written to it since
    Phase 10.1B, see app/api.py's own comment on save_score_history()) but
    every row's analysis_id references the analyses row it came from, so
    visibility is resolved via a JOIN to that row's submitted_by_user_id/
    startup_id (an INNER JOIN -- a score_history row whose analysis_id is
    NULL, or whose analyses row no longer exists, has no owner to check
    and is simply excluded, never shown to anyone including an admin; this
    is a known, accepted limitation of very old rows, not a new gap this
    task introduces).
    """
    search_term = f"%{company_name}%"

    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT
                sh.id AS id,
                sh.analysis_id AS analysis_id,
                sh.company_name AS company_name,
                sh.industry AS industry,
                sh.stage AS stage,
                sh.business_model AS business_model,
                sh.market_score AS market_score,
                sh.team_score AS team_score,
                sh.product_score AS product_score,
                sh.competition_score AS competition_score,
                sh.traction_score AS traction_score,
                sh.financial_score AS financial_score,
                sh.overall_score AS overall_score,
                sh.readiness_score AS readiness_score,
                sh.created_at AS created_at
            FROM score_history sh
            JOIN analyses a ON a.id = sh.analysis_id
            WHERE sh.company_name ILIKE :search_term
              AND {_analysis_visibility_clause("a")}
            ORDER BY sh.created_at ASC
        """), {
            "search_term": search_term,
            "viewer_user_id": viewer_user_id,
            "viewer_is_admin": viewer_is_admin,
        })

        rows = result.mappings().all()

    return [dict(row) for row in rows]


def get_startup_trends(company_name: str, viewer_user_id: str, viewer_is_admin: bool):
    history = get_score_history(company_name, viewer_user_id, viewer_is_admin)

    if len(history) == 0:
        return {
            "error": "No history found"
        }

    first = history[0]
    latest = history[-1]

    score_change = latest["overall_score"] - first["overall_score"]
    readiness_change = (
        latest["readiness_score"] -
        first["readiness_score"]
    )

    if score_change > 0:
        trend = "Improving"
    elif score_change < 0:
        trend = "Declining"
    else:
        trend = "Stable"

    return {
        "company_name": company_name,
        "first_score": first["overall_score"],
        "latest_score": latest["overall_score"],
        "score_change": score_change,
        "first_readiness": first["readiness_score"],
        "latest_readiness": latest["readiness_score"],
        "readiness_change": readiness_change,
        "trend": trend,
        "total_analyses": len(history)
    }


def get_or_create_startup(company_name, connection=None):
    """
    SIE Accounts & Ownership -- canonical Startup write path. Resolves
    company_name to its canonical startups.id, creating exactly one new
    startups row the first time this identity is ever seen.

    Uses the EXACT same normalization rule as backfill_startup_ids() and
    every canonical read query in this file (LOWER(TRIM(company_name)))
    -- not a new or improved one, so a new analysis can never resolve to
    a different notion of "the same startup" than the migration already
    established.

    Concurrency-safe: relies on the UNIQUE constraint on
    startups.normalized_name via INSERT ... ON CONFLICT DO NOTHING,
    followed by a SELECT for the (now certainly present) row's id. This
    is correct regardless of which of two concurrent callers' INSERT
    actually wins the race -- Postgres serializes concurrent inserts
    against the same unique key (the loser waits briefly rather than
    racing incorrectly), so by the time the SELECT below runs, the
    winning row is guaranteed visible in this transaction.

    Never modifies an existing startup's canonical_name: ON CONFLICT DO
    NOTHING never updates the existing row, so a later analysis that
    happens to use different casing/whitespace for an already-known
    company reuses the existing row exactly as first stored -- only the
    very first analysis for a given normalized identity sets
    canonical_name.

    Creates ONLY a startups row -- never touches startup_memberships or
    saved_startups, and never associates a user. Ownership is a
    completely separate concept from analysis (see the SIE Accounts &
    Ownership architecture design); this function's only job is identity
    resolution.

    Pass an existing SQLAlchemy Connection (already inside a transaction,
    e.g. save_analysis()'s own) via `connection` to keep Startup
    resolution and the Analysis insert atomic -- if that transaction
    later rolls back for any reason, a Startup created here rolls back
    with it, so a failed analysis write can never leave behind an orphan
    Startup. If no connection is passed, this opens and commits its own
    short transaction (useful for standalone/test callers).

    Returns None for a null/empty company_name -- exactly matching the
    existing exclusion already used everywhere else (search_analyses(),
    get_rankings(), backfill_startup_ids()) -- a nameless analysis is
    never merged into a fake shared identity, and gets no startup_id.
    """
    normalized_name = company_name.strip().lower() if company_name else ""

    if not normalized_name:
        return None

    def _resolve(conn):
        conn.execute(text("""
            INSERT INTO startups (canonical_name, normalized_name)
            VALUES (:canonical_name, :normalized_name)
            ON CONFLICT (normalized_name) DO NOTHING
        """), {
            "canonical_name": company_name.strip(),
            "normalized_name": normalized_name,
        })

        return conn.execute(text("""
            SELECT id FROM startups WHERE normalized_name = :normalized_name
        """), {"normalized_name": normalized_name}).scalar()

    if connection is not None:
        return _resolve(connection)

    with engine.begin() as new_connection:
        return _resolve(new_connection)


def save_analysis(
    company_text,
    summary,
    risk_analysis,
    competitor_analysis,
    memo,
    structured_analysis,
    investment_score,
    founder_analysis,
    market_analysis,
    sources,
    traction_analysis,
    market_score,
    team_score,
    product_score,
    competition_score,
    traction_score,
    financial_score,
    overall_score,
    recommendation,
    readiness_score,
    readiness_summary,
    methodology,
    startup_id=None,
    submitted_by_user_id=None,
):
    """
    Portfolio Release Task 3B -- Secure Analysis Visibility. submitted_by_user_id
    is the verified Clerk user_id of whoever is submitting THIS analysis --
    POST /analyze passes current_user.user_id here for every analysis it
    creates (not just founder-targeted ones), now that the column exists
    (see add_analysis_submitted_by_column()). Optional and defaults to
    None only so this function's other, non-HTTP callers (calibration,
    the reliability harness, tests) don't all need updating in the same
    change -- every real product path that creates an analysis has a
    verified user_id available and should pass it. A None value here
    produces exactly the same "historical NULL-owner" row the pre-Task-3B
    schema always produced, visible only to an approved startup member or
    an admin (see app/auth.py::user_can_view_analysis()) -- never treated
    as "public" or "nobody's problem."

    Phase 7.2.1 -- Deterministic Founder Re-analysis: startup_id is an
    OPTIONAL authoritative override, meant only for a caller that has
    ALREADY verified the current user is a real member of that exact
    startup (POST /analyze's own use of require_startup_member() before
    ever calling this function) -- save_analysis() itself does not check
    authorization, matching this file's existing convention that DB
    functions implement queries/writes, not access control.

    When startup_id is None (every existing caller, and /analyze's own
    normal/public path): behavior is completely unchanged --
    get_or_create_startup() resolves identity from the extracted
    company_name exactly as before.

    When startup_id is supplied: get_or_create_startup() is never
    called, so this analysis can never spawn a second startups row no
    matter what company name this particular analysis happened to
    extract ("Linear" vs "Linear Inc." vs "Linear App" all resolve to the
    SAME startup_id here, deterministically, because none of them are
    ever consulted for identity). The given id is looked up (never
    blindly trusted) inside this same transaction; a nonexistent id
    raises ValueError and nothing is written -- same
    "raise ValueError for a startup_id that doesn't exist" contract
    save_startup_for_user() already uses, so callers already know this
    shape.

    Per the Phase 7.2.1 design decision on identity vs. display: the
    row's `company_name` column (the field other canonical read paths
    key off, e.g. search_analyses()'s DISTINCT ON) is set to the
    startup's EXISTING canonical_name, not whatever this analysis
    happened to extract -- this is what actually prevents identity
    drift. The LLM-extracted name is NOT discarded, though: it still
    lives in `methodology`/`structured_analysis` (the JSONB blobs) via
    the analysis_context/company_name this function already receives one
    layer up, in `structured_analysis` -- callers may still show it,
    it simply never overrides canonical_name here.
    """
    company_name = None
    industry = None
    stage = None
    business_model = None

    if isinstance(structured_analysis, dict):
        company_name = structured_analysis.get("company_name")
        industry = structured_analysis.get("industry")
        stage = structured_analysis.get("stage")
        business_model = structured_analysis.get("business_model")

    created_at = datetime.now().isoformat()

    with engine.begin() as connection:
        if startup_id is not None:
            # Authoritative path (Phase 7.2.1): identity is already
            # decided by the caller's verified startup_id -- resolve the
            # real row directly, never via get_or_create_startup()'s
            # name-matching. The FK constraint on analyses.startup_id
            # would itself reject a nonexistent id, but failing here with
            # a clean ValueError (inside this same transaction, before
            # any INSERT is attempted) is the same "clean application
            # error, never a raw IntegrityError" discipline
            # save_startup_for_user() already established.
            startup_row = connection.execute(text("""
                SELECT id, canonical_name FROM startups WHERE id = :startup_id
            """), {"startup_id": startup_id}).mappings().first()

            if startup_row is None:
                raise ValueError(f"Startup {startup_id} does not exist")

            resolved_startup_id = startup_row["id"]
            # Overrides the extracted company_name for the DB column
            # only -- see this function's own docstring for why this is
            # the one thing that actually needs to stay pinned to the
            # canonical identity, while methodology/structured_analysis
            # (untouched below) may still carry whatever this analysis
            # extracted.
            company_name = startup_row["canonical_name"]
        else:
            # SIE Accounts & Ownership -- canonical Startup write path,
            # centralized here so every existing and future
            # save_analysis() caller gets it automatically (no
            # per-endpoint duplication). Resolved inside this same
            # transaction/connection so Startup resolution and the
            # Analysis insert commit or roll back together -- a failed
            # Analysis insert can never leave behind an orphan Startup.
            # See get_or_create_startup()'s own docstring for the
            # normalization/concurrency/ownership guarantees.
            resolved_startup_id = get_or_create_startup(company_name, connection=connection)

        result = connection.execute(text("""
            INSERT INTO analyses (
                company_name,
                startup_id,
                submitted_by_user_id,
                company_text,
                summary,
                risk_analysis,
                competitor_analysis,
                memo,
                created_at,
                structured_analysis,
                investment_score,
                founder_analysis,
                market_analysis,
                sources,
                traction_analysis,
                methodology,
                market_score,
                team_score,
                product_score,
                competition_score,
                traction_score,
                financial_score,
                overall_score,
                recommendation,
                readiness_score,
                readiness_summary,
                industry,
                stage,
                business_model
            )
            VALUES (
                :company_name,
                :startup_id,
                :submitted_by_user_id,
                :company_text,
                :summary,
                :risk_analysis,
                :competitor_analysis,
                :memo,
                :created_at,
                :structured_analysis,
                :investment_score,
                :founder_analysis,
                :market_analysis,
                :sources,
                :traction_analysis,
                CAST(:methodology AS JSONB),
                :market_score,
                :team_score,
                :product_score,
                :competition_score,
                :traction_score,
                :financial_score,
                :overall_score,
                :recommendation,
                :readiness_score,
                :readiness_summary,
                :industry,
                :stage,
                :business_model

            )
            RETURNING id
        """), {
            "company_name": company_name,
            "startup_id": resolved_startup_id,
            "submitted_by_user_id": submitted_by_user_id,
            "company_text": company_text,
            "summary": summary,
            "risk_analysis": risk_analysis,
            "competitor_analysis": competitor_analysis,
            "memo": memo,
            "created_at": created_at,
            "structured_analysis": json.dumps(structured_analysis),
            "investment_score": json.dumps(investment_score),
            "founder_analysis": json.dumps(founder_analysis),
            "market_analysis": json.dumps(market_analysis),
            "sources": json.dumps(sources),
            "traction_analysis": json.dumps(traction_analysis),
            "methodology": json.dumps(methodology),
            "market_score": market_score,
            "team_score": team_score,
            "product_score": product_score,
            "competition_score": competition_score,
            "traction_score": traction_score,
            "financial_score": financial_score,
            "overall_score": overall_score,
            "recommendation": recommendation,
            "readiness_score": readiness_score,
            "readiness_summary": readiness_summary,
            "industry": industry,
            "stage": stage,
            "business_model": business_model
        })
        analysis_id = result.scalar()
    return analysis_id

        

def search_analyses(query: str, viewer_user_id: str, viewer_is_admin: bool):
    """
    P0 Product Trust Cleanup: search results must represent unique
    startups backed by their latest CANONICAL Methodology v2 analysis --
    the same "methodology IS NOT NULL and methodology_version matches the
    current constant" rule as get_rankings(), so a legacy (pre-v2 or
    methodology-null) analysis can never surface as a current canonical
    startup. Search still matches broadly across the same text columns as
    before (company_text, summary, risk_analysis, etc.) -- only the
    candidate pool (canonical rows only) and the returned score's source
    (methodology.startup_intelligence_score, not the legacy overall_score
    column) have changed; the match behavior and result shape the frontend
    consumes (company_name, summary, overall_score) are unchanged.

    Portfolio Release Task 3B: scoped by _analysis_visibility_clause(),
    applied inside the WHERE that feeds DISTINCT ON -- so "the latest
    canonical result per company" means the caller's own latest
    authorized one, not the platform's globally-latest analysis of that
    company regardless of who submitted it. This also closes the "does
    company_text contain phrase X" probing risk noted in the read-only
    audit: full-text matching against company_text/summary/etc. now only
    ever runs against rows this viewer is already authorized to read in
    full, so a match can never reveal more than the viewer could already
    see by opening that startup's own profile.
    """
    search_term = f"%{query}%"

    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT
                company_name,
                summary,
                overall_score
            FROM (
                SELECT DISTINCT ON (LOWER(TRIM(company_name)))
                    company_name,
                    summary,
                    (methodology->>'startup_intelligence_score')::float AS overall_score,
                    created_at
                FROM analyses
                WHERE
                    methodology IS NOT NULL
                    AND methodology->'analysis_context'->>'methodology_version' = :methodology_version
                    AND company_name IS NOT NULL
                    AND TRIM(company_name) <> ''
                    AND {_analysis_visibility_clause()}
                    AND (
                        company_text ILIKE :search_term
                        OR company_name ILIKE :search_term
                        OR summary ILIKE :search_term
                        OR risk_analysis ILIKE :search_term
                        OR competitor_analysis ILIKE :search_term
                        OR memo ILIKE :search_term
                        OR structured_analysis ILIKE :search_term
                        OR investment_score ILIKE :search_term
                        OR founder_analysis ILIKE :search_term
                        OR market_analysis ILIKE :search_term
                        OR sources ILIKE :search_term
                        OR traction_analysis ILIKE :search_term
                    )
                ORDER BY
                    LOWER(TRIM(company_name)),
                    created_at DESC,
                    id DESC
            ) latest_canonical_results
            ORDER BY created_at DESC
        """), {
            "search_term": search_term,
            "methodology_version": METHODOLOGY_VERSION,
            "viewer_user_id": viewer_user_id,
            "viewer_is_admin": viewer_is_admin,
        })

        rows = result.mappings().all()

    return [dict(row) for row in rows]

        
    
def parse_structured_analysis(row):
    analysis = dict(row)

    json_fields = [
        "structured_analysis",
        "investment_score",
        "founder_analysis",
        "market_analysis",
        "sources",
        "traction_analysis"
        "methodology",
    ]

    for field in json_fields:

        value = analysis.get(field)

    if isinstance(value, str):
        try:
            analysis[field] = json.loads(value)
        except json.JSONDecodeError:
            pass

    return analysis

def get_analyses():
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT * FROM analyses
            ORDER BY id DESC
        """))

        rows = result.mappings().all()

    return [parse_structured_analysis(row) for row in rows]

def get_analysis_by_id(analysis_id):
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT * FROM analyses
            WHERE id = :analysis_id
        """), {
            "analysis_id": analysis_id
        })

        row = result.mappings().first()

    if row is None:
        return None

    return parse_structured_analysis(row)


def get_startup_by_name(company_name: str, viewer_user_id: str, viewer_is_admin: bool):
    """
    Portfolio Release Task 3B -- Secure Analysis Visibility. viewer_user_id/
    viewer_is_admin are REQUIRED (no default) -- every caller of this
    function must resolve them from a verified, authenticated identity
    first (this function has no way to check that itself). The main
    analyses query below is now scoped by _analysis_visibility_clause(),
    applied BEFORE `ORDER BY ... LIMIT 1` picks "the latest" -- so a
    viewer who is authorized to see SOME but not ALL analyses of a given
    company name sees their own latest authorized one, never a stranger's
    newer, inaccessible analysis silently taking priority (see that
    function's own docstring). The `startups`-only fallback below (a
    company that exists but has no analysis at all) carries zero analysis
    content -- no methodology, no text -- so it stays visible to any
    authenticated caller regardless of ownership; there is nothing
    confidential in "this company exists and hasn't been analyzed yet."

    Note: the `id` field returned here is analyses.id (the specific
    analysis row), not startups.id -- that naming predates the canonical
    Startup entity and is left alone since existing consumers
    (SPS History, etc.) already depend on it meaning "this analysis".

    Saved Startups (Watchlist Phase 1) added `startup_id` (analyses.
    startup_id, the canonical Startup FK -- see get_or_create_startup())
    alongside it, additively, so the frontend Save control has something
    stable to save without repurposing `id` or requiring a second request.
    A NULL startup_id here (only possible for pre-write-path historical
    rows that predate both the backfill and this column) means the
    frontend has nothing valid to save and hides the control rather than
    guessing.

    Phase 37E -- Company Lifecycle + Public Identity Convergence, Section
    6. Before this phase, a company with a real `startups` row (e.g. a
    freshly graduated one, per Phase 31) but zero analyses fell straight
    through to `None` here -- the public route then rendered "Startup not
    found," identical to a company that doesn't exist at all. That was
    dishonest: the company DOES exist, it just hasn't been evaluated yet.
    This function now distinguishes the two: if no qualifying analysis
    exists, it falls back to a direct `startups` lookup by
    `normalized_name` (the same `LOWER(TRIM(...))` normalization the
    analyses query already used, now via the pre-computed, UNIQUE-
    constrained column instead of a live string transform -- see
    `startups`'s own schema comment; the UNIQUE constraint is also why
    this fallback can never return more than one row, so no new collision
    risk is introduced). `has_analysis` tells the caller which case this
    is; `methodology` is None only in the fallback case -- never a
    fabricated SPS/pillar breakdown for a company that hasn't been
    evaluated (Section 6's own explicit requirement).
    """
    normalized_company_name = company_name.strip()

    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT
                id,
                startup_id,
                created_at,
                methodology,
                company_name AS canonical_name
            FROM analyses
            WHERE LOWER(TRIM(company_name)) =
                  LOWER(TRIM(:company_name))
              AND methodology IS NOT NULL
              AND {_analysis_visibility_clause()}
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """), {
            "company_name": normalized_company_name,
            "viewer_user_id": viewer_user_id,
            "viewer_is_admin": viewer_is_admin,
        })

        row = result.mappings().first()

        if row is None:
            startup_row = connection.execute(text("""
                SELECT id, canonical_name, created_at
                FROM startups
                WHERE normalized_name = LOWER(TRIM(:company_name))
            """), {
                "company_name": normalized_company_name
            }).mappings().first()

            if startup_row is None:
                return None

            return {
                "id": startup_row["id"],
                "startup_id": startup_row["id"],
                "canonical_name": startup_row["canonical_name"],
                "created_at": startup_row["created_at"],
                "methodology": None,
                "has_analysis": False,
            }

    startup = dict(row)

    if isinstance(startup["methodology"], str):
        startup["methodology"] = json.loads(
            startup["methodology"]
        )

    startup["has_analysis"] = True

    return startup


def get_sps_history(company_name: str, viewer_user_id: str, viewer_is_admin: bool):
    """
    Canonical SPS history for a company, sourced from the methodology
    JSONB rather than the legacy score_history table.

    score_history stores overall_score as INTEGER (lossy vs. the real
    float score) and, for every company analyzed before canonical
    methodology persistence existed, spans multiple incompatible
    revisions of the scoring algorithm. Filtering to
    methodology IS NOT NULL here naturally excludes all of that
    pre-canonical data, at the cost of most companies currently having
    zero or one point until more analyses are run under the current
    methodology.

    Portfolio Release Task 3B: scoped by _analysis_visibility_clause() --
    a viewer's SPS-history line only ever plots points from analyses of
    this company THEY are authorized to see (their own, or an approved
    member's), never every analysis anyone has ever submitted for a
    company with this name. viewer_user_id/viewer_is_admin are required,
    same contract as get_startup_by_name().
    """
    normalized_company_name = company_name.strip()

    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT
                id,
                created_at,
                methodology->>'startup_intelligence_score' AS sps
            FROM analyses
            WHERE LOWER(TRIM(company_name)) =
                  LOWER(TRIM(:company_name))
              AND methodology IS NOT NULL
              AND {_analysis_visibility_clause()}
            ORDER BY created_at ASC, id ASC
        """), {
            "company_name": normalized_company_name,
            "viewer_user_id": viewer_user_id,
            "viewer_is_admin": viewer_is_admin,
        })

        rows = result.mappings().all()

    return [
        {
            "analysis_id": row["id"],
            "created_at": row["created_at"],
            "startup_intelligence_score": (
                float(row["sps"]) if row["sps"] is not None else None
            ),
        }
        for row in rows
    ]


def delete_analysis(analysis_id: int):
    with engine.begin() as connection:
        result = connection.execute(text("""
            DELETE FROM analyses
            WHERE id = :analysis_id
        """), {
            "analysis_id": analysis_id
        })

        deleted_count = result.rowcount

    return deleted_count



def update_analysis(
    analysis_id: int,
    company_text: str,
    summary: str,
    risk_analysis: str,
    competitor_analysis: str,
    memo: str,
    structured_analysis: dict,
    investment_score: str,
    founder_analysis: str,
    market_analysis: str,
    sources: str,
    traction_analysis: str
):
    with engine.begin() as connection:
        result = connection.execute(text("""
            UPDATE analyses
            SET company_text = :company_text,
                summary = :summary,
                risk_analysis = :risk_analysis,
                competitor_analysis = :competitor_analysis,
                memo = :memo,
                structured_analysis = :structured_analysis,
                investment_score = :investment_score,
                founder_analysis = :founder_analysis,
                market_analysis = :market_analysis,
                sources = :sources,
                traction_analysis = :traction_analysis
            WHERE id = :analysis_id
        """), {
            "analysis_id": analysis_id,
            "company_text": company_text,
            "summary": summary,
            "risk_analysis": risk_analysis,
            "competitor_analysis": competitor_analysis,
            "memo": memo,
            "structured_analysis": json.dumps(structured_analysis),
            "investment_score": json.dumps(investment_score),
            "founder_analysis": json.dumps(founder_analysis),
            "market_analysis": json.dumps(market_analysis),
            "sources": json.dumps(sources),
            "traction_analysis": json.dumps(traction_analysis),
        })

        updated_count = result.rowcount

    return updated_count

def get_analytics(viewer_user_id: str, viewer_is_admin: bool):
    """
    Canonical Dashboard MVP: sourced from the exact same canonical
    population get_rankings() computes (latest Methodology v2 analysis per
    normalized startup) -- not COUNT(*)/AVG(...) over the full `analyses`
    table, which is still >90% legacy, pre-v2 rows. "Tracked startups" and
    "average score" now honestly mean "canonical startups" and "average
    canonical SPS."

    Per-pillar legacy averages (market/team/product/competition/traction/
    financial) and average_readiness_score are dropped entirely rather than
    carried forward unused: nothing in the frontend consumes them, they
    were sourced from the same legacy columns, and readiness_score
    specifically has no defined numeric scale at all (see the P0 Product
    Trust Cleanup report) -- inventing a "canonical" version of either
    would mean fabricating a metric, not just re-sourcing one. The
    redundant top_startups sub-list is dropped too: get_top_startups()
    already serves that, from the same canonical population, independently.

    Portfolio Release Task 3B: inherits get_rankings()'s viewer scoping --
    "total tracked startups"/"average score" now describe this viewer's
    own authorized population, not the whole platform's.
    """
    rankings = get_rankings(viewer_user_id, viewer_is_admin)

    scores = [
        row["overall_score"]
        for row in rankings
        if row["overall_score"] is not None
    ]

    return {
        "total_startups": len(rankings),
        "average_overall_score": (
            round(sum(scores) / len(scores), 2) if scores else None
        ),
    }


def get_sps_v3_analytics():
    """
    Phase 10.9, Part 23. Deliberately separate from get_analytics() above
    rather than folded into it -- V3 is an additive, feature-flagged,
    parallel assessment (see app/ai/sps_v3_adapter.py), not a replacement
    for the canonical V2.1 population get_analytics() describes, so
    mixing the two into one response would misrepresent what's actually
    being counted.

    "Latest analysis per startup that HAS an sps_v3 at all" -- the same
    ROW_NUMBER()-per-startup shape get_rankings() uses, scoped to rows
    where methodology->'sps_v3' is present, so re-analyzing a startup
    under V3 doesn't double count its history. average_overall_score
    only ever averages SUFFICIENT rows' real numbers -- assessment_state
    'limited'/'insufficient' rows are counted in their own bucket, never
    contributing a null (or a fabricated 0) to that average (Phase 10.9
    Part 23's explicit "never treat null as zero").
    """
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT
                methodology->'sps_v3'->>'assessment_state' AS assessment_state,
                (methodology->'sps_v3'->>'overall_score')::float AS overall_score
            FROM (
                SELECT
                    methodology,
                    ROW_NUMBER() OVER (
                        PARTITION BY startup_id
                        ORDER BY created_at DESC, id DESC
                    ) AS row_number
                FROM analyses
                WHERE methodology IS NOT NULL
                  AND methodology->'sps_v3' IS NOT NULL
                  AND startup_id IS NOT NULL
            ) ranked
            WHERE row_number = 1
        """))

        rows = result.mappings().all()

    counts = {"sufficient": 0, "limited": 0, "insufficient": 0}
    sufficient_scores = []

    for row in rows:
        state = row["assessment_state"]
        if state in counts:
            counts[state] += 1
        if state == "sufficient" and row["overall_score"] is not None:
            sufficient_scores.append(row["overall_score"])

    return {
        "total_v3_assessed": len(rows),
        "sufficient": counts["sufficient"],
        "limited": counts["limited"],
        "insufficient": counts["insufficient"],
        "average_sufficient_overall_score": (
            round(sum(sufficient_scores) / len(sufficient_scores), 2)
            if sufficient_scores else None
        ),
    }


def get_industry_analytics():
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT
                COALESCE(industry, 'Unknown') AS industry,
                COALESCE(stage, 'Unknown') AS stage,
                COALESCE(business_model, 'Unknown') AS business_model,
                COUNT(*) AS total_startups,
                ROUND(AVG(overall_score), 2) AS average_overall_score,
                ROUND(AVG(market_score), 2) AS average_market_score,
                ROUND(AVG(team_score), 2) AS average_team_score,
                ROUND(AVG(product_score), 2) AS average_product_score,
                ROUND(AVG(competition_score), 2) AS average_competition_score,
                ROUND(AVG(traction_score), 2) AS average_traction_score,
                ROUND(AVG(financial_score), 2) AS average_financial_score
            FROM analyses
            GROUP BY
                COALESCE(industry, 'Unknown'),
                COALESCE(stage, 'Unknown'),
                COALESCE(business_model, 'Unknown')
            ORDER BY total_startups DESC
        """))

        rows = result.mappings().all()

    return [dict(row) for row in rows]



def get_rankings(viewer_user_id: str, viewer_is_admin: bool):
    """
    P0 Product Trust Cleanup: rankings must reflect ONLY canonical
    Methodology v2 analyses -- never the legacy flattened score columns,
    and never an analysis whose methodology JSON predates the current v2
    dimension set (e.g. a stored blob stamped methodology_version "1.0",
    which `methodology IS NOT NULL` alone does not exclude).

    Every column below is read from the methodology JSONB, not the legacy
    analyses.overall_score/market_score/etc. columns -- those columns are
    left exactly as they were (still written at analysis time for
    historical/legacy consumers) but are no longer this query's source of
    truth. The response SHAPE is unchanged (same keys as before) so the
    frontend RankingsTable requires no changes.

    "One row per startup, latest canonical analysis" is still enforced via
    the same ROW_NUMBER()-over-normalized-company_name pattern as before,
    now scoped to canonical rows only.

    Portfolio Release Task 3B: per the approved decision, Rankings is
    scoped to this viewer's own authorized analyses (own submissions +
    approved memberships + admin), not a platform-wide public leaderboard
    -- _analysis_visibility_clause() is applied inside the WHERE, before
    ROW_NUMBER() picks "latest," so this is the viewer's own latest
    authorized analysis per company, never a stranger's newer one.
    """
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT
                id,
                company_name,
                industry,
                stage,
                business_model,
                overall_score,
                market_score,
                team_score,
                product_score,
                competition_score,
                traction_score,
                financial_score,
                recommendation,
                created_at
            FROM (
                SELECT
                    id,
                    company_name,
                    industry,
                    stage,
                    business_model,
                    (methodology->>'startup_intelligence_score')::float AS overall_score,
                    (methodology->'market'->>'score')::float AS market_score,
                    (methodology->'team'->>'score')::float AS team_score,
                    (methodology->'product'->>'score')::float AS product_score,
                    (methodology->'execution'->>'score')::float AS competition_score,
                    (methodology->'traction'->>'score')::float AS traction_score,
                    (methodology->'financial_health'->>'score')::float AS financial_score,
                    methodology->'startup_scorecard'->>'recommendation' AS recommendation,
                    created_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY LOWER(TRIM(company_name))
                        ORDER BY created_at DESC, id DESC
                    ) AS row_number
                FROM analyses
                WHERE
                    methodology IS NOT NULL
                    AND methodology->'analysis_context'->>'methodology_version' = :methodology_version
                    AND methodology->>'startup_intelligence_score' IS NOT NULL
                    AND company_name IS NOT NULL
                    AND TRIM(company_name) <> ''
                    AND {_analysis_visibility_clause()}
            ) ranked_analyses
            WHERE row_number = 1
            ORDER BY overall_score DESC NULLS LAST, company_name ASC
        """), {
            "methodology_version": METHODOLOGY_VERSION,
            "viewer_user_id": viewer_user_id,
            "viewer_is_admin": viewer_is_admin,
        })

        rows = result.mappings().all()

    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Startup Discovery V1. One centralized query, reused by both the count and
# the page of results, so "which startups match these filters" can never
# disagree between the two.
#
# Same canonical population as get_rankings() -- methodology IS NOT NULL,
# methodology_version == the current constant, startup_intelligence_score
# present, company_name present -- and the same "exactly one row per
# startup, latest analysis wins" rule. The one deliberate difference:
# get_rankings() still partitions by LOWER(TRIM(company_name)) (its own
# docstring explains why it hasn't been migrated off that); this partitions
# by analyses.startup_id, the real FK written by get_or_create_startup()/
# save_analysis() -- the same choice already made for
# get_saved_startups_for_user() in Saved Startups Phase 1, for the same
# reason (a real identity, not a re-derived string match). On the current
# canonical population these two grouping rules produce the identical
# result set (verified: both currently resolve to the same 6 startups) --
# this is a stricter implementation of the same semantics, not a new
# definition of "current startup."
#
# Every filter is optional and additive (AND'd together). A pillar-minimum
# filter (min_market, etc.) compares against a JSONB-derived score that is
# NULL for any startup whose pillar was Unavailable -- SQL's own NULL
# semantics (`NULL >= x` is never TRUE) mean an unavailable pillar can
# never satisfy a minimum, with no special-case code required. Nothing
# here invents or defaults a missing score.
# ---------------------------------------------------------------------------

DEFAULT_DISCOVERY_LIMIT = 24
MAX_DISCOVERY_LIMIT = 100

_DISCOVERY_SORT_COLUMNS = {
    "sps_desc": "overall_score DESC NULLS LAST, company_name ASC",
    "sps_asc": "overall_score ASC NULLS LAST, company_name ASC",
    "newest": "created_at DESC, company_name ASC",
    "name_asc": "company_name ASC",
}


def _build_discovery_filters(
    query: str | None,
    industry: str | None,
    stage: str | None,
    business_model: str | None,
    min_sps: float | None,
    max_sps: float | None,
    min_market: float | None,
    min_team: float | None,
    min_product: float | None,
    min_execution: float | None,
    min_traction: float | None,
    min_financial_health: float | None,
) -> tuple[str, dict]:
    """
    Shared by discover_startups() and count_discover_startups() below, so
    the count shown to a user and the rows they actually get always agree
    about which startups qualify. Every value is bound as a SQLAlchemy
    parameter (:name) -- no filter value is ever interpolated into the SQL
    string itself, including the free-text `query`.
    """
    clauses: list[str] = []
    params: dict = {}

    if query:
        clauses.append("company_name ILIKE :query")
        params["query"] = f"%{query}%"

    if industry:
        clauses.append("industry = :industry")
        params["industry"] = industry

    if stage:
        clauses.append("stage = :stage")
        params["stage"] = stage

    if business_model:
        clauses.append("business_model = :business_model")
        params["business_model"] = business_model

    if min_sps is not None:
        clauses.append("overall_score >= :min_sps")
        params["min_sps"] = min_sps

    if max_sps is not None:
        clauses.append("overall_score <= :max_sps")
        params["max_sps"] = max_sps

    if min_market is not None:
        clauses.append("market_score >= :min_market")
        params["min_market"] = min_market

    if min_team is not None:
        clauses.append("team_score >= :min_team")
        params["min_team"] = min_team

    if min_product is not None:
        clauses.append("product_score >= :min_product")
        params["min_product"] = min_product

    if min_execution is not None:
        clauses.append("execution_score >= :min_execution")
        params["min_execution"] = min_execution

    if min_traction is not None:
        clauses.append("traction_score >= :min_traction")
        params["min_traction"] = min_traction

    if min_financial_health is not None:
        clauses.append("financial_score >= :min_financial_health")
        params["min_financial_health"] = min_financial_health

    where_sql = ""
    if clauses:
        where_sql = " AND " + " AND ".join(clauses)

    return where_sql, params


_DISCOVERY_BASE_CTE = f"""
    WITH latest_per_startup AS (
        SELECT
            startup_id,
            company_name,
            industry,
            stage,
            business_model,
            overall_score,
            market_score,
            team_score,
            product_score,
            execution_score,
            traction_score,
            financial_score,
            created_at
        FROM (
            SELECT
                a.startup_id AS startup_id,
                a.company_name AS company_name,
                a.industry AS industry,
                a.stage AS stage,
                a.business_model AS business_model,
                (a.methodology->>'startup_intelligence_score')::float AS overall_score,
                (a.methodology->'market'->>'score')::float AS market_score,
                (a.methodology->'team'->>'score')::float AS team_score,
                (a.methodology->'product'->>'score')::float AS product_score,
                (a.methodology->'execution'->>'score')::float AS execution_score,
                (a.methodology->'traction'->>'score')::float AS traction_score,
                (a.methodology->'financial_health'->>'score')::float AS financial_score,
                a.created_at AS created_at,
                ROW_NUMBER() OVER (
                    PARTITION BY a.startup_id
                    ORDER BY a.created_at DESC, a.id DESC
                ) AS row_number
            FROM analyses a
            WHERE
                a.startup_id IS NOT NULL
                AND a.methodology IS NOT NULL
                AND a.methodology->'analysis_context'->>'methodology_version' = :methodology_version
                AND a.methodology->>'startup_intelligence_score' IS NOT NULL
                AND a.company_name IS NOT NULL
                AND TRIM(a.company_name) <> ''
                AND {_analysis_visibility_clause("a")}
        ) ranked
        WHERE row_number = 1
    )
"""
# Portfolio Release Task 3B: the visibility clause above is baked into
# this module-level CTE string at import time (it's a fixed SQL fragment
# containing the :viewer_user_id/:viewer_is_admin placeholders, not
# literal values -- same as :methodology_version already was) -- so every
# one of this CTE's three consumers below now REQUIRES viewer_user_id and
# viewer_is_admin among the params it binds, applied before ROW_NUMBER()
# picks "latest," same reasoning as get_rankings()/search_analyses().


def discover_startups(
    viewer_user_id: str,
    viewer_is_admin: bool,
    query: str | None = None,
    industry: str | None = None,
    stage: str | None = None,
    business_model: str | None = None,
    min_sps: float | None = None,
    max_sps: float | None = None,
    min_market: float | None = None,
    min_team: float | None = None,
    min_product: float | None = None,
    min_execution: float | None = None,
    min_traction: float | None = None,
    min_financial_health: float | None = None,
    sort: str = "sps_desc",
    limit: int = DEFAULT_DISCOVERY_LIMIT,
    offset: int = 0,
):
    where_sql, params = _build_discovery_filters(
        query, industry, stage, business_model,
        min_sps, max_sps,
        min_market, min_team, min_product, min_execution, min_traction, min_financial_health,
    )

    params["methodology_version"] = METHODOLOGY_VERSION
    params["viewer_user_id"] = viewer_user_id
    params["viewer_is_admin"] = viewer_is_admin
    # Defensive bounds even though app/api.py's Query(...) validation
    # already enforces these -- this function is also called directly by
    # tests and is safe to call with untrusted values on its own.
    params["limit"] = max(1, min(limit, MAX_DISCOVERY_LIMIT))
    params["offset"] = max(0, offset)

    order_sql = _DISCOVERY_SORT_COLUMNS.get(sort, _DISCOVERY_SORT_COLUMNS["sps_desc"])

    sql = _DISCOVERY_BASE_CTE + f"""
        SELECT * FROM latest_per_startup
        WHERE 1=1{where_sql}
        ORDER BY {order_sql}
        LIMIT :limit OFFSET :offset
    """

    with engine.begin() as connection:
        result = connection.execute(text(sql), params)
        rows = result.mappings().all()

    return [dict(row) for row in rows]


def count_discover_startups(
    viewer_user_id: str,
    viewer_is_admin: bool,
    query: str | None = None,
    industry: str | None = None,
    stage: str | None = None,
    business_model: str | None = None,
    min_sps: float | None = None,
    max_sps: float | None = None,
    min_market: float | None = None,
    min_team: float | None = None,
    min_product: float | None = None,
    min_execution: float | None = None,
    min_traction: float | None = None,
    min_financial_health: float | None = None,
) -> int:
    where_sql, params = _build_discovery_filters(
        query, industry, stage, business_model,
        min_sps, max_sps,
        min_market, min_team, min_product, min_execution, min_traction, min_financial_health,
    )

    params["methodology_version"] = METHODOLOGY_VERSION
    params["viewer_user_id"] = viewer_user_id
    params["viewer_is_admin"] = viewer_is_admin

    sql = _DISCOVERY_BASE_CTE + f"""
        SELECT COUNT(*) FROM latest_per_startup
        WHERE 1=1{where_sql}
    """

    with engine.begin() as connection:
        return connection.execute(text(sql), params).scalar()


def get_discovery_filter_options(viewer_user_id: str, viewer_is_admin: bool):
    """
    Startup Discovery V1, Part 4: filter option lists are derived from the
    REAL canonical population, never hardcoded -- so the UI can never offer
    an industry/stage/business model that currently returns zero results,
    and automatically grows as more canonical analyses are added. Sourced
    from the exact same canonical population discover_startups() itself
    queries (same methodology_version/startup_id gate), via the shared CTE.

    Portfolio Release Task 3B: same viewer-scoped CTE as discover_startups()
    -- filter options (which industries/stages/business models to offer)
    are derived only from analyses this viewer is authorized to see, never
    the whole platform's.
    """
    sql = _DISCOVERY_BASE_CTE + """
        SELECT
            ARRAY_AGG(DISTINCT industry) FILTER (WHERE industry IS NOT NULL AND TRIM(industry) <> '') AS industries,
            ARRAY_AGG(DISTINCT stage) FILTER (WHERE stage IS NOT NULL AND TRIM(stage) <> '') AS stages,
            ARRAY_AGG(DISTINCT business_model) FILTER (WHERE business_model IS NOT NULL AND TRIM(business_model) <> '') AS business_models
        FROM latest_per_startup
    """

    with engine.begin() as connection:
        row = connection.execute(
            text(sql),
            {
                "methodology_version": METHODOLOGY_VERSION,
                "viewer_user_id": viewer_user_id,
                "viewer_is_admin": viewer_is_admin,
            },
        ).mappings().first()

    return {
        "industries": sorted(row["industries"] or []),
        "stages": sorted(row["stages"] or []),
        "business_models": sorted(row["business_models"] or []),
    }


MIN_COMPARISON_STARTUPS = 2
MAX_COMPARISON_STARTUPS = 4


def get_startups_for_comparison(startup_ids: list[int], viewer_user_id: str, viewer_is_admin: bool):
    """
    Compare Startups V1. Resolves each of the given canonical startups.id
    values to its own latest canonical (methodology_version-matching)
    analysis -- the same startup_id-keyed "latest per startup" semantics
    as discover_startups()/get_saved_startups_for_user(), not a new or
    competing definition of "current startup".

    Unlike discover_startups()'s flat DiscoveryResult shape, this returns
    the FULL methodology JSONB per startup -- Compare needs pillar
    strengths/weaknesses/subscores, which the flat Discovery shape never
    carried. app/api.py's /compare endpoint slims this down to the fields
    the frontend actually needs (see ComparisonStartup); this function's
    job is only canonical resolution.

    Deduplicates startup_ids (preserving first-occurrence order) and
    returns results in that SAME order -- callers that need to know which
    of their requested ids didn't resolve (invalid id, or a real startup
    with no canonical analysis yet) compare their own input against the
    returned rows' startup_ids; this function never raises for a
    partially-unresolvable list, since "some ids didn't resolve" is a
    normal, cleanly-representable outcome, not an error.

    Portfolio Release Task 3B: startup_ids here are caller-supplied,
    explicit IDs (from the /compare?startups=1,2,3 query string) -- exactly
    the "explicit IDs must not bypass authorization" case. The visibility
    clause is applied inside the CTE's own WHERE, before ROW_NUMBER() picks
    "latest," so a startup_id the viewer isn't authorized to see resolves
    to nothing (indistinguishable from an invalid/nonexistent id in the
    response shape -- see missing_startup_ids in app/api.py's /compare),
    never a 403 that would confirm the id refers to something real.
    """
    deduped_ids = list(dict.fromkeys(startup_ids))

    if not deduped_ids:
        return []

    with engine.begin() as connection:
        result = connection.execute(text(f"""
            WITH latest_per_startup AS (
                SELECT
                    a.startup_id AS startup_id,
                    a.id AS analysis_id,
                    a.company_name AS company_name,
                    a.created_at AS created_at,
                    a.methodology AS methodology,
                    ROW_NUMBER() OVER (
                        PARTITION BY a.startup_id
                        ORDER BY a.created_at DESC, a.id DESC
                    ) AS row_number
                FROM analyses a
                WHERE
                    a.startup_id = ANY(:startup_ids)
                    AND a.methodology IS NOT NULL
                    AND a.methodology->'analysis_context'->>'methodology_version' = :methodology_version
                    AND {_analysis_visibility_clause("a")}
            )
            SELECT startup_id, analysis_id, company_name, created_at, methodology
            FROM latest_per_startup
            WHERE row_number = 1
        """), {
            "startup_ids": deduped_ids,
            "methodology_version": METHODOLOGY_VERSION,
            "viewer_user_id": viewer_user_id,
            "viewer_is_admin": viewer_is_admin,
        })

        rows = {row["startup_id"]: dict(row) for row in result.mappings().all()}

    ordered_results = []

    for startup_id in deduped_ids:
        row = rows.get(startup_id)

        if row is None:
            continue

        if isinstance(row["methodology"], str):
            row["methodology"] = json.loads(row["methodology"])

        ordered_results.append(row)

    return ordered_results


# ---------------------------------------------------------------------------
# Investor Workspace V1 (Phase 9). No new table: saved_startups remains the
# sole watchlist relationship (see save_startup_for_user()/
# get_saved_startups_for_user() above), and this function's only job is
# resolving each of a user's saved startups to its two most recent
# canonical (methodology_version-matching) analyses -- "latest" and
# "previous" -- so app/ai/investor_workspace.py can deterministically diff
# them. Same ROW_NUMBER()-per-startup_id pattern as
# get_startups_for_comparison() just above, generalized from "top 1" to
# "top 2" and batched across every saved startup_id in one query rather
# than one query per startup.
# ---------------------------------------------------------------------------

def get_watchlist_startups_for_user(user_id: str, viewer_is_admin: bool = False):
    """
    One entry per startup this user has saved (most-recently-saved first),
    each carrying its own `latest` and `previous` canonical analysis
    (id/created_at/methodology), independently resolved by startup_id --
    not by re-deriving identity from company_name the way get_rankings()
    still does. Either or both of `latest`/`previous` is None, never a
    fabricated stand-in:

    - `latest` is None when the startup has zero canonical analyses yet
      (e.g. only pre-Methodology-v2 history, or never analyzed at all).
      The startup still appears in the list -- a user's own saved list is
      never silently trimmed by the state of canonical intelligence.
    - `previous` is None when the startup has exactly one canonical
      analysis. This is the "no historical comparison yet" case Part 13.B
      calls out; callers must represent it as "unknown", never as a zero
      delta.

    Ownership of the WATCHLIST ITSELF is enforced entirely in SQL via
    `WHERE ss.user_id = :user_id` -- there is no path through this
    function for one user's watchlist to include another user's
    saved_startups row.

    Portfolio Release Task 3B -- Secure Analysis Visibility: watching
    (saving) a startup is NOT ownership of its analysis content, same
    principle as get_saved_startups_for_user() (approved decision, item
    5) -- and this function is a MORE severe instance of that same gap
    than Saved Startups' own list view: it returns the full methodology
    JSONB (evidence, rationale, everything), not just a score. The
    history_rows query below is now scoped by
    _analysis_visibility_clause(), so a watched startup this user is not
    otherwise authorized for (not the submitter, not an approved member,
    not an admin) correctly resolves to latest/previous = None -- the
    watchlist entry itself still appears (it's the user's own real
    saved_startups row), just with no visible intelligence, exactly
    mirroring the "zero canonical analyses yet" case already handled
    above.
    """
    with engine.begin() as connection:
        saved_rows = connection.execute(text("""
            SELECT
                ss.startup_id AS startup_id,
                ss.created_at AS saved_at,
                startups.canonical_name AS company_name
            FROM saved_startups ss
            JOIN startups ON startups.id = ss.startup_id
            WHERE ss.user_id = :user_id
            ORDER BY ss.created_at DESC
        """), {"user_id": user_id}).mappings().all()

        startup_ids = [row["startup_id"] for row in saved_rows]

        history_by_startup: dict[int, list[dict]] = {}

        if startup_ids:
            history_rows = connection.execute(text(f"""
                SELECT startup_id, analysis_id, created_at, methodology, row_number
                FROM (
                    SELECT
                        a.startup_id AS startup_id,
                        a.id AS analysis_id,
                        a.created_at AS created_at,
                        a.methodology AS methodology,
                        ROW_NUMBER() OVER (
                            PARTITION BY a.startup_id
                            ORDER BY a.created_at DESC, a.id DESC
                        ) AS row_number
                    FROM analyses a
                    WHERE
                        a.startup_id = ANY(:startup_ids)
                        AND a.methodology IS NOT NULL
                        AND a.methodology->'analysis_context'->>'methodology_version' = :methodology_version
                        AND {_analysis_visibility_clause("a")}
                ) ranked
                WHERE row_number <= 2
            """), {
                "startup_ids": startup_ids,
                "methodology_version": METHODOLOGY_VERSION,
                "viewer_user_id": user_id,
                "viewer_is_admin": viewer_is_admin,
            }).mappings().all()

            for row in history_rows:
                methodology = row["methodology"]
                if isinstance(methodology, str):
                    methodology = json.loads(methodology)

                entry = {
                    "analysis_id": row["analysis_id"],
                    "created_at": row["created_at"],
                    "methodology": methodology,
                }

                history_by_startup.setdefault(row["startup_id"], [None, None])
                history_by_startup[row["startup_id"]][row["row_number"] - 1] = entry

    results = []

    for row in saved_rows:
        latest, previous = history_by_startup.get(row["startup_id"], [None, None])
        results.append({
            "startup_id": row["startup_id"],
            "company_name": row["company_name"],
            "saved_at": row["saved_at"],
            "latest": latest,
            "previous": previous,
        })

    return results


# ---------------------------------------------------------------------------
# Idea Lab / Venture Simulator V1. modeled_ventures is a completely
# separate persistence concept from startups/analyses -- see the Phase 6
# design report for the full reasoning. Structurally:
#
# - No column here references startups or analyses. Creating, editing, or
#   deleting a modeled venture can never touch canonical intelligence,
#   because there is no foreign key path to it at all.
# - Every read/write function below takes user_id as a REQUIRED filter,
#   not an optional one -- the same "ownership scoped in the SQL itself,
#   not just checked in Python after the fact" discipline already used
#   for saved_startups (see save_startup_for_user()'s own docstring).
#   A mismatched owner gets a clean "not found" (None / 0 rows), never a
#   leaked row and never a different error shape that would let a caller
#   distinguish "doesn't exist" from "belongs to someone else".
# - model_result (the computed VPS) is stored as its own JSONB column,
#   entirely separate from analyses.methodology -- a modeled venture can
#   never be mistaken for a canonical analysis by any query that reads
#   analyses, because it was never inserted into analyses at all.
# ---------------------------------------------------------------------------

def create_modeled_ventures_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS modeled_ventures (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,
                industry TEXT,
                business_model TEXT,
                target_customer TEXT,
                stage TEXT,
                assumptions JSONB NOT NULL DEFAULT '{}'::jsonb,
                model_result JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

    print("modeled_ventures table created successfully.")


def create_modeled_venture(
    user_id: str,
    name: str,
    description: str | None,
    industry: str | None,
    business_model: str | None,
    target_customer: str | None,
    stage: str | None,
    assumptions: dict,
    model_result: dict | None,
) -> int:
    with engine.begin() as connection:
        result = connection.execute(text("""
            INSERT INTO modeled_ventures (
                user_id, name, description, industry, business_model,
                target_customer, stage, assumptions, model_result
            )
            VALUES (
                :user_id, :name, :description, :industry, :business_model,
                :target_customer, :stage, :assumptions, :model_result
            )
            RETURNING id
        """), {
            "user_id": user_id,
            "name": name,
            "description": description,
            "industry": industry,
            "business_model": business_model,
            "target_customer": target_customer,
            "stage": stage,
            "assumptions": json.dumps(assumptions),
            "model_result": json.dumps(model_result) if model_result is not None else None,
        })

        return result.scalar()


def _parse_venture_row(row: dict) -> dict:
    venture = dict(row)

    if isinstance(venture.get("assumptions"), str):
        venture["assumptions"] = json.loads(venture["assumptions"])

    if isinstance(venture.get("model_result"), str):
        venture["model_result"] = json.loads(venture["model_result"])

    return venture


def list_modeled_ventures_for_user(user_id: str):
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT id, user_id, name, description, industry, business_model,
                   target_customer, stage, assumptions, model_result,
                   created_at, updated_at
            FROM modeled_ventures
            WHERE user_id = :user_id
            ORDER BY updated_at DESC
        """), {"user_id": user_id})

        rows = result.mappings().all()

    return [_parse_venture_row(dict(row)) for row in rows]


def get_modeled_venture_for_user(user_id: str, venture_id: int):
    """
    Returns None both when the venture doesn't exist AND when it belongs
    to a different user -- the caller (app/api.py) maps both to the same
    404, so a request can never distinguish "wrong id" from "someone
    else's venture" (the same non-leaking shape already used for Saved
    Startups' invalid-startup-id handling).
    """
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT id, user_id, name, description, industry, business_model,
                   target_customer, stage, assumptions, model_result,
                   created_at, updated_at
            FROM modeled_ventures
            WHERE id = :venture_id AND user_id = :user_id
        """), {"venture_id": venture_id, "user_id": user_id})

        row = result.mappings().first()

    if row is None:
        return None

    return _parse_venture_row(dict(row))


def update_modeled_venture_for_user(
    user_id: str,
    venture_id: int,
    name: str,
    description: str | None,
    industry: str | None,
    business_model: str | None,
    target_customer: str | None,
    stage: str | None,
    assumptions: dict,
    model_result: dict | None,
) -> bool:
    """Returns True if a row was actually updated -- False means either the
    venture doesn't exist or belongs to a different user; the WHERE
    clause's user_id filter is what makes cross-user writes structurally
    impossible, not a Python-level check performed after the fact."""
    with engine.begin() as connection:
        result = connection.execute(text("""
            UPDATE modeled_ventures
            SET name = :name,
                description = :description,
                industry = :industry,
                business_model = :business_model,
                target_customer = :target_customer,
                stage = :stage,
                assumptions = :assumptions,
                model_result = :model_result,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :venture_id AND user_id = :user_id
        """), {
            "venture_id": venture_id,
            "user_id": user_id,
            "name": name,
            "description": description,
            "industry": industry,
            "business_model": business_model,
            "target_customer": target_customer,
            "stage": stage,
            "assumptions": json.dumps(assumptions),
            "model_result": json.dumps(model_result) if model_result is not None else None,
        })

        return result.rowcount > 0


def delete_modeled_venture_for_user(user_id: str, venture_id: int) -> bool:
    with engine.begin() as connection:
        result = connection.execute(text("""
            DELETE FROM modeled_ventures
            WHERE id = :venture_id AND user_id = :user_id
        """), {"venture_id": venture_id, "user_id": user_id})

        return result.rowcount > 0


# ---------------------------------------------------------------------------
# Phase 27 -- Shareable Venture Snapshot V1. Four narrowly-scoped additive
# columns on the EXISTING modeled_ventures table -- no new table, no
# generic "permissions"/"visibility" system. Investigated first (Part 1):
# no share/public-token architecture existed anywhere in this repository
# before this phase.
#
# share_public_id is generated ONCE, the first time sharing is ever
# enabled, and never regenerated or deleted afterward -- disabling sets
# share_enabled=false but leaves the id in place, so re-enabling reuses
# the exact same URL (Part 15's "do not build snapshot versioning," and
# Part 6's "prefer an opaque public identifier... venture IDs directly
# enumerable" -- a random, unguessable token, never the sequential
# integer `id` this table already exposes internally). The value itself
# is never treated as a secret credential -- knowing it is exactly
# equivalent to having the link, which is the intended sharing model
# (Part 4/6's own "a person needs the link," not a password).
def add_venture_share_columns():
    columns = [
        "share_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "share_public_id TEXT",
        "share_show_vps BOOLEAN NOT NULL DEFAULT FALSE",
        "share_show_validation BOOLEAN NOT NULL DEFAULT TRUE",
    ]

    for column in columns:
        column_name = column.split()[0]
        try:
            with engine.begin() as connection:
                connection.execute(text(
                    f"ALTER TABLE modeled_ventures ADD COLUMN {column}"
                ))
            print(f"{column_name} column added")
        except Exception as e:
            print(f"{column_name} migration skipped", e)

    # A unique index, not a UNIQUE column constraint, so multiple rows
    # that have never enabled sharing (share_public_id IS NULL) don't
    # collide against Postgres's own NULL-uniqueness semantics -- this
    # index only ever needs to guarantee uniqueness among REAL, generated
    # tokens.
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_modeled_ventures_share_public_id
                ON modeled_ventures (share_public_id)
                WHERE share_public_id IS NOT NULL
            """))
        print("idx_modeled_ventures_share_public_id index created")
    except Exception as e:
        print("idx_modeled_ventures_share_public_id migration skipped", e)


def get_venture_share_settings_for_owner(user_id: str, venture_id: int) -> dict | None:
    """Owner-only read of the current share settings. Returns None (never
    a 404-shaped partial) when the venture doesn't exist or belongs to a
    different user -- the same non-leaking shape get_modeled_venture_for_user()
    already established."""
    with engine.begin() as connection:
        row = connection.execute(text("""
            SELECT share_enabled, share_public_id, share_show_vps, share_show_validation
            FROM modeled_ventures
            WHERE id = :venture_id AND user_id = :user_id
        """), {"venture_id": venture_id, "user_id": user_id}).mappings().first()

    return dict(row) if row is not None else None


def update_venture_share_settings_for_owner(
    user_id: str,
    venture_id: int,
    enabled: bool,
    show_vps: bool,
    show_validation: bool,
) -> dict | None:
    """Enables/disables sharing and updates the two visibility toggles in
    one call. Generates share_public_id ONLY the first time `enabled` is
    True and no id exists yet -- every subsequent enable/disable cycle
    reuses that same id (Part 14/15's own "disable, then re-enable if
    architecture supports it" and "URL remains stable" requirements)."""
    with engine.begin() as connection:
        current = connection.execute(text("""
            SELECT share_public_id FROM modeled_ventures
            WHERE id = :venture_id AND user_id = :user_id
        """), {"venture_id": venture_id, "user_id": user_id}).mappings().first()

        if current is None:
            return None

        public_id = current["share_public_id"]
        if enabled and not public_id:
            # 16 bytes of randomness, URL-safe -- ~128 bits of entropy,
            # structurally unguessable (Part 6's own "do not make venture
            # IDs directly enumerable" requirement, satisfied by using
            # secrets.token_urlsafe rather than the sequential `id`).
            public_id = secrets.token_urlsafe(16)

        connection.execute(text("""
            UPDATE modeled_ventures
            SET share_enabled = :enabled,
                share_public_id = :public_id,
                share_show_vps = :show_vps,
                share_show_validation = :show_validation
            WHERE id = :venture_id AND user_id = :user_id
        """), {
            "venture_id": venture_id,
            "user_id": user_id,
            "enabled": enabled,
            "public_id": public_id,
            "show_vps": show_vps,
            "show_validation": show_validation,
        })

        row = connection.execute(text("""
            SELECT share_enabled, share_public_id, share_show_vps, share_show_validation
            FROM modeled_ventures
            WHERE id = :venture_id AND user_id = :user_id
        """), {"venture_id": venture_id, "user_id": user_id}).mappings().first()

    return dict(row) if row is not None else None


def get_venture_by_share_public_id(public_id: str) -> dict | None:
    """THE public, unauthenticated lookup. Returns None both when no
    venture has this public_id at all AND when one does but sharing is
    currently disabled -- a caller can never distinguish "wrong link" from
    "this founder turned sharing off," matching this module's own
    established non-leaking-404 precedent (get_modeled_venture_for_user's
    docstring) one level up. share_enabled is checked in SQL, not in
    Python after the fact, so a disabled venture's row is never even
    returned to the caller."""
    with engine.begin() as connection:
        row = connection.execute(text("""
            SELECT id, name, stage, target_customer, assumptions, model_result,
                   share_show_vps, share_show_validation, updated_at
            FROM modeled_ventures
            WHERE share_public_id = :public_id AND share_enabled = TRUE
        """), {"public_id": public_id}).mappings().first()

    if row is None:
        return None

    return _parse_venture_row(dict(row))


# ---------------------------------------------------------------------------
# Phase 10.7 -- Founder Missions V1. venture_missions belongs to
# modeled_ventures, structurally as separate from founder_actions/
# startups/analyses as modeled_ventures itself already is from those same
# tables (see create_modeled_ventures_table()'s own docstring -- the same
# reasoning applies here one level down). The FK is to modeled_ventures(id)
# ONLY; there is no column here, and no query anywhere in this module,
# that could resolve a mission to a startup_id, analysis_id, or
# founder_action.
#
# Deliberately modeled on founder_actions' own table/function shape
# (title, description, a related-category label, status, source +
# source_ref for the exact same "Add to Plan is idempotent" dedup
# discipline -- see create_founder_action()'s own docstring, reused here
# verbatim in create_venture_mission()) rather than a new pattern --
# Part 1's own instruction to inspect founder_actions "only as a
# reference," not to reuse it directly (no shared table, no shared FK, no
# shared endpoint).
#
# THE VPS FIREWALL (Part 9) is structural, not a convention someone has to
# remember: no function in this section ever touches modeled_ventures.
# assumptions or modeled_ventures.model_result, and no function in
# app/api.py's mission endpoints ever calls compute_vps()/
# update_modeled_venture_for_user(). A mission's status has no code path
# to a score.
#
# learning_summary/learning_recorded_at live directly on this table
# (Part 11's Option A) -- a mission has at most one current reflection in
# V1, so a second table would be unused complexity today. resource_ref is
# a nullable, unused-in-V1 column (Part 18): a future Founder Playbook
# feature can populate it without a schema change, but nothing reads or
# writes it in this phase.
def create_venture_missions_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS venture_missions (
                id SERIAL PRIMARY KEY,
                venture_id INTEGER NOT NULL REFERENCES modeled_ventures(id) ON DELETE CASCADE,
                created_by_user_id TEXT NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                description TEXT,
                mission_type TEXT NOT NULL DEFAULT 'other'
                    CHECK (mission_type IN (
                        'customer_discovery', 'validation', 'pricing', 'gtm',
                        'product', 'founder', 'economics', 'other'
                    )),
                related_category TEXT,
                source TEXT NOT NULL
                    CHECK (source IN ('vps_guidance', 'founder_created')),
                -- Dedup key for vps_guidance-sourced missions only -- see
                -- create_venture_mission()'s own docstring. Always NULL
                -- for founder_created, so the partial unique index below
                -- never constrains founder-authored missions.
                source_ref TEXT,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'completed', 'dismissed')),
                learning_summary TEXT,
                learning_recorded_at TIMESTAMP,
                -- Part 18: nullable, future Founder Playbook hook. Unused
                -- (never read, never written) in this phase.
                resource_ref TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """))

        connection.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS venture_missions_dedup_vps_guidance
            ON venture_missions (venture_id, source_ref)
            WHERE source <> 'founder_created'
        """))

    print("venture_missions table created successfully.")


def add_pitch_deck_coach_mission_source():
    """
    Phase 11 -- Pitch Deck Coach V2, Part 13. Same migration shape as
    add_fundraising_gap_source_to_founder_actions() (Phase 8): widens the
    CHECK constraint to allow a third source value, 'pitch_deck_coach',
    for a mission a founder explicitly created from a deck review's
    top_fixes card ("Make this a mission"). Deliberately its own source
    value, not reused 'vps_guidance' or 'founder_created': provenance
    should say where a mission actually came from, and this codebase's
    own established pattern (founder_actions' 'sie_recommendation' /
    'founder_created' / 'fundraising_gap' trio) is exactly this --
    distinct source per real origin. Dedup behavior is intentionally the
    SAME as vps_guidance (source <> 'founder_created' already covers any
    non-founder_created value, this one included) -- clicking "Make this
    a mission" twice for the identical fix title on the same venture
    must not create two rows. Never touches existing rows.
    """
    with engine.begin() as connection:
        connection.execute(text("""
            ALTER TABLE venture_missions DROP CONSTRAINT IF EXISTS venture_missions_source_check
        """))
        connection.execute(text("""
            ALTER TABLE venture_missions ADD CONSTRAINT venture_missions_source_check
            CHECK (source IN ('vps_guidance', 'founder_created', 'pitch_deck_coach'))
        """))

    print("venture_missions.source migrated to include pitch_deck_coach.")


def _mission_ownership_join_clause() -> str:
    # Ownership is enforced by this JOIN's predicate, not by a Python
    # check performed after a row is fetched -- the same discipline
    # get_modeled_venture_for_user() already uses one table up. A mission
    # belonging to a venture some OTHER user owns can never be selected,
    # updated, or returned by any function below; there is no code path
    # where the WHERE clause is satisfied but the row belongs to the
    # wrong user.
    return "JOIN modeled_ventures v ON v.id = vm.venture_id"


def list_venture_missions_for_owner(user_id: str, venture_id: int):
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT vm.id, vm.venture_id, vm.created_by_user_id, vm.title,
                   vm.description, vm.mission_type, vm.related_category,
                   vm.source, vm.source_ref, vm.status, vm.learning_summary,
                   vm.learning_recorded_at, vm.resource_ref, vm.created_at,
                   vm.updated_at, vm.completed_at, vm.question_text,
                   vm.why_it_matters, vm.interpretation_summary,
                   vm.interpretation_limitations, vm.interpretation_generated_at
            FROM venture_missions vm
            {_mission_ownership_join_clause()}
            WHERE vm.venture_id = :venture_id AND v.user_id = :user_id
            ORDER BY vm.created_at ASC
        """), {"venture_id": venture_id, "user_id": user_id})

        return [dict(row) for row in result.mappings().all()]


# Phase 34E -- Founder Experience Simplification V1. "My Ideas" (the
# venture list) needs, per card, "what should I continue?" -- the active
# question, if any -- without turning that list page into N+1 queries (one
# per venture). ONE bulk query across every venture this user owns,
# DISTINCT ON venture_id so a venture with more than one active mission
# (shouldn't normally happen under the one-active-question-at-a-time V1
# model, but is not itself invalid) still contributes exactly one row,
# the most recently created.
def list_active_questions_for_user(user_id: str) -> dict[int, str]:
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT DISTINCT ON (vm.venture_id) vm.venture_id, vm.question_text
            FROM venture_missions vm
            JOIN modeled_ventures v ON v.id = vm.venture_id
            WHERE v.user_id = :user_id
              AND vm.status = 'active'
              AND vm.question_text IS NOT NULL
            ORDER BY vm.venture_id, vm.created_at DESC
        """), {"user_id": user_id})

        return {row["venture_id"]: row["question_text"] for row in result.mappings().all()}


# Phase 40A-FIX -- Private Beta P1 Hardening. Additive column, separate
# from and additional to venture_missions' own pre-existing
# `(venture_id, source_ref) WHERE source <> 'founder_created'` unique
# index -- that index collapses accidentally-duplicate vps_guidance/
# pitch_deck_coach SUGGESTIONS by matching title (a payload-similarity
# mechanism, confirmed by create_venture_mission()'s own docstring:
# "founder_created missions are never deduplicated" by it at all). This
# new column is the ONE genuine request-identity mechanism, identical
# shape to venture_decisions'/venture_financial_snapshots' own
# idempotency_key, and is what actually protects a founder-authored
# custom mission (the one case the existing index explicitly skips)
# from a real double-submit.
def add_mission_idempotency_column():
    """
    Scoped to (created_by_user_id, idempotency_key), not a bare
    idempotency_key -- see add_financial_snapshot_idempotency_column()'s
    own docstring for the exact cross-user replay finding this scoping
    closes. `created_by_user_id` is venture_missions' own user-identity
    column (this table predates the `user_id` naming convention later
    tables use).
    """
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                ALTER TABLE venture_missions
                ADD COLUMN idempotency_key TEXT
            """))
    except Exception as e:
        print("venture_missions.idempotency_key migration skipped", e)

    try:
        with engine.begin() as connection:
            connection.execute(text("DROP INDEX IF EXISTS venture_missions_idempotency_key_idx"))
            connection.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS venture_missions_idempotency_key_idx
                ON venture_missions (created_by_user_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL
            """))
        print("venture_missions.idempotency_key added.")
    except Exception as e:
        print("venture_missions.idempotency_key_idx migration skipped", e)


_MISSION_COLUMNS = """
                id, venture_id, created_by_user_id, title, description,
                mission_type, related_category, source, source_ref, status,
                learning_summary, learning_recorded_at, resource_ref,
                created_at, updated_at, completed_at,
                question_text, why_it_matters, interpretation_summary,
                interpretation_limitations, interpretation_generated_at
"""

# Same column list, `vm.`-qualified -- required whenever the query also
# joins `modeled_ventures v` (which shares column names like `id` with
# venture_missions), or the bare names above would be ambiguous.
_MISSION_COLUMNS_VM = """
                vm.id, vm.venture_id, vm.created_by_user_id, vm.title,
                vm.description, vm.mission_type, vm.related_category,
                vm.source, vm.source_ref, vm.status, vm.learning_summary,
                vm.learning_recorded_at, vm.resource_ref, vm.created_at,
                vm.updated_at, vm.completed_at, vm.question_text,
                vm.why_it_matters, vm.interpretation_summary,
                vm.interpretation_limitations, vm.interpretation_generated_at
"""


def create_venture_mission(
    venture_id: int,
    user_id: str,
    title: str,
    description: str | None,
    mission_type: str,
    related_category: str | None,
    source: str,
    resource_ref: str | None = None,
    question_text: str | None = None,
    why_it_matters: str | None = None,
    idempotency_key: str | None = None,
):
    """
    Creates one venture_missions row, OR -- for a vps_guidance/
    pitch_deck_coach-sourced mission whose exact title already exists for
    this venture -- returns the existing row untouched. Verbatim the same
    idempotency contract as create_founder_action() (see that function's
    own docstring for the full reasoning); source_ref is derived HERE
    from title, never accepted from the caller, and founder_created
    missions are never deduplicated BY THIS MECHANISM.

    resource_ref (Phase 11, Part 14): the first real use of the column
    Phase 10.7 reserved as "future Founder Playbook hook" -- a playbook
    slug (e.g. "go-to-market") the caller resolved BEFORE calling this
    (via lib/playbooks/resourceMap.ts on the frontend), never computed
    here. None for every existing caller (vps_guidance suggestions,
    founder-authored missions) -- this function's signature default
    keeps their behavior byte-identical.

    question_text / why_it_matters (Phase 34D -- SIE Build Intelligence
    Loop V1): the specific unknown this Test targets, set once at
    creation and otherwise immutable -- see
    docs/product/SIE_BUILD_INTELLIGENCE_ARCHITECTURE_V1.md §D.1. Both
    default to None so every pre-existing caller (vps_guidance
    suggestions, "Create your own action") keeps working byte-identical.

    Ownership is enforced by the caller (app/api.py) verifying
    get_modeled_venture_for_user(user_id, venture_id) is not None BEFORE
    this runs -- this function itself does not re-check ownership because
    venture_id here is only ever a value the caller already confirmed
    belongs to user_id, same as create_founder_action() trusts an
    already-verified startup_id.

    idempotency_key (Phase 40A-FIX): a SEPARATE, additional
    request-identity mechanism from the source_ref dedup above -- see
    add_mission_idempotency_column()'s own docstring. When omitted (the
    default), this function's SQL and behavior are byte-identical to
    before this phase: the ORIGINAL `ON CONFLICT (venture_id, source_ref)
    WHERE source <> 'founder_created'` statement runs unchanged, and a
    founder_created mission (source_ref always NULL) is still never
    deduplicated by it. When provided, a DIFFERENT INSERT statement runs
    instead, targeting `ON CONFLICT (idempotency_key)` -- this is what
    actually protects a founder-authored custom mission (or any other
    caller that chooses to pass one) from a genuine double-submit. Both
    statements insert the exact same row shape; only the conflict target
    differs, and Postgres only supports one arbiter per INSERT, which is
    why this is a branch rather than a single combined statement.
    """
    source_ref = title.strip() if source != "founder_created" else None

    with engine.begin() as connection:
        if idempotency_key is not None:
            result = connection.execute(text(f"""
                INSERT INTO venture_missions (
                    venture_id, created_by_user_id, title, description,
                    mission_type, related_category, source, source_ref,
                    resource_ref, status, question_text, why_it_matters, idempotency_key
                )
                VALUES (
                    :venture_id, :created_by_user_id, :title, :description,
                    :mission_type, :related_category, :source, :source_ref,
                    :resource_ref, 'active', :question_text, :why_it_matters, :idempotency_key
                )
                ON CONFLICT (created_by_user_id, idempotency_key) WHERE idempotency_key IS NOT NULL
                    DO NOTHING
                RETURNING {_MISSION_COLUMNS}
            """), {
                "venture_id": venture_id,
                "created_by_user_id": user_id,
                "title": title,
                "description": description,
                "mission_type": mission_type,
                "related_category": related_category,
                "source": source,
                "source_ref": source_ref,
                "resource_ref": resource_ref,
                "question_text": question_text,
                "why_it_matters": why_it_matters,
                "idempotency_key": idempotency_key,
            })

            row = result.mappings().first()
            if row is not None:
                return dict(row)

            existing = connection.execute(text(f"""
                SELECT {_MISSION_COLUMNS}
                FROM venture_missions
                WHERE idempotency_key = :idempotency_key AND created_by_user_id = :created_by_user_id
            """), {"idempotency_key": idempotency_key, "created_by_user_id": user_id}).mappings().first()

            return dict(existing)

        result = connection.execute(text(f"""
            INSERT INTO venture_missions (
                venture_id, created_by_user_id, title, description,
                mission_type, related_category, source, source_ref,
                resource_ref, status, question_text, why_it_matters
            )
            VALUES (
                :venture_id, :created_by_user_id, :title, :description,
                :mission_type, :related_category, :source, :source_ref,
                :resource_ref, 'active', :question_text, :why_it_matters
            )
            ON CONFLICT (venture_id, source_ref)
                WHERE source <> 'founder_created'
                DO NOTHING
            RETURNING {_MISSION_COLUMNS}
        """), {
            "venture_id": venture_id,
            "created_by_user_id": user_id,
            "title": title,
            "description": description,
            "mission_type": mission_type,
            "related_category": related_category,
            "source": source,
            "source_ref": source_ref,
            "resource_ref": resource_ref,
            "question_text": question_text,
            "why_it_matters": why_it_matters,
        })

        row = result.mappings().first()

        if row is not None:
            return dict(row)

        existing = connection.execute(text(f"""
            SELECT {_MISSION_COLUMNS}
            FROM venture_missions
            WHERE venture_id = :venture_id AND source_ref = :source_ref
        """), {"venture_id": venture_id, "source_ref": source_ref}).mappings().first()

        return dict(existing)


def capture_venture_observation(
    venture_id: int,
    user_id: str,
    title: str,
    learning_summary: str,
    related_category: str | None,
):
    """
    Phase 23 -- Universal Founder Capture V1. "Save what happened" is
    NOT a fourth venture_missions write path -- it is the existing
    create -> record-learning -> complete sequence
    (create_venture_mission() -> record_venture_mission_learning_for_owner()
    -> update_venture_mission_status_for_owner()), collapsed into ONE
    atomic INSERT because a capture's learning_summary is known at
    creation time (unlike an ordinary mission, which is created active
    and reflected on later). This produces the exact same row shape,
    the exact same three get_venture_history() events (action_added,
    learning_recorded, action_completed -- see that endpoint's own
    source-to-event mapping, unchanged by this phase), and is subject to
    the exact same VPS FIREWALL as every other venture_missions write:
    nothing here touches modeled_ventures.assumptions or
    modeled_ventures.model_result, and no caller of this function ever
    calls compute_vps()/update_modeled_venture_for_user(). A capture has
    no code path to a score -- only the founder's own explicit,
    separate PUT /ventures/{id} call (THE VPS FIREWALL, restated in
    app/api.py::update_venture()'s own comment) can do that.

    mission_type is always 'other' (an observation is not a task in the
    existing customer_discovery/validation/pricing/gtm/product/founder/
    economics taxonomy -- see venture_missions' own CHECK constraint;
    forcing a capture into one of those seven would be a false
    classification, not a true one) and source is always
    'founder_created' (both already-valid values; no schema migration
    needed). related_category is the ALREADY-EXISTING free-text display
    label column (create_venture_mission()'s own docstring: "a display
    label... not a foreign key into the scoring engine") -- reused here
    to hold the founder's chosen capture category (e.g.
    "customer_conversation"), never validated against VPS_CATEGORIES,
    exactly as it already isn't for any other mission.

    Deliberately never deduplicated (source_ref stays NULL, same as
    every other founder_created row) -- two captures with identical text
    are two real, distinct observations, not a double-click to collapse.

    Ownership is enforced by the caller (app/api.py), exactly like
    create_venture_mission() -- this function trusts venture_id was
    already confirmed to belong to user_id.
    """
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            INSERT INTO venture_missions (
                venture_id, created_by_user_id, title, description,
                mission_type, related_category, source, source_ref,
                status, learning_summary, learning_recorded_at, completed_at
            )
            VALUES (
                :venture_id, :created_by_user_id, :title, NULL,
                'other', :related_category, 'founder_created', NULL,
                'completed', :learning_summary, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING {_MISSION_COLUMNS}
        """), {
            "venture_id": venture_id,
            "created_by_user_id": user_id,
            "title": title,
            "related_category": related_category,
            "learning_summary": learning_summary,
        })

        row = result.mappings().first()
        return dict(row)


def update_venture_mission_status_for_owner(
    user_id: str, venture_id: int, mission_id: int, new_status: str
):
    """
    Returns the updated row, or None if this mission_id doesn't exist for
    this venture_id/user_id combination -- never revealing whether the
    mission exists for a different user's venture (the JOIN's WHERE
    clause is what makes that structurally impossible, not a Python check
    after the fact).

    completed_at is set the first time status becomes 'completed' and is
    NEVER cleared afterward (dismissing a previously-completed mission,
    while unusual, doesn't erase the historical fact that it was once
    completed) -- CASE WHEN only sets it forward, never back to NULL.
    """
    with engine.begin() as connection:
        result = connection.execute(text("""
            UPDATE venture_missions vm
            SET status = :new_status,
                updated_at = CURRENT_TIMESTAMP,
                completed_at = CASE
                    WHEN :new_status = 'completed' THEN CURRENT_TIMESTAMP
                    ELSE vm.completed_at
                END
            FROM modeled_ventures v
            WHERE vm.venture_id = v.id
              AND vm.id = :mission_id
              AND vm.venture_id = :venture_id
              AND v.user_id = :user_id
            RETURNING vm.id, vm.venture_id, vm.created_by_user_id, vm.title,
                      vm.description, vm.mission_type, vm.related_category,
                      vm.source, vm.source_ref, vm.status, vm.learning_summary,
                      vm.learning_recorded_at, vm.resource_ref, vm.created_at,
                      vm.updated_at, vm.completed_at, vm.question_text,
                      vm.why_it_matters, vm.interpretation_summary,
                      vm.interpretation_limitations, vm.interpretation_generated_at
        """), {
            "mission_id": mission_id,
            "venture_id": venture_id,
            "user_id": user_id,
            "new_status": new_status,
        })

        row = result.mappings().first()
        return dict(row) if row is not None else None


def record_venture_mission_learning_for_owner(
    user_id: str, venture_id: int, mission_id: int, learning_summary: str
):
    """Same ownership-scoped UPDATE...FROM...WHERE shape as
    update_venture_mission_status_for_owner() -- see that function's own
    docstring. Recording a reflection never touches `status`; a founder
    can reflect without completing, or complete without reflecting."""
    with engine.begin() as connection:
        result = connection.execute(text("""
            UPDATE venture_missions vm
            SET learning_summary = :learning_summary,
                learning_recorded_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            FROM modeled_ventures v
            WHERE vm.venture_id = v.id
              AND vm.id = :mission_id
              AND vm.venture_id = :venture_id
              AND v.user_id = :user_id
            RETURNING vm.id, vm.venture_id, vm.created_by_user_id, vm.title,
                      vm.description, vm.mission_type, vm.related_category,
                      vm.source, vm.source_ref, vm.status, vm.learning_summary,
                      vm.learning_recorded_at, vm.resource_ref, vm.created_at,
                      vm.updated_at, vm.completed_at, vm.question_text,
                      vm.why_it_matters, vm.interpretation_summary,
                      vm.interpretation_limitations, vm.interpretation_generated_at
        """), {
            "mission_id": mission_id,
            "venture_id": venture_id,
            "user_id": user_id,
            "learning_summary": learning_summary,
        })

        row = result.mappings().first()
        return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# Phase 16 -- Founder Progress / Venture History V1.
#
# venture_model_updates is narrowly scoped to modeled-venture history --
# NOT a generic event-sourcing platform, NOT a reuse of SPS's own
# score_history (that table's schema/semantics are for canonical,
# real-startup analyses; a modeled venture's VPS is architecturally
# separate from SPS, same reasoning as everywhere else VPS/SPS are kept
# apart). One row is written per explicit, successful PUT
# /ventures/{id} call whose assumptions actually changed -- never for a
# no-op save, never for anything mission-status/learning-related (THE
# VPS FIREWALL, restated: no function in this section, and no caller of
# these functions, ever fires from a mission's status or learning_summary
# changing -- see app/api.py's update_venture() for the one, single call
# site that writes here).
#
# before_/after_ columns are intentionally redundant with what a
# reconstruction FROM modeled_ventures alone could never recover once a
# LATER update overwrites the current row -- this is exactly, and only,
# the minimum persistence gap Part 5 asked to close: modeled_ventures
# itself has never stored anything but its own current state.
def create_venture_model_updates_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS venture_model_updates (
                id SERIAL PRIMARY KEY,
                venture_id INTEGER NOT NULL REFERENCES modeled_ventures(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id),
                before_vps DOUBLE PRECISION,
                after_vps DOUBLE PRECISION,
                before_categories JSONB NOT NULL,
                after_categories JSONB NOT NULL,
                before_assumptions JSONB NOT NULL,
                after_assumptions JSONB NOT NULL,
                -- Part 10's Action -> Learning -> Model Update -> VPS
                -- connection: set only when the update was made from
                -- MissionsSection's own "Update my model ->" flow for a
                -- specific mission (never inferred/guessed after the
                -- fact). ON DELETE SET NULL, not CASCADE: a mission being
                -- deleted (it never is today, but if that ever changes)
                -- must not delete real, already-happened history -- it
                -- just loses the cross-reference.
                related_mission_id INTEGER REFERENCES venture_missions(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

    print("venture_model_updates table created successfully.")


def create_venture_model_update(
    venture_id: int,
    user_id: str,
    before_vps: float | None,
    after_vps: float | None,
    before_categories: list,
    after_categories: list,
    before_assumptions: dict,
    after_assumptions: dict,
    related_mission_id: int | None,
):
    """
    Ownership is enforced by the caller (app/api.py's update_venture(),
    the ONLY call site) having already confirmed venture_id belongs to
    user_id via get_modeled_venture_for_user()/update_modeled_venture_for_user()
    immediately before this runs -- identical trust boundary to
    create_venture_mission()'s own docstring.
    """
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO venture_model_updates (
                venture_id, user_id, before_vps, after_vps,
                before_categories, after_categories,
                before_assumptions, after_assumptions, related_mission_id
            )
            VALUES (
                :venture_id, :user_id, :before_vps, :after_vps,
                :before_categories, :after_categories,
                :before_assumptions, :after_assumptions, :related_mission_id
            )
        """), {
            "venture_id": venture_id,
            "user_id": user_id,
            "before_vps": before_vps,
            "after_vps": after_vps,
            "before_categories": json.dumps(before_categories),
            "after_categories": json.dumps(after_categories),
            "before_assumptions": json.dumps(before_assumptions),
            "after_assumptions": json.dumps(after_assumptions),
            "related_mission_id": related_mission_id,
        })


def list_venture_model_updates_for_owner(user_id: str, venture_id: int):
    """Same ownership-scoped JOIN discipline as
    list_venture_missions_for_owner() -- a modeled_ventures row this
    user_id doesn't own can never match, structurally, not by a
    Python-level check performed after the fact."""
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT mu.id, mu.venture_id, mu.before_vps, mu.after_vps,
                   mu.before_categories, mu.after_categories,
                   mu.before_assumptions, mu.after_assumptions,
                   mu.related_mission_id, mu.created_at
            FROM venture_model_updates mu
            JOIN modeled_ventures v ON v.id = mu.venture_id
            WHERE mu.venture_id = :venture_id AND v.user_id = :user_id
            ORDER BY mu.created_at ASC
        """), {"venture_id": venture_id, "user_id": user_id})

        return [dict(row) for row in result.mappings().all()]


# ---------------------------------------------------------------------------
# Phase 34D -- SIE Build Intelligence Loop V1.
#
# Implements the architecture accepted in
# docs/product/SIE_BUILD_INTELLIGENCE_ARCHITECTURE_V1.md exactly -- see
# that document's §D for the full reasoning behind every design choice
# below, not repeated here. Two new tables (venture_decisions,
# venture_evidence) plus the additive venture_missions columns already
# added above (question_text, why_it_matters, interpretation_summary,
# interpretation_limitations, interpretation_generated_at).
#
# Table creation order matters: venture_decisions is created BEFORE
# venture_evidence because venture_evidence.related_decision_id
# references it.
# ---------------------------------------------------------------------------

def add_venture_intelligence_columns():
    """
    Additive-only migration on the existing venture_missions table --
    every existing row is valid post-migration with these five columns
    simply NULL. Same idempotent-per-column try/except shape as
    add_venture_share_columns() (this file, Phase 27); safe to re-run.
    """
    columns = [
        "question_text TEXT",
        "why_it_matters TEXT",
        "interpretation_summary TEXT",
        "interpretation_limitations TEXT",
        "interpretation_generated_at TIMESTAMP",
    ]

    for column in columns:
        column_name = column.split()[0]
        try:
            with engine.begin() as connection:
                connection.execute(text(
                    f"ALTER TABLE venture_missions ADD COLUMN {column}"
                ))
            print(f"{column_name} column added to venture_missions")
        except Exception as e:
            print(f"{column_name} migration skipped", e)

    # Widen mission_type's CHECK constraint to the fuller test taxonomy
    # (SIE_BUILD_METHODOLOGY_V1.md §10) -- exact same
    # DROP CONSTRAINT IF EXISTS / ADD CONSTRAINT shape as
    # add_pitch_deck_coach_mission_source()'s own widening of the
    # `source` constraint (this file, Phase 11). Every existing value is
    # still valid; this is purely additive and safe to re-run.
    with engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE venture_missions DROP CONSTRAINT IF EXISTS venture_missions_mission_type_check"
        ))
        connection.execute(text("""
            ALTER TABLE venture_missions ADD CONSTRAINT venture_missions_mission_type_check
            CHECK (mission_type IN (
                'customer_discovery', 'validation', 'pricing', 'gtm', 'product',
                'founder', 'economics', 'problem_interview', 'prototype_test',
                'landing_page_test', 'willingness_to_pay_test', 'paid_pilot',
                'pre_sale', 'outbound_test', 'pricing_test', 'channel_test',
                'retention_observation', 'competitive_research', 'unit_economics',
                'other'
            ))
        """))

    print("venture_missions.mission_type widened to the full test taxonomy.")


def create_venture_decisions_table():
    """
    Permanently separates SIE's recommendation from the founder's actual
    choice -- see CreateDecisionRequest's own docstring in
    app/models/venture_missions.py. `evidence_ids` is a plain Postgres
    array (not a join table) -- a short, immutable-once-decided list with
    no attributes of its own worth a separate table, the same judgment
    already made for venture_evidence.superseded_by_id-style corrections
    elsewhere in this design. `supersedes_decision_id` is how a reversal
    is represented: a NEW row, never an edit to the old one (§18
    append-only history).
    """
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS venture_decisions (
                id SERIAL PRIMARY KEY,
                venture_id INTEGER NOT NULL REFERENCES modeled_ventures(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id),
                related_mission_id INTEGER REFERENCES venture_missions(id) ON DELETE SET NULL,
                sie_recommendation TEXT NOT NULL,
                sie_reasoning TEXT NOT NULL,
                founder_choice TEXT NOT NULL,
                founder_rationale TEXT,
                evidence_ids INTEGER[] NOT NULL DEFAULT '{}',
                supersedes_decision_id INTEGER REFERENCES venture_decisions(id) ON DELETE SET NULL,
                -- Phase 34D §17 idempotency: a client-generated key, unique
                -- when present. A retried submission with the same key
                -- returns the existing row instead of creating a duplicate
                -- (see create_venture_decision()'s own docstring).
                idempotency_key TEXT,
                decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS venture_decisions_idempotency_key_idx
            ON venture_decisions (idempotency_key)
            WHERE idempotency_key IS NOT NULL
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS venture_decisions_venture_idx
            ON venture_decisions (venture_id, decided_at DESC)
        """))

    print("venture_decisions table created successfully.")


def create_venture_evidence_table():
    """
    The single genuinely new durable concept this phase adds -- see
    CreateEvidenceRequest's own docstring in app/models/venture_missions.py
    and SIE_BUILD_INTELLIGENCE_ARCHITECTURE_V1.md §D.2. `evidence_type`
    and `provenance` are both CHECK-constrained to the canonical
    vocabularies from SIE_BUILD_METHODOLOGY_V1.md §4/§14 -- no Evidence
    Score, no confidence percentage, anywhere in this schema.
    `superseded_by_id` is a self-reference used exactly like
    venture_decisions.supersedes_decision_id: a correction inserts a NEW
    row and points the OLD row at it; nothing is ever edited in place.
    An Outcome (SIE_BUILD_METHODOLOGY_V1.md §13) is simply a row with
    evidence_type='longitudinal_outcome' and related_decision_id set --
    no separate outcomes table.

    Created AFTER venture_decisions because related_decision_id
    references it.
    """
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS venture_evidence (
                id SERIAL PRIMARY KEY,
                venture_id INTEGER NOT NULL REFERENCES modeled_ventures(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id),
                related_mission_id INTEGER REFERENCES venture_missions(id) ON DELETE SET NULL,
                related_decision_id INTEGER REFERENCES venture_decisions(id) ON DELETE SET NULL,
                evidence_type TEXT NOT NULL CHECK (evidence_type IN (
                    'founder_claim', 'reported_preference', 'observed_behavior',
                    'commitment', 'transaction', 'longitudinal_outcome', 'external_source'
                )),
                statement TEXT NOT NULL,
                provenance TEXT NOT NULL CHECK (provenance IN (
                    'founder_said', 'founder_observed', 'sie_inferred',
                    'sie_calculated', 'external_source', 'still_unknown'
                )),
                source_quote TEXT,
                structured_field_path TEXT,
                structured_value DOUBLE PRECISION,
                relationship TEXT CHECK (relationship IN ('supports', 'contradicts', 'mixed', 'neutral')),
                founder_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
                superseded_by_id INTEGER REFERENCES venture_evidence(id) ON DELETE SET NULL,
                idempotency_key TEXT,
                occurred_at TIMESTAMP,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS venture_evidence_idempotency_key_idx
            ON venture_evidence (idempotency_key)
            WHERE idempotency_key IS NOT NULL
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS venture_evidence_venture_idx
            ON venture_evidence (venture_id, recorded_at DESC)
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS venture_evidence_mission_idx
            ON venture_evidence (related_mission_id)
        """))

    print("venture_evidence table created successfully.")


_EVIDENCE_COLUMNS = """
                id, venture_id, user_id, related_mission_id, related_decision_id,
                evidence_type, statement, provenance, source_quote,
                structured_field_path, structured_value, relationship,
                founder_confirmed, superseded_by_id, occurred_at, recorded_at
"""


def create_venture_evidence(
    venture_id: int,
    user_id: str,
    evidence_type: str,
    statement: str,
    provenance: str,
    related_mission_id: int | None = None,
    related_decision_id: int | None = None,
    source_quote: str | None = None,
    structured_field_path: str | None = None,
    structured_value: float | None = None,
    relationship: str | None = None,
    occurred_at=None,
    idempotency_key: str | None = None,
):
    """
    Ownership of related_mission_id/related_decision_id is enforced by
    the CALLER (app/api.py) via the same ownership-scoped SELECT every
    other mutation in this file already uses BEFORE this runs -- this
    function trusts venture_id/related_mission_id/related_decision_id
    were already confirmed to belong to user_id, exactly like
    create_venture_mission() trusts its own venture_id.

    Idempotent when idempotency_key is provided (Phase 34D §17): a
    retried request with the same key returns the existing row via
    ON CONFLICT ... DO NOTHING + a fallback SELECT, the identical pattern
    create_venture_mission() already uses for its own source_ref dedup.
    Founder-confirmed evidence is always inserted with
    founder_confirmed=True -- there is no code path that persists an
    unconfirmed candidate signal (see app/api.py's own comment on this).
    """
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            INSERT INTO venture_evidence (
                venture_id, user_id, related_mission_id, related_decision_id,
                evidence_type, statement, provenance, source_quote,
                structured_field_path, structured_value, relationship,
                founder_confirmed, occurred_at, idempotency_key
            )
            VALUES (
                :venture_id, :user_id, :related_mission_id, :related_decision_id,
                :evidence_type, :statement, :provenance, :source_quote,
                :structured_field_path, :structured_value, :relationship,
                TRUE, :occurred_at, :idempotency_key
            )
            ON CONFLICT (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL
                DO NOTHING
            RETURNING {_EVIDENCE_COLUMNS}
        """), {
            "venture_id": venture_id,
            "user_id": user_id,
            "related_mission_id": related_mission_id,
            "related_decision_id": related_decision_id,
            "evidence_type": evidence_type,
            "statement": statement,
            "provenance": provenance,
            "source_quote": source_quote,
            "structured_field_path": structured_field_path,
            "structured_value": structured_value,
            "relationship": relationship,
            "occurred_at": occurred_at,
            "idempotency_key": idempotency_key,
        })

        row = result.mappings().first()
        if row is not None:
            return dict(row)

        # idempotency_key collided with an existing row -- return it
        # (idempotent success), never a duplicate, never an error.
        existing = connection.execute(text(f"""
            SELECT {_EVIDENCE_COLUMNS}
            FROM venture_evidence
            WHERE idempotency_key = :idempotency_key AND user_id = :user_id
        """), {"idempotency_key": idempotency_key, "user_id": user_id}).mappings().first()

        return dict(existing)


def list_venture_evidence_for_owner(user_id: str, venture_id: int, related_mission_id: int | None = None):
    """Same ownership-scoped JOIN discipline as list_venture_missions_for_owner()."""
    clause = "AND ve.related_mission_id = :related_mission_id" if related_mission_id is not None else ""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT ve.id, ve.venture_id, ve.user_id, ve.related_mission_id,
                   ve.related_decision_id, ve.evidence_type, ve.statement,
                   ve.provenance, ve.source_quote, ve.structured_field_path,
                   ve.structured_value, ve.relationship, ve.founder_confirmed,
                   ve.superseded_by_id, ve.occurred_at, ve.recorded_at
            FROM venture_evidence ve
            JOIN modeled_ventures v ON v.id = ve.venture_id
            WHERE ve.venture_id = :venture_id AND v.user_id = :user_id
            {clause}
            ORDER BY ve.recorded_at ASC
        """), {"venture_id": venture_id, "user_id": user_id, "related_mission_id": related_mission_id})

        return [dict(row) for row in result.mappings().all()]


def supersede_venture_evidence_for_owner(user_id: str, venture_id: int, evidence_id: int, superseded_by_id: int):
    """
    Correction, never destruction (§18): points the OLD evidence row at
    the NEW one that corrects it. The old row's own statement/type/
    provenance are never rewritten -- a founder (or a future admin view)
    can always see exactly what was originally recorded and what it was
    later corrected to.

    Not yet called from any API endpoint (Phase 34D-A audit, 2026-09):
    the V1 founder-facing loop has no "correct this evidence" UI, so
    nothing invokes this today. Kept rather than removed -- it is the
    correct, ownership-scoped implementation of a requirement the
    accepted architecture explicitly calls for
    (docs/product/SIE_BUILD_INTELLIGENCE_ARCHITECTURE_V1.md §18), not a
    stale draft; wiring a correction UI to it is future scope, not a
    reason to delete working, spec-matching plumbing now.
    """
    with engine.begin() as connection:
        result = connection.execute(text("""
            UPDATE venture_evidence ve
            SET superseded_by_id = :superseded_by_id
            FROM modeled_ventures v
            WHERE ve.venture_id = v.id
              AND ve.id = :evidence_id
              AND ve.venture_id = :venture_id
              AND v.user_id = :user_id
            RETURNING ve.id
        """), {
            "evidence_id": evidence_id,
            "venture_id": venture_id,
            "user_id": user_id,
            "superseded_by_id": superseded_by_id,
        })
        row = result.mappings().first()
        return row is not None


# Phase 34G-A -- Intelligence Resolution + Learning Integrity Hardening,
# §3/§6. The first real caller of the supersede mechanism above: a
# founder-explicit way to say "this specific old result should no longer
# be treated as the current picture" -- covering all four of the
# directive's illustrative reasons (incorrect, superseded, a different
# segment, before a major product change) with ONE small action rather
# than four separate mechanisms, per the directive's own "do not build a
# large evidence-management system" instruction.
#
# Distinguishes EXISTS from CURRENTLY DECISION-DOMINANT: the old row is
# never edited or deleted (still fully queryable via
# list_venture_evidence_for_owner() -- "superseded evidence remains in
# history," §3/§11) -- it is simply excluded from every `superseded_by_id
# IS NULL` view (app/api.py's own `current_evidence` filter, already in
# place since Phase 34D), which is exactly what removes it from the
# recommendation engine's stage_mix computation (app/ai/build_recommendation.py)
# without silently averaging it away or claiming it was wrong.
#
# Both writes happen in ONE transaction -- a resolution note that gets
# created but never actually clears the old row (or vice versa) would be
# a genuinely confusing half-state, unlike the two independent,
# separately-atomic evidence/decision writes documented in
# docs/product/SIE_BUILD_INTELLIGENCE_ARCHITECTURE_V1.md §K (those are
# independent facts; a resolution is fundamentally one fact about one
# other row, so it gets one transaction).
def resolve_venture_evidence_for_owner(
    user_id: str,
    venture_id: int,
    evidence_id: int,
    resolution_note: str,
) -> dict | None:
    """
    Creates a new venture_evidence row holding the founder's own
    resolution note (evidence_type inherited from the row being resolved,
    so it stays part of the same funnel stage; relationship left NULL --
    this row is a note ABOUT resolving a tension, not itself new
    supporting/contradicting evidence) and points the OLD row's
    superseded_by_id at it, atomically. Returns the new row's dict, or
    None if `evidence_id` doesn't exist, isn't owned by this venture/user,
    or is already superseded (idempotent no-op on a repeat call, mirroring
    every other *_for_owner ownership check in this file).
    """
    with engine.begin() as connection:
        old_row = connection.execute(text("""
            SELECT ve.id, ve.evidence_type, ve.superseded_by_id
            FROM venture_evidence ve
            JOIN modeled_ventures v ON v.id = ve.venture_id
            WHERE ve.id = :evidence_id AND ve.venture_id = :venture_id AND v.user_id = :user_id
            FOR UPDATE
        """), {"evidence_id": evidence_id, "venture_id": venture_id, "user_id": user_id}).mappings().first()

        if old_row is None or old_row["superseded_by_id"] is not None:
            return None

        new_row = connection.execute(text("""
            INSERT INTO venture_evidence (
                venture_id, user_id, evidence_type, statement, provenance,
                relationship, founder_confirmed
            )
            VALUES (:venture_id, :user_id, :evidence_type, :statement, 'founder_said', NULL, TRUE)
            RETURNING id, venture_id, user_id, related_mission_id, related_decision_id,
                      evidence_type, statement, provenance, source_quote,
                      structured_field_path, structured_value, relationship,
                      founder_confirmed, superseded_by_id, occurred_at, recorded_at
        """), {
            "venture_id": venture_id,
            "user_id": user_id,
            "evidence_type": old_row["evidence_type"],
            "statement": resolution_note,
        }).mappings().first()

        connection.execute(text("""
            UPDATE venture_evidence SET superseded_by_id = :new_id WHERE id = :old_id
        """), {"new_id": new_row["id"], "old_id": old_row["id"]})

        return dict(new_row)


# ---------------------------------------------------------------------------
# Phase 35B -- Financial State Persistence + Runway Engine V1. See
# docs/product/SIE_FINANCIAL_DECISION_ENGINE_V2.md for the full design.
#
# APPEND-ONLY, deliberately -- mirrors venture_model_updates' own
# before/after-snapshot precedent, never update-in-place. A founder
# changing cash from $500K to $450K INSERTs a new row; the $500K row is
# never touched. "Current financial state" is simply the most recent row
# by (as_of_date DESC, recorded_at DESC) -- there is no separate
# "current state" table to keep in sync, and no risk of silently
# overwriting the only copy of a prior snapshot (§12 of the directive).
#
# Every money column is NULLABLE and stores INTEGER CENTS -- NULL means
# "unknown," never zero (§15 of the directive: "unknown is not zero").
# An explicit zero is stored as the integer 0, indistinguishable from any
# other real value, and distinguishable from NULL at every layer (SQL,
# Python, JSON, the calculation engine in app/ai/financial_engine.py).
# This is the same "no fake precision" discipline
# dashboard/lib/fundraising/rational.ts already established for cap-table
# math, applied to a domain (money in, money out) simple enough that
# plain integer cents -- no Rational/bigint machinery -- is sufficient;
# see SIE_FINANCIAL_DECISION_ENGINE_V2.md's "money representation"
# section for the full reasoning.
#
# Provenance (Phase 35A §11): every field persisted by this phase is,
# structurally, FOUNDER_ENTERED actual data -- there is no code path that
# writes a snapshot row from anything else (no AI estimate, no imported
# feed, no scenario). Rather than a speculative per-field provenance
# column with only one real value in it today, that contract is encoded
# structurally: this is the ONLY write path into this table
# (create_venture_financial_snapshot(), called from exactly one endpoint,
# POST /ventures/{id}/financials), so every row's provenance is knowable
# without a column. HISTORICAL_ACTUAL/IMPORTED/PLANNED/ASSUMPTION/
# SIE_CALCULATED are documented, future values -- see the doc's own
# "provenance" section for exactly what would need to change to add them
# (most likely a `provenance` column on this same table, or a sibling
# `venture_financial_line_items` table per the 35A design, once a second
# write path -- a scenario, a planned hire -- actually exists).
def create_venture_financial_snapshots_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS venture_financial_snapshots (
                id SERIAL PRIMARY KEY,
                venture_id INTEGER NOT NULL REFERENCES modeled_ventures(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id),
                as_of_date DATE NOT NULL,
                cash_balance_cents BIGINT,
                monthly_recurring_revenue_cents BIGINT,
                monthly_non_recurring_revenue_cents BIGINT,
                payroll_cents BIGINT,
                contractors_cents BIGINT,
                software_cents BIGINT,
                marketing_cents BIGINT,
                rent_cents BIGINT,
                professional_services_cents BIGINT,
                other_expenses_cents BIGINT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS venture_financial_snapshots_venture_idx
            ON venture_financial_snapshots (venture_id, as_of_date DESC, recorded_at DESC)
        """))
    print("venture_financial_snapshots table created successfully.")


# Phase 40A-FIX -- Private Beta P1 Hardening. Additive column on an
# already-populated table -- every existing snapshot starts with NULL
# ("this row predates request-identity idempotency," the correct honest
# default). Identical shape/index pattern to venture_decisions'/
# venture_financial_commitments' own idempotency_key: a nullable TEXT
# column plus a unique index scoped to non-null values only, so any
# number of pre-existing (and future, deliberately keyless) rows can
# keep NULL without colliding with each other.
def add_financial_snapshot_idempotency_column():
    """
    The unique index is scoped to (user_id, idempotency_key), NOT a bare
    idempotency_key -- deliberately, per a security finding made while
    testing this exact phase's own required cross-user regression case.
    idempotency_key is entirely client-supplied, unvalidated free text;
    a bare-key unique index (plus a correspondingly unscoped fallback
    SELECT) would let User B submit a key equal to one User A already
    used and receive User A's row back. Scoping by user_id makes that
    structurally impossible: the SAME literal key string is a completely
    independent value for every different user_id.
    """
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                ALTER TABLE venture_financial_snapshots
                ADD COLUMN idempotency_key TEXT
            """))
    except Exception as e:
        print("venture_financial_snapshots.idempotency_key migration skipped", e)

    # DROP + CREATE (by name) rather than CREATE ... IF NOT EXISTS alone
    # -- an index name existing already does not mean its DEFINITION is
    # the corrected one, and "IF NOT EXISTS" only checks the name. Safe
    # to re-run indefinitely: dropping a nonexistent index and creating
    # an already-correct one are both no-ops.
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP INDEX IF EXISTS venture_financial_snapshots_idempotency_key_idx"))
            connection.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS venture_financial_snapshots_idempotency_key_idx
                ON venture_financial_snapshots (user_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL
            """))
        print("venture_financial_snapshots.idempotency_key added.")
    except Exception as e:
        print("venture_financial_snapshots.idempotency_key_idx migration skipped", e)


_FINANCIAL_SNAPSHOT_COLUMNS = """
                id, venture_id, user_id, as_of_date, cash_balance_cents,
                monthly_recurring_revenue_cents, monthly_non_recurring_revenue_cents,
                payroll_cents, contractors_cents, software_cents, marketing_cents,
                rent_cents, professional_services_cents, other_expenses_cents, recorded_at
"""

_FINANCIAL_SNAPSHOT_COLUMNS_QUALIFIED = """
                vfs.id, vfs.venture_id, vfs.user_id, vfs.as_of_date, vfs.cash_balance_cents,
                vfs.monthly_recurring_revenue_cents, vfs.monthly_non_recurring_revenue_cents,
                vfs.payroll_cents, vfs.contractors_cents, vfs.software_cents, vfs.marketing_cents,
                vfs.rent_cents, vfs.professional_services_cents, vfs.other_expenses_cents, vfs.recorded_at
"""


def create_venture_financial_snapshot(
    venture_id: int,
    user_id: str,
    as_of_date,
    cash_balance_cents: int | None = None,
    monthly_recurring_revenue_cents: int | None = None,
    monthly_non_recurring_revenue_cents: int | None = None,
    payroll_cents: int | None = None,
    contractors_cents: int | None = None,
    software_cents: int | None = None,
    marketing_cents: int | None = None,
    rent_cents: int | None = None,
    professional_services_cents: int | None = None,
    other_expenses_cents: int | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """
    Ownership of venture_id is enforced by the CALLER (app/api.py) via the
    same ownership-scoped SELECT every other mutation in this file already
    uses BEFORE this runs -- identical discipline to create_venture_evidence().
    Always an INSERT -- there is no update path for this table (see this
    section's own module comment above).

    Phase 40A-FIX: idempotent when idempotency_key is provided -- the
    identical ON CONFLICT + fallback-SELECT pattern create_venture_decision()/
    create_venture_evidence()/create_venture_financial_commitment() already
    use. A retried request with the same key returns the EXISTING row,
    never a second, duplicate historical snapshot. Omitting the key (the
    default) reproduces this function's own prior behavior exactly --
    always a fresh INSERT, byte-identical for every caller that hasn't
    been updated to pass one.
    """
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            INSERT INTO venture_financial_snapshots (
                venture_id, user_id, as_of_date, cash_balance_cents,
                monthly_recurring_revenue_cents, monthly_non_recurring_revenue_cents,
                payroll_cents, contractors_cents, software_cents, marketing_cents,
                rent_cents, professional_services_cents, other_expenses_cents, idempotency_key
            )
            VALUES (
                :venture_id, :user_id, :as_of_date, :cash_balance_cents,
                :monthly_recurring_revenue_cents, :monthly_non_recurring_revenue_cents,
                :payroll_cents, :contractors_cents, :software_cents, :marketing_cents,
                :rent_cents, :professional_services_cents, :other_expenses_cents, :idempotency_key
            )
            ON CONFLICT (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL
                DO NOTHING
            RETURNING {_FINANCIAL_SNAPSHOT_COLUMNS}
        """), {
            "venture_id": venture_id,
            "user_id": user_id,
            "as_of_date": as_of_date,
            "cash_balance_cents": cash_balance_cents,
            "monthly_recurring_revenue_cents": monthly_recurring_revenue_cents,
            "monthly_non_recurring_revenue_cents": monthly_non_recurring_revenue_cents,
            "payroll_cents": payroll_cents,
            "contractors_cents": contractors_cents,
            "software_cents": software_cents,
            "marketing_cents": marketing_cents,
            "rent_cents": rent_cents,
            "professional_services_cents": professional_services_cents,
            "other_expenses_cents": other_expenses_cents,
            "idempotency_key": idempotency_key,
        })

        row = result.mappings().first()
        if row is not None:
            return dict(row)

        existing = connection.execute(text(f"""
            SELECT {_FINANCIAL_SNAPSHOT_COLUMNS}
            FROM venture_financial_snapshots
            WHERE idempotency_key = :idempotency_key AND user_id = :user_id
        """), {"idempotency_key": idempotency_key, "user_id": user_id}).mappings().first()

        return dict(existing)


def get_latest_venture_financial_snapshot_for_owner(user_id: str, venture_id: int) -> dict | None:
    """The "current" financial state -- the most recent snapshot by
    (as_of_date, recorded_at), never a separate "current state" row."""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {_FINANCIAL_SNAPSHOT_COLUMNS_QUALIFIED}
            FROM venture_financial_snapshots vfs
            JOIN modeled_ventures v ON v.id = vfs.venture_id
            WHERE vfs.venture_id = :venture_id AND v.user_id = :user_id
            ORDER BY vfs.as_of_date DESC, vfs.recorded_at DESC
            LIMIT 1
        """), {"venture_id": venture_id, "user_id": user_id})
        row = result.mappings().first()
        return dict(row) if row else None


def list_venture_financial_snapshots_for_owner(user_id: str, venture_id: int) -> list[dict]:
    """Every snapshot ever recorded for this venture, oldest first -- the
    "prior financial information remains recoverable" guarantee (§12/§23
    of the directive), not yet exposed as a dedicated History UI, but
    fully queryable and tested (see test_venture_financials.py's own
    history-safety test)."""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {_FINANCIAL_SNAPSHOT_COLUMNS_QUALIFIED}
            FROM venture_financial_snapshots vfs
            JOIN modeled_ventures v ON v.id = vfs.venture_id
            WHERE vfs.venture_id = :venture_id AND v.user_id = :user_id
            ORDER BY vfs.as_of_date ASC, vfs.recorded_at ASC
        """), {"venture_id": venture_id, "user_id": user_id})
        return [dict(row) for row in result.mappings().all()]


# ---------------------------------------------------------------------------
# Phase 35C -- Hiring + Operating Plan Engine V1. See
# docs/product/SIE_FINANCIAL_DECISION_ENGINE_V2.md for the full design.
#
# A dedicated `venture_hire_plans` table rather than the generic
# `venture_financial_line_items` Phase 35A originally sketched -- with
# exactly one plan TYPE in this phase (a hire), a `kind` discriminator
# column carrying one live value would be premature abstraction. The
# natural evolution once revenue/cost-cut/financing plan types exist
# (§20 of this phase's directive explicitly defers all of them) is either
# a sibling table per type or a widened version of this one with a `kind`
# column added -- a decision for whichever future phase actually needs
# it, not guessed here.
#
# UPDATE-IN-PLACE, deliberately -- mirrors venture_missions.status/
# learning_summary's own existing update-in-place precedent
# (SIE_BUILD_INTELLIGENCE_ARCHITECTURE_V1.md §D.1), not
# venture_evidence's append-only superseded_by_id correction pattern. A
# planned hire is an ACTIVELY-EDITED DRAFT the founder is still shaping
# ("what if I offer a lower salary?"), not an immutable observation
# already made -- editing it in place is the same judgment call Build
# already made for a mission's own in-flight fields. `status` transitions
# (planned -> cancelled/actualized) are the same UPDATE, never a DELETE:
# the row -- and the fact that a hire was once planned at all -- always
# remains queryable. `updated_at` gives a minimal, honest "this changed
# recently" signal without a full field-level changelog (§18 of the
# directive: "do not build an elaborate audit UI").
def create_venture_hire_plans_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS venture_hire_plans (
                id SERIAL PRIMARY KEY,
                venture_id INTEGER NOT NULL REFERENCES modeled_ventures(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id),
                role TEXT NOT NULL,
                employment_type TEXT NOT NULL CHECK (employment_type IN ('employee', 'contractor')),
                annual_salary_cents BIGINT,
                burden_percent DOUBLE PRECISION,
                monthly_cost_cents BIGINT,
                one_time_cost_cents BIGINT,
                start_date DATE NOT NULL,
                end_date DATE,
                status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'cancelled', 'actualized')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS venture_hire_plans_venture_idx
            ON venture_hire_plans (venture_id, status)
        """))
    print("venture_hire_plans table created successfully.")


# Phase 35D -- Operating Scenarios + Financial Plan Reconciliation V1, §13.
# Additive column, safe on an existing table with real rows (every
# existing hire plan simply starts with this NULL -- "never reconciled
# against any snapshot yet," the correct honest default). Records which
# financial snapshot (by id) a founder has already answered the
# reconciliation question against for THIS plan -- see
# list_pending_reconciliation_for_owner()'s own docstring for exactly how
# this prevents re-asking about a plan the founder already resolved,
# while still asking again if a NEWER snapshot arrives.
def add_hire_plan_reconciliation_column():
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                ALTER TABLE venture_hire_plans
                ADD COLUMN last_reconciled_snapshot_id INTEGER REFERENCES venture_financial_snapshots(id) ON DELETE SET NULL
            """))
        print("venture_hire_plans.last_reconciled_snapshot_id added.")
    except Exception as e:
        print("last_reconciled_snapshot_id migration skipped", e)


_HIRE_PLAN_COLUMNS_QUALIFIED = """
                vhp.id, vhp.venture_id, vhp.user_id, vhp.role, vhp.employment_type,
                vhp.annual_salary_cents, vhp.burden_percent, vhp.monthly_cost_cents,
                vhp.one_time_cost_cents, vhp.start_date, vhp.end_date, vhp.status,
                vhp.created_at, vhp.updated_at, vhp.last_reconciled_snapshot_id
"""


def create_venture_hire_plan(
    venture_id: int,
    user_id: str,
    role: str,
    employment_type: str,
    start_date,
    annual_salary_cents: int | None = None,
    burden_percent: float | None = None,
    monthly_cost_cents: int | None = None,
    one_time_cost_cents: int | None = None,
    end_date=None,
) -> dict:
    """Ownership of venture_id is enforced by the CALLER (app/api.py),
    identical discipline to create_venture_financial_snapshot()."""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            INSERT INTO venture_hire_plans (
                venture_id, user_id, role, employment_type, annual_salary_cents,
                burden_percent, monthly_cost_cents, one_time_cost_cents, start_date, end_date
            )
            VALUES (
                :venture_id, :user_id, :role, :employment_type, :annual_salary_cents,
                :burden_percent, :monthly_cost_cents, :one_time_cost_cents, :start_date, :end_date
            )
            RETURNING {_HIRE_PLAN_COLUMNS_QUALIFIED.replace("vhp.", "")}
        """), {
            "venture_id": venture_id, "user_id": user_id, "role": role,
            "employment_type": employment_type, "annual_salary_cents": annual_salary_cents,
            "burden_percent": burden_percent, "monthly_cost_cents": monthly_cost_cents,
            "one_time_cost_cents": one_time_cost_cents, "start_date": start_date, "end_date": end_date,
        })
        return dict(result.mappings().first())


def list_venture_hire_plans_for_owner(user_id: str, venture_id: int, status: str | None = None) -> list[dict]:
    clause = "AND vhp.status = :status" if status is not None else ""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {_HIRE_PLAN_COLUMNS_QUALIFIED}
            FROM venture_hire_plans vhp
            JOIN modeled_ventures v ON v.id = vhp.venture_id
            WHERE vhp.venture_id = :venture_id AND v.user_id = :user_id
            {clause}
            ORDER BY vhp.start_date ASC, vhp.created_at ASC
        """), {"venture_id": venture_id, "user_id": user_id, "status": status})
        return [dict(row) for row in result.mappings().all()]


def get_venture_hire_plan_for_owner(user_id: str, venture_id: int, hire_plan_id: int) -> dict | None:
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {_HIRE_PLAN_COLUMNS_QUALIFIED}
            FROM venture_hire_plans vhp
            JOIN modeled_ventures v ON v.id = vhp.venture_id
            WHERE vhp.id = :hire_plan_id AND vhp.venture_id = :venture_id AND v.user_id = :user_id
        """), {"hire_plan_id": hire_plan_id, "venture_id": venture_id, "user_id": user_id})
        row = result.mappings().first()
        return dict(row) if row else None


# Phase 40A-FIX -- Private Beta P1 Hardening. Batched sibling of
# get_venture_hire_plan_for_owner() -- ownership (venture_id + user_id)
# is enforced IN THE QUERY ITSELF, identical to every single-id lookup
# in this file, not by fetching everything and filtering in Python.
# Callers that previously issued one query per referenced id (scenario
# building, scenario/commitment ownership validation) now issue exactly
# one query for the whole batch. Returns [] immediately for an empty
# id list -- `= ANY('{}')` is legal SQL but a wasted round trip.
def list_venture_hire_plans_for_owner_by_ids(
    user_id: str, venture_id: int, hire_plan_ids: list[int], status: str | None = None
) -> list[dict]:
    if not hire_plan_ids:
        return []
    clause = "AND vhp.status = :status" if status is not None else ""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {_HIRE_PLAN_COLUMNS_QUALIFIED}
            FROM venture_hire_plans vhp
            JOIN modeled_ventures v ON v.id = vhp.venture_id
            WHERE vhp.id = ANY(:hire_plan_ids) AND vhp.venture_id = :venture_id AND v.user_id = :user_id
            {clause}
        """), {"hire_plan_ids": hire_plan_ids, "venture_id": venture_id, "user_id": user_id, "status": status})
        return [dict(row) for row in result.mappings().all()]


def update_venture_hire_plan_for_owner(user_id: str, venture_id: int, hire_plan_id: int, **fields) -> dict | None:
    """Partial update-in-place -- `fields` is whatever the caller
    (app/api.py) determined should change, already validated. Always sets
    updated_at. Returns None if the row doesn't exist or isn't owned by
    this venture/user (ownership re-checked in the same statement, never
    a separate check-then-trust step)."""
    if not fields:
        return get_venture_hire_plan_for_owner(user_id, venture_id, hire_plan_id)

    set_clause = ", ".join(f"{key} = :{key}" for key in fields)
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            UPDATE venture_hire_plans vhp
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            FROM modeled_ventures v
            WHERE vhp.venture_id = v.id
              AND vhp.id = :hire_plan_id
              AND vhp.venture_id = :venture_id
              AND v.user_id = :user_id
            RETURNING {_HIRE_PLAN_COLUMNS_QUALIFIED}
        """), {**fields, "hire_plan_id": hire_plan_id, "venture_id": venture_id, "user_id": user_id})
        row = result.mappings().first()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Phase 35D -- Operating Scenarios + Financial Plan Reconciliation V1. See
# docs/product/SIE_FINANCIAL_DECISION_ENGINE_V2.md.
#
# venture_financial_plans covers the two NEW plan types this phase adds
# (revenue_target, expense_change) -- one table, not two, since both
# share an identical shape (a signed/absolute amount, a category only
# meaningful for expense_change, a dated window, the same
# planned/cancelled/actualized lifecycle as venture_hire_plans). This is
# deliberately NOT a merge with venture_hire_plans itself: hiring's own
# fields (employment_type, salary, burden) have no equivalent here, and
# Phase 35C's own directive explicitly forbade refactoring working hire
# persistence "merely for theoretical purity." A `plan_type` discriminator
# column is justified NOW specifically because there are two new,
# genuinely interchangeable-shaped types being added at once -- the exact
# threshold 35A/35C's own commentary already named for when this becomes
# worth it.
def create_venture_financial_plans_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS venture_financial_plans (
                id SERIAL PRIMARY KEY,
                venture_id INTEGER NOT NULL REFERENCES modeled_ventures(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id),
                plan_type TEXT NOT NULL CHECK (plan_type IN ('revenue_target', 'expense_change')),
                label TEXT NOT NULL,
                category TEXT CHECK (category IN (
                    'payroll', 'contractors', 'software', 'marketing', 'rent', 'professional_services', 'other'
                )),
                amount_cents BIGINT NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE,
                status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'cancelled', 'actualized')),
                last_reconciled_snapshot_id INTEGER REFERENCES venture_financial_snapshots(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS venture_financial_plans_venture_idx
            ON venture_financial_plans (venture_id, status)
        """))
    print("venture_financial_plans table created successfully.")


_FINANCIAL_PLAN_COLUMNS_QUALIFIED = """
                vfp.id, vfp.venture_id, vfp.user_id, vfp.plan_type, vfp.label, vfp.category,
                vfp.amount_cents, vfp.start_date, vfp.end_date, vfp.status,
                vfp.last_reconciled_snapshot_id, vfp.created_at, vfp.updated_at
"""


def create_venture_financial_plan(
    venture_id: int,
    user_id: str,
    plan_type: str,
    label: str,
    amount_cents: int,
    start_date,
    category: str | None = None,
    end_date=None,
) -> dict:
    """Ownership of venture_id, and the §7 never-negative-expense
    validation, are both enforced by the CALLER (app/api.py) -- identical
    discipline to create_venture_hire_plan()."""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            INSERT INTO venture_financial_plans (
                venture_id, user_id, plan_type, label, category, amount_cents, start_date, end_date
            )
            VALUES (
                :venture_id, :user_id, :plan_type, :label, :category, :amount_cents, :start_date, :end_date
            )
            RETURNING {_FINANCIAL_PLAN_COLUMNS_QUALIFIED.replace("vfp.", "")}
        """), {
            "venture_id": venture_id, "user_id": user_id, "plan_type": plan_type, "label": label,
            "category": category, "amount_cents": amount_cents, "start_date": start_date, "end_date": end_date,
        })
        return dict(result.mappings().first())


def list_venture_financial_plans_for_owner(user_id: str, venture_id: int, status: str | None = None) -> list[dict]:
    clause = "AND vfp.status = :status" if status is not None else ""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {_FINANCIAL_PLAN_COLUMNS_QUALIFIED}
            FROM venture_financial_plans vfp
            JOIN modeled_ventures v ON v.id = vfp.venture_id
            WHERE vfp.venture_id = :venture_id AND v.user_id = :user_id
            {clause}
            ORDER BY vfp.start_date ASC, vfp.created_at ASC
        """), {"venture_id": venture_id, "user_id": user_id, "status": status})
        return [dict(row) for row in result.mappings().all()]


def get_venture_financial_plan_for_owner(user_id: str, venture_id: int, plan_id: int) -> dict | None:
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {_FINANCIAL_PLAN_COLUMNS_QUALIFIED}
            FROM venture_financial_plans vfp
            JOIN modeled_ventures v ON v.id = vfp.venture_id
            WHERE vfp.id = :plan_id AND vfp.venture_id = :venture_id AND v.user_id = :user_id
        """), {"plan_id": plan_id, "venture_id": venture_id, "user_id": user_id})
        row = result.mappings().first()
        return dict(row) if row else None


# Phase 40A-FIX -- Private Beta P1 Hardening. Batched sibling of
# get_venture_financial_plan_for_owner() -- see
# list_venture_hire_plans_for_owner_by_ids()'s own docstring immediately
# above for the exact same reasoning, applied here to
# venture_financial_plans.
def list_venture_financial_plans_for_owner_by_ids(
    user_id: str, venture_id: int, plan_ids: list[int], status: str | None = None
) -> list[dict]:
    if not plan_ids:
        return []
    clause = "AND vfp.status = :status" if status is not None else ""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {_FINANCIAL_PLAN_COLUMNS_QUALIFIED}
            FROM venture_financial_plans vfp
            JOIN modeled_ventures v ON v.id = vfp.venture_id
            WHERE vfp.id = ANY(:plan_ids) AND vfp.venture_id = :venture_id AND v.user_id = :user_id
            {clause}
        """), {"plan_ids": plan_ids, "venture_id": venture_id, "user_id": user_id, "status": status})
        return [dict(row) for row in result.mappings().all()]


def update_venture_financial_plan_for_owner(user_id: str, venture_id: int, plan_id: int, **fields) -> dict | None:
    """Update-in-place, identical discipline and identical reasoning to
    update_venture_hire_plan_for_owner() -- see that function's own
    docstring."""
    if not fields:
        return get_venture_financial_plan_for_owner(user_id, venture_id, plan_id)

    set_clause = ", ".join(f"{key} = :{key}" for key in fields)
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            UPDATE venture_financial_plans vfp
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            FROM modeled_ventures v
            WHERE vfp.venture_id = v.id
              AND vfp.id = :plan_id
              AND vfp.venture_id = :venture_id
              AND v.user_id = :user_id
            RETURNING {_FINANCIAL_PLAN_COLUMNS_QUALIFIED}
        """), {**fields, "plan_id": plan_id, "venture_id": venture_id, "user_id": user_id})
        row = result.mappings().first()
        return dict(row) if row else None


# venture_financial_scenarios -- a NAMED SELECTION of plan ids, never a
# frozen copy of actual state. `hire_plan_ids`/`financial_plan_ids` are
# plain Postgres arrays, mirroring venture_decisions.evidence_ids' own
# precedent (db.py, Phase 34D) -- "a short, immutable-once-decided list
# with no need for its own queryable attributes," the same judgment
# reapplied here for "which plans does this scenario include." See
# docs/product/SIE_FINANCIAL_DECISION_ENGINE_V2.md's own "scenario
# baseline semantics" section for why NOTHING about the actual financial
# state is copied into this table -- a scenario's numeric result is
# always recomputed live, at read time, against whatever the LATEST
# actual snapshot and the SELECTED plans' CURRENT values currently say.
def create_venture_financial_scenarios_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS venture_financial_scenarios (
                id SERIAL PRIMARY KEY,
                venture_id INTEGER NOT NULL REFERENCES modeled_ventures(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id),
                name TEXT NOT NULL,
                hire_plan_ids INTEGER[] NOT NULL DEFAULT '{}',
                financial_plan_ids INTEGER[] NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS venture_financial_scenarios_venture_idx
            ON venture_financial_scenarios (venture_id)
        """))
    print("venture_financial_scenarios table created successfully.")


_SCENARIO_COLUMNS_QUALIFIED = """
                vfs.id, vfs.venture_id, vfs.user_id, vfs.name,
                vfs.hire_plan_ids, vfs.financial_plan_ids, vfs.created_at, vfs.updated_at
"""


def create_venture_financial_scenario(
    venture_id: int, user_id: str, name: str, hire_plan_ids: list[int], financial_plan_ids: list[int]
) -> dict:
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            INSERT INTO venture_financial_scenarios (venture_id, user_id, name, hire_plan_ids, financial_plan_ids)
            VALUES (:venture_id, :user_id, :name, :hire_plan_ids, :financial_plan_ids)
            RETURNING {_SCENARIO_COLUMNS_QUALIFIED.replace("vfs.", "")}
        """), {
            "venture_id": venture_id, "user_id": user_id, "name": name,
            "hire_plan_ids": hire_plan_ids, "financial_plan_ids": financial_plan_ids,
        })
        return dict(result.mappings().first())


def list_venture_financial_scenarios_for_owner(user_id: str, venture_id: int) -> list[dict]:
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {_SCENARIO_COLUMNS_QUALIFIED}
            FROM venture_financial_scenarios vfs
            JOIN modeled_ventures v ON v.id = vfs.venture_id
            WHERE vfs.venture_id = :venture_id AND v.user_id = :user_id
            ORDER BY vfs.created_at ASC
        """), {"venture_id": venture_id, "user_id": user_id})
        return [dict(row) for row in result.mappings().all()]


def get_venture_financial_scenario_for_owner(user_id: str, venture_id: int, scenario_id: int) -> dict | None:
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {_SCENARIO_COLUMNS_QUALIFIED}
            FROM venture_financial_scenarios vfs
            JOIN modeled_ventures v ON v.id = vfs.venture_id
            WHERE vfs.id = :scenario_id AND vfs.venture_id = :venture_id AND v.user_id = :user_id
        """), {"scenario_id": scenario_id, "venture_id": venture_id, "user_id": user_id})
        row = result.mappings().first()
        return dict(row) if row else None


def update_venture_financial_scenario_for_owner(user_id: str, venture_id: int, scenario_id: int, **fields) -> dict | None:
    if not fields:
        return get_venture_financial_scenario_for_owner(user_id, venture_id, scenario_id)
    set_clause = ", ".join(f"{key} = :{key}" for key in fields)
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            UPDATE venture_financial_scenarios vfs
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            FROM modeled_ventures v
            WHERE vfs.venture_id = v.id
              AND vfs.id = :scenario_id
              AND vfs.venture_id = :venture_id
              AND v.user_id = :user_id
            RETURNING {_SCENARIO_COLUMNS_QUALIFIED}
        """), {**fields, "scenario_id": scenario_id, "venture_id": venture_id, "user_id": user_id})
        row = result.mappings().first()
        return dict(row) if row else None


def delete_venture_financial_scenario_for_owner(user_id: str, venture_id: int, scenario_id: int) -> bool:
    """A scenario is a saved SELECTION/query, not a fact about the world
    (unlike a plan or evidence row) -- deleting one is safe and carries no
    history obligation."""
    with engine.begin() as connection:
        result = connection.execute(text("""
            DELETE FROM venture_financial_scenarios vfs
            USING modeled_ventures v
            WHERE vfs.venture_id = v.id
              AND vfs.id = :scenario_id
              AND vfs.venture_id = :venture_id
              AND v.user_id = :user_id
            RETURNING vfs.id
        """), {"scenario_id": scenario_id, "venture_id": venture_id, "user_id": user_id})
        return result.mappings().first() is not None


# Phase 35D §13 reconciliation query: "planned" hires/plans whose
# start_date is already at-or-before the LATEST snapshot's own as_of_date
# (i.e., should plausibly already be reflected in what the founder just
# entered) AND have not already been reconciled against THIS SPECIFIC
# snapshot. Re-surfaces on a NEWER snapshot even for a plan the founder
# already dismissed against an OLDER one -- correct, because a newer
# snapshot is new information that could change the answer.
def list_pending_reconciliation_for_owner(user_id: str, venture_id: int, latest_snapshot_id: int, as_of_date) -> dict:
    hires = list_venture_hire_plans_for_owner(user_id, venture_id, status="planned")
    plans = list_venture_financial_plans_for_owner(user_id, venture_id, status="planned")
    pending_hires = [
        h for h in hires
        if h["start_date"] <= as_of_date and h["last_reconciled_snapshot_id"] != latest_snapshot_id
    ]
    pending_plans = [
        p for p in plans
        if p["start_date"] <= as_of_date and p["last_reconciled_snapshot_id"] != latest_snapshot_id
    ]
    return {"hire_plans": pending_hires, "financial_plans": pending_plans}


# Phase 40A-FIX -- Private Beta P1 Hardening / Security Correction.
# Discovered while implementing this phase's own P1 #2 (idempotency for
# financial snapshots/missions) and confirmed by this phase's own
# required cross-user regression test: venture_decisions,
# venture_evidence, and venture_financial_commitments each originally
# enforced idempotency_key uniqueness GLOBALLY -- a bare `(idempotency_key)
# WHERE idempotency_key IS NOT NULL` index, paired with an equally
# unscoped fallback SELECT (`WHERE idempotency_key = :idempotency_key`,
# no user_id filter). idempotency_key is entirely client-supplied,
# unvalidated free text -- an authenticated User B submitting the exact
# same key string User A had already used (guessed, reused, or simply
# coincidentally identical) would receive User A's own row back from the
# fallback SELECT. That is a real cross-tenant data exposure, not a
# theoretical one, and is exactly what this phase's own directive asked
# to re-verify ("User B cannot replay User A's idempotency key to obtain
# User A's resource").
#
# Fix: widen each unique index to (user_id, idempotency_key). Safe to
# migrate onto existing data -- global uniqueness always implies
# per-user uniqueness, so no existing row can violate the new, more
# permissive constraint. Each function's own fallback SELECT is updated
# in the SAME phase to add "AND user_id = :user_id" (see
# create_venture_evidence()/create_venture_financial_commitment()/
# create_venture_decision()'s own fallback queries). This phase's own
# two NEW idempotency mechanisms (venture_financial_snapshots,
# venture_missions) were written with the correct scoping from the
# start -- see add_financial_snapshot_idempotency_column()'s and
# add_mission_idempotency_column()'s own docstrings.
def fix_idempotency_key_scoping_to_prevent_cross_user_replay():
    fixes = [
        ("venture_decisions_idempotency_key_idx", "venture_decisions"),
        ("venture_evidence_idempotency_key_idx", "venture_evidence"),
        ("venture_financial_commitments_idempotency_key_idx", "venture_financial_commitments"),
    ]
    for index_name, table_name in fixes:
        try:
            with engine.begin() as connection:
                connection.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
                connection.execute(text(f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS {index_name}
                    ON {table_name} (user_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL
                """))
            print(f"{index_name} re-scoped to (user_id, idempotency_key).")
        except Exception as e:
            print(f"{index_name} re-scoping skipped", e)


# ---------------------------------------------------------------------------
# Phase 38D-A -- Financial Commitment Persistence + Frozen Expectation V1.
# See docs/product/SIE_COMMITTED_PLAN_LEARNING_ARCHITECTURE_V1.md for the
# accepted architecture (§24 "minimum schema").
#
# The ONE new object the 38D architecture calls for. Deliberately NOT a
# frozen copy of venture_financial_scenarios (that table stays exactly
# what it already is -- a hypothetical, always-live-recomputed named
# selection, per its own docstring above) -- this is a SEPARATE,
# independent, append-only fact: "the founder explicitly committed to
# this financial expectation on this date." `plan_snapshot` and
# `expected_monthly` are JSONB because both are written EXACTLY ONCE,
# never queried by a SQL predicate, and always read back whole -- the
# same "avoid five tables for one workflow" judgment already applied to
# venture_financial_scenarios.hire_plan_ids/financial_plan_ids (plain
# arrays, not a join table).
#
# `status`/`supersedes_commitment_id` mirror venture_decisions' own
# already-shipped append-only reversal pattern exactly (self-FK, a NEW
# row on reversal, never an edit to the old one) -- included in the
# schema now per the accepted architecture, but NO code path in this
# phase ever sets status to anything but 'active' or writes
# supersedes_commitment_id (38D-A directive §3: "creation is the
# important operation" -- supersede/abandon lifecycle actions are
# explicitly deferred, not needed to safely create a commitment).
def create_venture_financial_commitments_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS venture_financial_commitments (
                id SERIAL PRIMARY KEY,
                venture_id INTEGER NOT NULL REFERENCES modeled_ventures(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id),
                committed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                -- NOT NULL + RESTRICT, not SET NULL: §8 of the directive
                -- forbids a commitment ever existing without a real source
                -- snapshot, and snapshots have no delete path in this
                -- codebase anyway (append-only, confirmed above) -- RESTRICT
                -- just makes that guarantee explicit rather than relying on
                -- SET NULL silently fighting a NOT NULL constraint.
                source_snapshot_id INTEGER NOT NULL REFERENCES venture_financial_snapshots(id) ON DELETE RESTRICT,
                scenario_id INTEGER REFERENCES venture_financial_scenarios(id) ON DELETE SET NULL,
                scenario_name TEXT,
                hire_plan_ids INTEGER[] NOT NULL DEFAULT '{}',
                financial_plan_ids INTEGER[] NOT NULL DEFAULT '{}',
                plan_snapshot JSONB NOT NULL,
                calculation_version TEXT NOT NULL,
                projection_start DATE NOT NULL,
                projection_horizon_months INTEGER NOT NULL,
                expected_monthly JSONB NOT NULL,
                related_decision_id INTEGER REFERENCES venture_decisions(id) ON DELETE SET NULL,
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'abandoned')),
                supersedes_commitment_id INTEGER REFERENCES venture_financial_commitments(id) ON DELETE SET NULL,
                founder_rationale TEXT,
                idempotency_key TEXT
            )
        """))
        connection.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS venture_financial_commitments_idempotency_key_idx
            ON venture_financial_commitments (idempotency_key)
            WHERE idempotency_key IS NOT NULL
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS venture_financial_commitments_venture_idx
            ON venture_financial_commitments (venture_id, committed_at DESC)
        """))
    print("venture_financial_commitments table created successfully.")


# Phase 38D-C -- Founder Explanation + Learning Capture V1. Additive
# columns on an already-populated table -- every existing commitment
# simply starts with both NULL ("no explanation recorded yet," the
# correct honest default, exactly the same judgment already made for
# venture_hire_plans.last_reconciled_snapshot_id in Phase 35D).
#
# This is the ONE mutable pair on an otherwise append-only row --
# precedented directly by venture_missions.learning_summary's own
# existing update-in-place field (cited by name in the 38D architecture
# doc's own §12), not a new pattern invented here. Saving/editing an
# explanation touches ONLY these two columns -- see
# update_venture_financial_commitment_explanation_for_owner()'s own
# docstring for the exact SET clause, which the 38D-C directive requires
# never widen to any other column on this table.
def add_financial_commitment_explanation_columns():
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                ALTER TABLE venture_financial_commitments
                ADD COLUMN founder_explanation TEXT
            """))
            connection.execute(text("""
                ALTER TABLE venture_financial_commitments
                ADD COLUMN explanation_recorded_at TIMESTAMP
            """))
        print("venture_financial_commitments.founder_explanation/explanation_recorded_at added.")
    except Exception as e:
        print("founder_explanation/explanation_recorded_at migration skipped", e)


_COMMITMENT_COLUMNS = """
                id, venture_id, user_id, committed_at, source_snapshot_id,
                scenario_id, scenario_name, hire_plan_ids, financial_plan_ids,
                plan_snapshot, calculation_version, projection_start,
                projection_horizon_months, expected_monthly, related_decision_id,
                status, supersedes_commitment_id, founder_rationale,
                founder_explanation, explanation_recorded_at
"""


def _parse_commitment_json_fields(row: dict) -> dict:
    """psycopg2/SQLAlchemy sometimes returns a JSONB column already
    decoded, sometimes as a raw string, depending on the exact driver
    path taken -- identical defensive `isinstance(..., str)` guard
    already used everywhere else JSONB is read back in this file (e.g.
    the `methodology`/`model_result` fields above)."""
    for field in ("plan_snapshot", "expected_monthly"):
        if isinstance(row.get(field), str):
            row[field] = json.loads(row[field])
    return row


def create_venture_financial_commitment(
    venture_id: int,
    user_id: str,
    source_snapshot_id: int,
    plan_snapshot: list[dict],
    calculation_version: str,
    projection_start,
    projection_horizon_months: int,
    expected_monthly: list[dict],
    hire_plan_ids: list[int] | None = None,
    financial_plan_ids: list[int] | None = None,
    scenario_id: int | None = None,
    scenario_name: str | None = None,
    related_decision_id: int | None = None,
    founder_rationale: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """
    Ownership of venture_id/scenario_id/every id in hire_plan_ids,
    financial_plan_ids/related_decision_id is enforced by the CALLER
    (app/api.py), identical discipline to create_venture_decision().
    Always exactly ONE INSERT -- the frozen fields (plan_snapshot,
    expected_monthly, calculation_version, source_snapshot_id,
    committed_at) are never written to again by any other function in
    this file (§3 of the 38D-A directive: append-only historical
    integrity). Idempotent when idempotency_key is provided, the
    identical ON CONFLICT + fallback-SELECT pattern create_venture_decision()
    and create_venture_evidence() already use.
    """
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            INSERT INTO venture_financial_commitments (
                venture_id, user_id, source_snapshot_id, scenario_id, scenario_name,
                hire_plan_ids, financial_plan_ids, plan_snapshot, calculation_version,
                projection_start, projection_horizon_months, expected_monthly,
                related_decision_id, founder_rationale, idempotency_key
            )
            VALUES (
                :venture_id, :user_id, :source_snapshot_id, :scenario_id, :scenario_name,
                :hire_plan_ids, :financial_plan_ids, CAST(:plan_snapshot AS JSONB), :calculation_version,
                :projection_start, :projection_horizon_months, CAST(:expected_monthly AS JSONB),
                :related_decision_id, :founder_rationale, :idempotency_key
            )
            ON CONFLICT (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL
                DO NOTHING
            RETURNING {_COMMITMENT_COLUMNS}
        """), {
            "venture_id": venture_id,
            "user_id": user_id,
            "source_snapshot_id": source_snapshot_id,
            "scenario_id": scenario_id,
            "scenario_name": scenario_name,
            "hire_plan_ids": hire_plan_ids or [],
            "financial_plan_ids": financial_plan_ids or [],
            "plan_snapshot": json.dumps(plan_snapshot),
            "calculation_version": calculation_version,
            "projection_start": projection_start,
            "projection_horizon_months": projection_horizon_months,
            "expected_monthly": json.dumps(expected_monthly),
            "related_decision_id": related_decision_id,
            "founder_rationale": founder_rationale,
            "idempotency_key": idempotency_key,
        })

        row = result.mappings().first()
        if row is not None:
            return _parse_commitment_json_fields(dict(row))

        existing = connection.execute(text(f"""
            SELECT {_COMMITMENT_COLUMNS}
            FROM venture_financial_commitments
            WHERE idempotency_key = :idempotency_key AND user_id = :user_id
        """), {"idempotency_key": idempotency_key, "user_id": user_id}).mappings().first()

        return _parse_commitment_json_fields(dict(existing))


def list_venture_financial_commitments_for_owner(user_id: str, venture_id: int) -> list[dict]:
    """Every commitment ever made for this venture, most recent first --
    the full, honest timeline (§17 of the accepted architecture:
    "independent commitment events, not one giant operating-plan
    object")."""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {_COMMITMENT_COLUMNS}
            FROM venture_financial_commitments
            WHERE venture_id = :venture_id AND user_id = :user_id
            ORDER BY committed_at DESC
        """), {"venture_id": venture_id, "user_id": user_id})
        return [_parse_commitment_json_fields(dict(row)) for row in result.mappings().all()]


def get_venture_financial_commitment_for_owner(user_id: str, venture_id: int, commitment_id: int) -> dict | None:
    """Returns the row EXACTLY as stored -- no recomputation, no
    re-derivation of expected_monthly/plan_snapshot from live plan rows.
    This is the load-bearing guarantee of the whole phase: a GET must
    never depend on the current state of venture_hire_plans/
    venture_financial_plans/venture_financial_snapshots."""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT {_COMMITMENT_COLUMNS}
            FROM venture_financial_commitments
            WHERE id = :commitment_id AND venture_id = :venture_id AND user_id = :user_id
        """), {"commitment_id": commitment_id, "venture_id": venture_id, "user_id": user_id})
        row = result.mappings().first()
        return _parse_commitment_json_fields(dict(row)) if row else None


def update_venture_financial_commitment_explanation_for_owner(
    user_id: str, venture_id: int, commitment_id: int, founder_explanation: str
) -> dict | None:
    """
    Phase 38D-C. The ONLY UPDATE path this table has -- and its own SET
    clause touches EXACTLY two columns, `founder_explanation` and
    `explanation_recorded_at` (always CURRENT_TIMESTAMP, whether this is
    the first save or an edit of an existing one -- §5 of the directive:
    "explanation_recorded_at should consistently represent the latest
    successful explanation save/update," never a created-vs-updated
    distinction, never a revision history). Every other column --
    `plan_snapshot`, `expected_monthly`, `committed_at`,
    `source_snapshot_id`, `calculation_version`, and everything else --
    is absent from this statement entirely, not merely unchanged by
    coincidence: there is no code path in this function that could ever
    touch them, which is what keeps 38D-A's frozen-expectation guarantee
    load-bearing rather than just conventionally honored.

    Returns None if the row doesn't exist or isn't owned by this
    venture/user (ownership re-checked in the same statement, the same
    discipline as update_venture_hire_plan_for_owner()).
    """
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            UPDATE venture_financial_commitments
            SET founder_explanation = :founder_explanation,
                explanation_recorded_at = CURRENT_TIMESTAMP
            WHERE id = :commitment_id AND venture_id = :venture_id AND user_id = :user_id
            RETURNING {_COMMITMENT_COLUMNS}
        """), {
            "founder_explanation": founder_explanation,
            "commitment_id": commitment_id,
            "venture_id": venture_id,
            "user_id": user_id,
        })
        row = result.mappings().first()
        return _parse_commitment_json_fields(dict(row)) if row else None


_DECISION_COLUMNS = """
                id, venture_id, user_id, related_mission_id, sie_recommendation,
                sie_reasoning, founder_choice, founder_rationale, evidence_ids,
                supersedes_decision_id, decided_at
"""


def create_venture_decision(
    venture_id: int,
    user_id: str,
    sie_recommendation: str,
    sie_reasoning: str,
    founder_choice: str,
    related_mission_id: int | None = None,
    founder_rationale: str | None = None,
    evidence_ids: list[int] | None = None,
    supersedes_decision_id: int | None = None,
    idempotency_key: str | None = None,
):
    """
    Ownership of related_mission_id/every id in evidence_ids is enforced
    by the CALLER (app/api.py), exactly as create_venture_evidence()
    documents. Idempotent when idempotency_key is provided, same
    ON CONFLICT + fallback-SELECT pattern as create_venture_evidence().
    """
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            INSERT INTO venture_decisions (
                venture_id, user_id, related_mission_id, sie_recommendation,
                sie_reasoning, founder_choice, founder_rationale, evidence_ids,
                supersedes_decision_id, idempotency_key
            )
            VALUES (
                :venture_id, :user_id, :related_mission_id, :sie_recommendation,
                :sie_reasoning, :founder_choice, :founder_rationale, :evidence_ids,
                :supersedes_decision_id, :idempotency_key
            )
            ON CONFLICT (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL
                DO NOTHING
            RETURNING {_DECISION_COLUMNS}
        """), {
            "venture_id": venture_id,
            "user_id": user_id,
            "related_mission_id": related_mission_id,
            "sie_recommendation": sie_recommendation,
            "sie_reasoning": sie_reasoning,
            "founder_choice": founder_choice,
            "founder_rationale": founder_rationale,
            "evidence_ids": evidence_ids or [],
            "supersedes_decision_id": supersedes_decision_id,
            "idempotency_key": idempotency_key,
        })

        row = result.mappings().first()
        if row is not None:
            return dict(row)

        existing = connection.execute(text(f"""
            SELECT {_DECISION_COLUMNS}
            FROM venture_decisions
            WHERE idempotency_key = :idempotency_key AND user_id = :user_id
        """), {"idempotency_key": idempotency_key, "user_id": user_id}).mappings().first()

        return dict(existing)


def list_venture_decisions_for_owner(user_id: str, venture_id: int):
    """Same ownership-scoped JOIN discipline as list_venture_missions_for_owner()."""
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT vd.id, vd.venture_id, vd.user_id, vd.related_mission_id,
                   vd.sie_recommendation, vd.sie_reasoning, vd.founder_choice,
                   vd.founder_rationale, vd.evidence_ids, vd.supersedes_decision_id,
                   vd.decided_at
            FROM venture_decisions vd
            JOIN modeled_ventures v ON v.id = vd.venture_id
            WHERE vd.venture_id = :venture_id AND v.user_id = :user_id
            ORDER BY vd.decided_at ASC
        """), {"venture_id": venture_id, "user_id": user_id})

        return [dict(row) for row in result.mappings().all()]


def set_venture_mission_interpretation_for_owner(
    user_id: str, venture_id: int, mission_id: int,
    interpretation_summary: str, interpretation_limitations: str,
):
    """
    Update-in-place, deliberately -- see VentureMissionResponse's own
    docstring in app/models/venture_missions.py for why this is the one
    place in this design where that's correct rather than append-only:
    a test has exactly one live interpretation cycle in this V1's
    single-question model, and a founder revising it before the test
    completes should see the latest reading, not a growing list.
    """
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            UPDATE venture_missions vm
            SET interpretation_summary = :interpretation_summary,
                interpretation_limitations = :interpretation_limitations,
                interpretation_generated_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            FROM modeled_ventures v
            WHERE vm.venture_id = v.id
              AND vm.id = :mission_id
              AND vm.venture_id = :venture_id
              AND v.user_id = :user_id
            RETURNING {_MISSION_COLUMNS_VM}
        """), {
            "mission_id": mission_id,
            "venture_id": venture_id,
            "user_id": user_id,
            "interpretation_summary": interpretation_summary,
            "interpretation_limitations": interpretation_limitations,
        })

        row = result.mappings().first()
        return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# Phase 10.8 -- Pitch Deck Coach V1. pitch_deck_reviews has no FK to
# startups/analyses/modeled_ventures -- only to users(id), the same "clean
# private entity" shape modeled_ventures and venture_missions already
# established (see create_modeled_ventures_table()'s and
# create_venture_missions_table()'s own docstrings). A pitch deck review
# is a coaching artifact, never a Startup/Analysis: nothing in this
# section, or anywhere that reads from this table, has a path into
# Rankings, Discovery, Compare, or SPS History.
#
# `review` is one JSONB blob holding the full sanitized coaching payload
# app/ai/pitch_deck_coaching.py::generate_pitch_deck_review() returns
# (story/sections/top_fixes/strengths/open_questions/prep_questions) --
# deliberately not split across columns, the same reasoning
# modeled_ventures.model_result already uses for VPSResult: this is a
# single cohesive artifact always read and written as a whole, never
# queried by its internal fields.
#
# Deck text is intentionally NOT persisted here -- only readiness_label,
# deck_filename, page_count, and the review JSONB. The founder's raw deck
# content only ever needs to exist in memory for the one request that
# reviews it; storing it again would be a second copy of potentially
# sensitive material with no product use for this phase.
# ---------------------------------------------------------------------------

def create_pitch_deck_reviews_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS pitch_deck_reviews (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                deck_filename TEXT NOT NULL,
                page_count INTEGER NOT NULL,
                readiness_label TEXT NOT NULL,
                review JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

    print("pitch_deck_reviews table created successfully.")


def create_pitch_deck_review(
    user_id: str,
    deck_filename: str,
    page_count: int,
    readiness_label: str,
    review: dict,
) -> int:
    with engine.begin() as connection:
        result = connection.execute(text("""
            INSERT INTO pitch_deck_reviews (
                user_id, deck_filename, page_count, readiness_label, review
            )
            VALUES (
                :user_id, :deck_filename, :page_count, :readiness_label, :review
            )
            RETURNING id
        """), {
            "user_id": user_id,
            "deck_filename": deck_filename,
            "page_count": page_count,
            "readiness_label": readiness_label,
            "review": json.dumps(review),
        })

        return result.scalar()


def _parse_pitch_deck_review_row(row: dict) -> dict:
    parsed = dict(row)

    if isinstance(parsed.get("review"), str):
        parsed["review"] = json.loads(parsed["review"])

    return parsed


def list_pitch_deck_reviews_for_user(user_id: str):
    """Part 17: reviews naturally coexist -- every POST creates a new row,
    nothing here overwrites a prior review. Summary shape only (no
    `review` JSONB) -- matches list_modeled_ventures_for_user()'s own
    light-list convention; app/api.py projects this into
    PitchDeckReviewSummary."""
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT id, user_id, deck_filename, page_count, readiness_label, created_at
            FROM pitch_deck_reviews
            WHERE user_id = :user_id
            ORDER BY created_at DESC
        """), {"user_id": user_id})

        return [dict(row) for row in result.mappings().all()]


def count_recent_pitch_deck_reviews(user_id: str, window_hours: int) -> int:
    """Minimal cost-control check (Part 24's own "preserve Phase 10.1
    hardening" posture, scoped down for this phase): counts every review
    row created in the rolling window, regardless of outcome. Pitch Deck
    Coach makes exactly one LLM call per review (see
    generate_pitch_deck_review()), a materially smaller cost surface than
    the six-pillar canonical pipeline analysis_runs guards -- so this
    reuses that module's proportionate, count-based approach rather than
    its full concurrency-lock/fingerprint/dedup machinery, which this
    phase's own test list (Part 25) does not call for."""
    with engine.begin() as connection:
        return connection.execute(text("""
            SELECT count(*) FROM pitch_deck_reviews
            WHERE user_id = :user_id
              AND created_at > CURRENT_TIMESTAMP - make_interval(hours => :window_hours)
        """), {"user_id": user_id, "window_hours": window_hours}).scalar()


def get_pitch_deck_review_for_user(user_id: str, review_id: int):
    """Returns None both when the review doesn't exist AND when it
    belongs to a different user -- same non-leaking 404 shape as
    get_modeled_venture_for_user()."""
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT id, user_id, deck_filename, page_count, readiness_label, review, created_at
            FROM pitch_deck_reviews
            WHERE id = :review_id AND user_id = :user_id
        """), {"review_id": review_id, "user_id": user_id})

        row = result.mappings().first()

    if row is None:
        return None

    return _parse_pitch_deck_review_row(dict(row))


def get_top_startups(viewer_user_id: str, viewer_is_admin: bool, limit: int = 10):
    """
    Canonical Dashboard MVP: Top Startups reuses get_rankings() directly --
    the exact same canonical population, "latest analysis per startup"
    logic, and SPS-descending order -- rather than a second, parallel
    query against the legacy score_history table. Top Startups and
    Rankings can now never disagree about which analyses are eligible or
    which one is "latest" for a given company, because they're the same
    query. Portfolio Release Task 3B: inherits the same viewer-scoping
    get_rankings() now applies.
    """
    return get_rankings(viewer_user_id, viewer_is_admin)[:limit]


def get_top_improving_startups(viewer_user_id: str, viewer_is_admin: bool, limit: int = 10):
    """
    Canonical Dashboard MVP: sourced ONLY from canonical Methodology v2
    analyses (methodology IS NOT NULL AND methodology_version matches the
    current constant) -- never the legacy score_history table, which mixes
    incompatible scoring eras and has no methodology-version concept at
    all. A startup needs at least 2 canonical analyses before an
    "improvement" can be honestly computed; a startup with only one
    canonical analysis is excluded, not compared against itself or against
    a legacy score. Returns [] -- not a partial/fake leaderboard -- if
    fewer than one startup currently qualifies; the frontend's existing
    empty state already renders that truthfully.

    Final MVP Stabilization: also requires score_change > 0. Without this,
    a company whose SPS actually declined between analyses could still
    surface here (as the least-bad entry) under the label "Fastest
    improving startups" -- a real, honest-labeling defect found during
    the Core MVP acceptance walkthrough, not a hypothetical: with only one
    repeat-analyzed company in the dataset and a negative score_change,
    that company was the sole (misleading) entry. A company that hasn't
    actually improved now falls out of this list entirely and the
    zero-results empty state (see above) takes over, rather than the list
    quietly including a decline.
    """
    with engine.begin() as connection:
        result = connection.execute(text(f"""
            SELECT
                company_name,
                (methodology->>'startup_intelligence_score')::float AS sps,
                created_at
            FROM analyses
            WHERE
                methodology IS NOT NULL
                AND methodology->'analysis_context'->>'methodology_version' = :methodology_version
                AND methodology->>'startup_intelligence_score' IS NOT NULL
                AND company_name IS NOT NULL
                AND TRIM(company_name) <> ''
                AND {_analysis_visibility_clause()}
            ORDER BY LOWER(TRIM(company_name)), created_at ASC, id ASC
        """), {
            "methodology_version": METHODOLOGY_VERSION,
            "viewer_user_id": viewer_user_id,
            "viewer_is_admin": viewer_is_admin,
        })

        rows = result.mappings().all()

    companies = {}

    for row in rows:
        normalized_name = row["company_name"].lower().strip()

        if normalized_name not in companies:
            companies[normalized_name] = {
                "display_name": row["company_name"],
                "first_score": row["sps"],
                "latest_score": row["sps"],
                "canonical_analysis_count": 1,
            }
        else:
            companies[normalized_name]["latest_score"] = row["sps"]
            companies[normalized_name]["display_name"] = row["company_name"]
            companies[normalized_name]["canonical_analysis_count"] += 1

    improvements = [
        {
            "company_name": data["display_name"],
            "first_score": data["first_score"],
            "latest_score": data["latest_score"],
            "score_change": round(data["latest_score"] - data["first_score"], 2),
        }
        for data in companies.values()
        if data["canonical_analysis_count"] >= 2
        and data["latest_score"] > data["first_score"]
    ]

    improvements.sort(
        key=lambda x: x["score_change"],
        reverse=True
    )

    return improvements[:limit]

# ---------------------------------------------------------------------------
# Phase 10.1B -- AI Cost + Analysis Abuse Protection. analysis_runs is a
# new, additive, purely operational table: one row per REAL attempt to
# run the expensive pipeline (POST /analyze reaching the usage-protection
# gate), never a second scoring or intelligence concept. It has no FK
# from any canonical table and nothing here ever reads back into
# Methodology v2/SPS/VPS/Fundraising Readiness/Investor Workspace -- it
# exists purely to answer three operational questions: "does this user
# already have a run in flight," "how many attempts has this user made
# recently," and "did this user just submit the exact same thing."
#
# Durability requirement (Part 3): the concurrency lock below MUST survive
# multiple worker processes and process restarts, not just be correct
# within one Python process. It is enforced by
# analysis_runs_one_active_per_user, a PARTIAL UNIQUE INDEX on
# (user_id) WHERE status = 'running' -- the database itself guarantees at
# most one 'running' row per user_id can ever exist, regardless of how
# many processes/threads race to insert one. This is the same
# "correctness lives in a real constraint, not a check-then-act race" the
# codebase already established at create_startup_memberships_table()'s
# UNIQUE(user_id, startup_id) and approve_startup_claim()'s
# SELECT ... FOR UPDATE.
# ---------------------------------------------------------------------------

# Centralized, named policy constants (Part 4: "keep the policy
# centralized/configurable rather than scattering magic numbers") --
# every number a beta-usage decision depends on lives here, nowhere else.

# How many analysis attempts (any status -- 'running', 'completed', or
# 'failed' all count, matching Part 4.C's "completed/started analyses")
# a single user may make in the rolling window below. This is a small
# closed beta with a bounded, personally-invited user population (see the
# Phase 10.1 audit) -- 20/day is generous enough not to interfere with a
# real founder testing their own startup repeatedly or an investor
# exploring several companies in one sitting, while still bounding the
# realistic worst case (a careless script, a stuck retry loop, a shared
# account) to a small, predictable number of paid LLM/Tavily calls.
DAILY_ANALYSIS_CAP = 20
USAGE_WINDOW_HOURS = 24

# How long a 'running' row is trusted before it's treated as abandoned
# (Part 5: "stale running records caused by process termination"). Reuses
# the frontend's own existing ANALYZE_TIMEOUT_MS (10 minutes --
# dashboard/lib/api/analyze.ts) as the exact same "this should have
# finished by now" ceiling, rather than inventing a second number for the
# same real-world fact: a genuine analysis that hasn't finished in 10
# minutes is already considered hung/timed-out from the client's own
# point of view.
STALE_RUN_THRESHOLD_MINUTES = 10

# How long a SUCCESSFUL (status='completed') run's fingerprint blocks an
# identical resubmission from the same user (Part 4.B: "shortly after a
# successful submission"). Deliberately short -- long enough to catch an
# accidental double-click/duplicate-tab submission of the exact same
# input, short enough that a user who genuinely wants to re-run the same
# public company text again later is never meaningfully blocked. Never
# applied to a failed run (a user must always be able to immediately
# retry after a failure -- see AnalyzeStartupForm.tsx's own existing "Your
# input hasn't been lost -- you can try again" copy) and never applied to
# a founder-targeted re-analysis (startup_id is not None) -- Phase 7.2.1's
# whole point is that re-analyzing the SAME startup again soon after a
# previous run is a legitimate, expected workflow, not a duplicate.
DUPLICATE_COOLDOWN_MINUTES = 5


def create_analysis_runs_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                startup_id INTEGER REFERENCES startups(id),
                fingerprint TEXT,
                status TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """))

        connection.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS analysis_runs_one_active_per_user
            ON analysis_runs (user_id)
            WHERE status = 'running'
        """))

    print("analysis_runs table created successfully.")


def compute_analysis_fingerprint(company_text: str | None, website_url: str | None, pdf_bytes: bytes | None) -> str:
    """
    A deterministic fingerprint of the RAW inputs a caller submitted --
    computed from what the client actually sent, before any extraction,
    so the duplicate-cooldown check (has_recent_duplicate_completed_run()
    below) can run before website fetch/PDF parsing, not after (Part 5).
    Plain sha256 over a delimited, order-fixed concatenation -- no
    external library, no secret, nothing sensitive derived from it that
    isn't already fully known to the caller who submitted it.
    """
    normalized_text = (company_text or "").strip()
    normalized_url = (website_url or "").strip().lower()
    pdf_digest = hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else ""

    combined = f"{normalized_text}\x00{normalized_url}\x00{pdf_digest}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def count_recent_analysis_runs(user_id: str) -> int:
    """Part 4.C usage-cap check -- counts every attempt (any status) in
    the rolling USAGE_WINDOW_HOURS window, regardless of how it ended."""
    with engine.begin() as connection:
        return connection.execute(text("""
            SELECT count(*) FROM analysis_runs
            WHERE user_id = :user_id
              AND created_at > CURRENT_TIMESTAMP - make_interval(hours => :window_hours)
        """), {"user_id": user_id, "window_hours": USAGE_WINDOW_HOURS}).scalar()


def has_recent_duplicate_completed_run(user_id: str, fingerprint: str) -> bool:
    """
    Part 4.B rapid-accidental-duplicate check. Only ever called by the
    caller for a NON-founder-targeted request (startup_id is None) --
    see this module's own DUPLICATE_COOLDOWN_MINUTES docstring for why
    founder-targeted re-analysis and failed runs are both deliberately
    excluded from this check entirely (the exclusion is enforced by what
    the caller passes in / calls this at all, not by a parameter here).
    """
    with engine.begin() as connection:
        row = connection.execute(text("""
            SELECT 1 FROM analysis_runs
            WHERE user_id = :user_id
              AND fingerprint = :fingerprint
              AND status = 'completed'
              AND startup_id IS NULL
              AND created_at > CURRENT_TIMESTAMP - make_interval(mins => :cooldown_minutes)
            LIMIT 1
        """), {"user_id": user_id, "fingerprint": fingerprint, "cooldown_minutes": DUPLICATE_COOLDOWN_MINUTES}).first()
        return row is not None


def begin_analysis_run(user_id: str, startup_id: int | None, fingerprint: str) -> int | None:
    """
    Part 4.A concurrency lock. First expires any of THIS user's stale
    'running' rows (a crash/restart mid-pipeline is the only way one can
    outlive STALE_RUN_THRESHOLD_MINUTES, since a real run always
    transitions to 'completed'/'failed' via finish_analysis_run() in a
    try/finally -- see that function's own docstring), in its own
    transaction, then attempts the actual INSERT in a second, separate
    transaction so a unique-violation there cleanly aborts only that one
    statement.

    Returns the new row's id on success. Returns None if the user already
    has a genuinely active (non-stale) 'running' row -- the caller must
    treat None as "reject with 409," never retry-insert itself; the
    partial unique index (see create_analysis_runs_table()) is what
    actually guarantees correctness under real concurrent requests, this
    pre-expiry step is only what keeps a long-dead crash from permanently
    locking the user out.
    """
    with engine.begin() as connection:
        connection.execute(text("""
            UPDATE analysis_runs
            SET status = 'failed', completed_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id
              AND status = 'running'
              AND created_at < CURRENT_TIMESTAMP - make_interval(mins => :threshold)
        """), {"user_id": user_id, "threshold": STALE_RUN_THRESHOLD_MINUTES})

    try:
        with engine.begin() as connection:
            result = connection.execute(text("""
                INSERT INTO analysis_runs (user_id, startup_id, fingerprint, status)
                VALUES (:user_id, :startup_id, :fingerprint, 'running')
                RETURNING id
            """), {"user_id": user_id, "startup_id": startup_id, "fingerprint": fingerprint})
            return result.scalar()
    except IntegrityError:
        return None


def finish_analysis_run(run_id: int, status: str) -> None:
    """
    Releases the concurrency lock (Part 5: "do not leave the user
    permanently locked because a previous request crashed") by
    transitioning a 'running' row to its real terminal status. Called
    from a `finally` block around the entire post-gate request body in
    POST /analyze, so this runs whether the request ultimately succeeded,
    failed validation, failed extraction, failed the pipeline, or failed
    to persist -- every one of those paths still frees the user to submit
    again immediately.
    """
    with engine.begin() as connection:
        connection.execute(text("""
            UPDATE analysis_runs
            SET status = :status, completed_at = CURRENT_TIMESTAMP
            WHERE id = :run_id
        """), {"run_id": run_id, "status": status})


def add_methodology_column():
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                ALTER TABLE analyses
                ADD COLUMN methodology JSONB
            """))

        print("methodology column added")

    except Exception as error:
        print("methodology migration skipped", error)


# ---------------------------------------------------------------------------
# Phase 28 -- Product Analytics & Growth Measurement V1.
#
# ONE new, append-only table. No new AI system, no new score, no
# recommendation change (Part 21). This is behavioral telemetry -- what
# happened, to which venture, when -- never a second copy of founder
# content. venture_missions/venture_model_updates (founder-facing product
# memory) and product_events (aggregate measurement) are deliberately
# separate, per Part 20's own instruction, even though they're both
# written from the same underlying founder actions.
#
# Investigated first (Part 1): `lib/api/analytics.ts` and the platform-
# wide `/analytics`, `/top-startups` endpoints are aggregate STARTUP
# rankings analytics, a completely different concern (confirmed already,
# repeatedly, since Phase 22). There is no per-founder behavioral event
# mechanism anywhere in this codebase before this phase.
#
# Schema, deliberately close to (not identical to) Part 5's own candidate
# fields, after determining what's actually necessary:
#   id              -- surrogate key
#   event_name      -- one of a small, fixed set (see app/api.py's own
#                      logging call sites -- there is no generic
#                      "log any event" path anywhere in this codebase)
#   user_id         -- nullable: an anonymous public-snapshot view has no
#                      signed-in user at all
#   venture_id      -- nullable: not every event is venture-scoped (there
#                      are none that aren't, currently, but the column
#                      stays nullable rather than assuming that forever)
#   share_public_id -- nullable: only distribution events carry this
#   source          -- nullable: currently used for exactly one thing,
#                      venture_created's own "organic" vs. "snapshot"
#                      attribution (Part 17) -- a safe, small enum string,
#                      never a URL, never a referrer, never a user agent
#   metadata        -- JSONB, allowlisted per call site (see each
#                      log_product_event() call in app/api.py), NEVER
#                      free text -- no Capture/learning/Action text, no
#                      raw description, no fundraising terms, ever
#   created_at      -- when the event was recorded
#
# No FK constraints to users/modeled_ventures -- deliberately, matching
# this table's own append-only, best-effort nature (Part 19: analytics
# must fail open, never block a real founder action; a hard FK failure
# on an ordinary DELETE /ventures/{id} would be exactly the kind of
# telemetry-blocks-product failure this phase forbids). Referential
# integrity for reporting is instead enforced query-side (a report simply
# excludes/nulls out anything that no longer resolves).
def create_product_events_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS product_events (
                id SERIAL PRIMARY KEY,
                event_name TEXT NOT NULL,
                user_id TEXT,
                venture_id INTEGER,
                share_public_id TEXT,
                source TEXT,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_product_events_name_created
            ON product_events (event_name, created_at)
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_product_events_venture
            ON product_events (venture_id)
        """))

    print("product_events table created successfully.")


# Phase 28, Part 2/3. The complete, closed set of event names this
# codebase will ever insert -- there is no code path anywhere that
# accepts an arbitrary event_name from a request body (Part 5's own "no
# arbitrary frontend metadata dumping" instruction extends to the event
# name itself, not just its metadata). Every one of these is logged from
# exactly one call site in app/api.py, documented there with the precise
# state transition that triggers it.
QUALIFYING_BUILDING_EVENTS = (
    "action_created",
    "action_completed",
    "learning_recorded",
    "capture_recorded",
    "venture_model_updated",
)

_ALL_EVENT_NAMES = frozenset(QUALIFYING_BUILDING_EVENTS) | {
    "venture_created",
    "snapshot_enabled",
    "snapshot_disabled",
    "snapshot_viewed_publicly",
    "snapshot_link_copied",
    "snapshot_cta_clicked",
    # Phase 31 -- Venture -> Startup Graduation V1, Part 14. Deliberately
    # NOT added to QUALIFYING_BUILDING_EVENTS -- that tuple feeds the
    # Meaningful Building Days / North Star reports' own existing
    # definition of "building", which this phase was explicitly told not
    # to redefine. graduation_prompt_shown/graduation_started are logged
    # client-side (VentureGraduation.tsx / GraduateVentureReview.tsx);
    # venture_graduated and startup_opened_from_venture are logged from
    # app/api.py -- see each call site's own comment for the exact
    # trigger.
    "graduation_prompt_shown",
    "graduation_started",
    "venture_graduated",
    "startup_opened_from_venture",
    # Phase 34D -- SIE Build Intelligence Loop V1. Deliberately NOT added
    # to QUALIFYING_BUILDING_EVENTS -- same reasoning as graduation's own
    # events above: that tuple's "Meaningful Building Days" definition is
    # out of scope to redefine in this phase. Logged from app/api.py's
    # new POST /ventures/{id}/evidence and POST /ventures/{id}/decisions
    # endpoints.
    "evidence_confirmed",
    "decision_recorded",
    # Phase 34G-A -- Intelligence Resolution + Learning Integrity
    # Hardening, §3/§6. Logged from app/api.py's new
    # POST /ventures/{id}/evidence/{evidence_id}/resolve endpoint.
    # Deliberately NOT added to QUALIFYING_BUILDING_EVENTS, same
    # reasoning as evidence_confirmed/decision_recorded above.
    "evidence_resolved",
    # Phase 35B -- Financial State Persistence + Runway Engine V1. Logged
    # from app/api.py's new POST /ventures/{id}/financials endpoint.
    # Deliberately NOT added to QUALIFYING_BUILDING_EVENTS, same reasoning
    # as every other Build/Finance event above.
    "financial_snapshot_recorded",
    # Phase 35C -- Hiring + Operating Plan Engine V1. Logged from
    # app/api.py's new POST /ventures/{id}/hire-plans and
    # PATCH /ventures/{id}/hire-plans/{id} endpoints. Deliberately NOT
    # added to QUALIFYING_BUILDING_EVENTS, same reasoning as above.
    "hire_plan_created",
    "hire_plan_status_changed",
    # Phase 35D -- Operating Scenarios + Financial Plan Reconciliation V1.
    # Logged from app/api.py's new financial-plan/scenario/reconciliation
    # endpoints. Deliberately NOT added to QUALIFYING_BUILDING_EVENTS,
    # same reasoning as every other Build/Finance event above.
    "financial_plan_created",
    "financial_plan_status_changed",
    "financial_plan_reconciled",
    "financial_scenario_created",
    # Phase 38D-A -- Financial Commitment Persistence + Frozen Expectation
    # V1. Logged from app/api.py's new POST /ventures/{id}/financial-commitments
    # endpoint. Deliberately NOT added to QUALIFYING_BUILDING_EVENTS, same
    # reasoning as every other Finance event above.
    "financial_commitment_created",
    # Phase 38D-C -- Founder Explanation + Learning Capture V1. Logged
    # from app/api.py's new PATCH .../financial-commitments/{id}/explanation
    # endpoint. Deliberately NOT added to QUALIFYING_BUILDING_EVENTS, same
    # reasoning as every other Finance event above.
    "financial_commitment_explanation_recorded",
}


def log_product_event(
    event_name: str,
    user_id: str | None = None,
    venture_id: int | None = None,
    share_public_id: str | None = None,
    source: str | None = None,
    metadata: dict | None = None,
) -> None:
    """
    THE single write path for product_events -- every call site in
    app/api.py calls this, never a raw INSERT of its own. Deliberately
    swallows its own failures (Part 19: "analytics should fail open" --
    a telemetry outage must never block Capture, an Action, a model
    update, or a share toggle from succeeding). Asserts event_name is one
    of the fixed set in Python, before ever reaching SQL -- a typo'd
    event name fails loudly in dev/tests rather than silently polluting
    the table with an unrecognized string no report will ever look for.
    """
    if event_name not in _ALL_EVENT_NAMES:
        raise ValueError(f"Unrecognized product event name: {event_name!r}")

    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO product_events
                    (event_name, user_id, venture_id, share_public_id, source, metadata)
                VALUES
                    (:event_name, :user_id, :venture_id, :share_public_id, :source, :metadata)
            """), {
                "event_name": event_name,
                "user_id": user_id,
                "venture_id": venture_id,
                "share_public_id": share_public_id,
                "source": source,
                "metadata": json.dumps(metadata or {}),
            })
    except Exception as error:
        # Fail open, always -- see this function's own docstring. Printed,
        # not raised, so a telemetry outage is visible in logs without
        # ever surfacing to the founder or aborting their real request.
        print(f"product_events insert skipped for '{event_name}'", error)


# Phase 28, Part 16. The one existing, already-repo-wide convention for
# marking test-created data: every automated test in app/tests/ that
# creates a real user row uses a "zztest_" user_id prefix (21 of 45 test
# files, confirmed by direct grep before writing this). No new
# environment/marker system was invented -- this reuses that exact,
# already-established convention. A public/anonymous event (no user_id)
# is excluded instead by checking whether the venture it's attributed to
# belongs to a zztest_ user, since a live browser walkthrough against a
# zztest_-seeded venture (e.g. this phase's own live acceptance testing)
# would otherwise still pollute aggregate counts.
# Phase 29 -- Private Beta Readiness, Part 13/25. A second, real
# contamination source Phase 28 hadn't yet accounted for: the creator/
# operator's OWN real (non-zztest_) account, used for every phase's own
# extensive live testing across this entire engagement. That account is
# never a real beta founder, so it must be excluded from beta metrics
# exactly like a zztest_ user is -- otherwise Day-1 beta numbers would be
# silently inflated by the creator's own dev traffic. Reused, not
# reinvented: ADMIN_USER_IDS already exists (app/auth.py, Phase 7.1A) as
# the server-side allowlist of exactly those accounts. Read directly here
# via the same os.getenv() pattern app/auth.py's own
# _resolve_admin_user_ids() uses, rather than importing from app.auth --
# app/auth.py already imports FROM this module (get_or_create_user), so
# the reverse import would be circular. This is intentionally the same
# small, duplicated env-read every other *_ALLOWED_ORIGINS/*_USER_IDS
# pattern in this codebase already accepts (see app/api.py's own
# CORS_ALLOWED_ORIGINS comment) -- not a new architecture.
def _resolve_admin_user_ids_for_exclusion() -> list[str]:
    raw = os.getenv("ADMIN_USER_IDS", "")
    return [user_id.strip() for user_id in raw.split(",") if user_id.strip()]


def _excluded_user_ids_sql_list() -> str:
    """A literal SQL list, not a bind param -- ADMIN_USER_IDS is a small,
    server-operator-controlled env var (never per-request/client input),
    the same trust level _qualifying_events_sql_list() already extends to
    its own hardcoded Python tuple. Single quotes are still escaped
    defensively. Returns "" (an empty list literal is invalid SQL) when
    no admins are configured -- callers handle that case themselves."""
    ids = _resolve_admin_user_ids_for_exclusion()
    return ", ".join("'" + admin_id.replace("'", "''") + "'" for admin_id in ids)


_TEST_EXCLUSION_SQL = """
    (pe.user_id IS NULL OR pe.user_id NOT LIKE 'zztest_%')
    AND (pe.venture_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM modeled_ventures v
        WHERE v.id = pe.venture_id AND v.user_id LIKE 'zztest_%'
    ))
"""


def _test_exclusion_sql(exclude_test_users: bool) -> str:
    """`exclude_test_users=False` exists ONLY for this file's own hand-
    calculated-fixture regression test (Part 24), which necessarily
    creates its fixture ventures under a zztest_ user (the same cleanup
    lifecycle every other test in this codebase already relies on) and
    needs to verify the report arithmetic against exactly those rows,
    independent of the exclusion filter that's separately, directly
    tested by test_zztest_users_excluded_from_reports(). Every real call
    site (the admin endpoint) always uses the default True.

    When True, ALSO excludes any current ADMIN_USER_IDS account (Part
    13/25's own "clean beta baseline" requirement) -- both exclusions
    live in one fragment so every report function automatically gets
    both without a second parameter to remember to pass.
    """
    if not exclude_test_users:
        return "TRUE"

    admin_ids_sql = _excluded_user_ids_sql_list()
    admin_exclusion = f"AND (pe.user_id IS NULL OR pe.user_id NOT IN ({admin_ids_sql}))" if admin_ids_sql else ""
    admin_venture_exclusion = (
        f"""AND (pe.venture_id IS NULL OR NOT EXISTS (
            SELECT 1 FROM modeled_ventures v
            WHERE v.id = pe.venture_id AND v.user_id IN ({admin_ids_sql})
        ))"""
        if admin_ids_sql else ""
    )
    return f"{_TEST_EXCLUSION_SQL} {admin_exclusion} {admin_venture_exclusion}"


def _qualifying_events_sql_list() -> str:
    return ", ".join(f"'{name}'" for name in QUALIFYING_BUILDING_EVENTS)


def get_north_star_report(window_days: int, exclude_test_users: bool = True) -> dict:
    """Weekly/rolling-window Active Building Ventures: distinct ventures
    with >=1 qualifying event in the trailing `window_days`. Excludes
    venture_created itself (Part 7's own explicit decision -- creation is
    activation, not ongoing building).

    Phase 29 fix: this function (and the two below) previously referenced
    the raw _TEST_EXCLUSION_SQL constant directly rather than calling
    _test_exclusion_sql() -- meaning the Part 13/25 admin-account
    exclusion added this phase silently did NOT apply here, even though
    it applied to activation/retention/distribution. Live-verified bug:
    the admin dashboard showed "Ventures created: 0" (correctly excluded)
    alongside "Captures: 2" (NOT excluded) for the same creator-only
    testing session. Fixed by routing all six report functions through
    the one shared _test_exclusion_sql() call.
    """
    exclusion = _test_exclusion_sql(exclude_test_users)
    with engine.begin() as connection:
        row = connection.execute(text(f"""
            SELECT COUNT(DISTINCT pe.venture_id) AS active_ventures
            FROM product_events pe
            WHERE pe.event_name IN ({_qualifying_events_sql_list()})
              AND pe.created_at >= NOW() - INTERVAL '1 day' * :days
              AND {exclusion}
        """), {"days": window_days}).mappings().first()

    return {"window_days": window_days, "active_ventures": row["active_ventures"] or 0}


def get_meaningful_building_days_report(window_days: int, exclude_test_users: bool = True) -> dict:
    """Part 10's own chosen metric: distinct (venture, calendar day) pairs
    with >=1 qualifying event, in the window -- never a fabricated
    "session" count. Reported both as a total and per-active-venture."""
    exclusion = _test_exclusion_sql(exclude_test_users)
    with engine.begin() as connection:
        row = connection.execute(text(f"""
            SELECT COUNT(DISTINCT (pe.venture_id, DATE(pe.created_at))) AS building_days,
                   COUNT(DISTINCT pe.venture_id) AS active_ventures
            FROM product_events pe
            WHERE pe.event_name IN ({_qualifying_events_sql_list()})
              AND pe.created_at >= NOW() - INTERVAL '1 day' * :days
              AND {exclusion}
        """), {"days": window_days}).mappings().first()

    active = row["active_ventures"] or 0
    building_days = row["building_days"] or 0
    return {
        "window_days": window_days,
        "meaningful_building_days": building_days,
        "active_ventures": active,
        "building_days_per_active_venture": round(building_days / active, 2) if active else None,
    }


def get_engagement_counts_report(window_days: int, exclude_test_users: bool = True) -> dict:
    """Captures / Active Venture and Actions Completed / Active Venture --
    Part 11's own two named engagement ratios. Denominator is the SAME
    active-venture count get_north_star_report() already computes, not a
    second, possibly-inconsistent definition of "active"."""
    exclusion = _test_exclusion_sql(exclude_test_users)
    with engine.begin() as connection:
        counts = connection.execute(text(f"""
            SELECT
                COUNT(*) FILTER (WHERE pe.event_name = 'capture_recorded') AS captures,
                COUNT(*) FILTER (WHERE pe.event_name = 'action_completed') AS actions_completed,
                COUNT(DISTINCT pe.venture_id) AS active_ventures
            FROM product_events pe
            WHERE pe.event_name IN ({_qualifying_events_sql_list()})
              AND pe.created_at >= NOW() - INTERVAL '1 day' * :days
              AND {exclusion}
        """), {"days": window_days}).mappings().first()

    active = counts["active_ventures"] or 0
    return {
        "window_days": window_days,
        "captures": counts["captures"] or 0,
        "actions_completed": counts["actions_completed"] or 0,
        "active_ventures": active,
        "captures_per_active_venture": round((counts["captures"] or 0) / active, 2) if active else None,
        "actions_completed_per_active_venture": round((counts["actions_completed"] or 0) / active, 2) if active else None,
    }


def get_activation_report(window_days: int, exclude_test_users: bool = True, venture_ids: list[int] | None = None) -> dict:
    """
    Part 8's own investigation, resolved: "venture_created + an
    immediately-populated recommendation" was rejected as too weak --
    compute_vps() always returns SOME model_result synchronously at
    creation, so virtually every venture would "activate" by that
    definition regardless of whether the founder ever did anything real.

    ACTIVATION, as implemented: a venture counts as activated if it
    performed >=1 qualifying building event (the same set the North Star
    uses) within 24 hours of its own venture_created event. This is
    venture-level (not session-level -- no session infrastructure exists
    anywhere in this codebase), anchored on a real, already-logged
    timestamp pair, and requires genuine founder-initiated follow-through,
    not just seeing a recommendation SIE computed automatically.
    """
    exclusion = _test_exclusion_sql(exclude_test_users)
    # venture_ids: None in every real call site (the admin endpoint never
    # passes it) -- exists solely so this file's own hand-calculated-
    # fixture test can scope a report to exactly its own fixture
    # ventures, isolated from whatever other real/test data happens to
    # already be in this shared dev database.
    scope = "AND pe.venture_id = ANY(:venture_ids)" if venture_ids else ""
    with engine.begin() as connection:
        row = connection.execute(text(f"""
            WITH created AS (
                SELECT pe.venture_id, pe.created_at
                FROM product_events pe
                WHERE pe.event_name = 'venture_created'
                  AND pe.created_at >= NOW() - INTERVAL '1 day' * :days
                  AND {exclusion}
                  {scope}
            )
            SELECT
                COUNT(*) AS total_created,
                COUNT(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1 FROM product_events q
                        WHERE q.venture_id = created.venture_id
                          AND q.event_name IN ({_qualifying_events_sql_list()})
                          AND q.created_at > created.created_at
                          AND q.created_at <= created.created_at + INTERVAL '24 hours'
                    )
                ) AS activated_count
            FROM created
        """), {"days": window_days, "venture_ids": venture_ids}).mappings().first()

    total = row["total_created"] or 0
    activated = row["activated_count"] or 0
    return {
        "window_days": window_days,
        "ventures_created": total,
        "activated": activated,
        "activation_rate": round(activated / total, 4) if total else None,
    }


def get_retention_report(lookback_days: int = 60, exclude_test_users: bool = True, venture_ids: list[int] | None = None) -> dict:
    """
    Part 9. Venture-level (explicitly labeled as such -- a single founder
    can own multiple ventures, and every other Phase 22-27 metric already
    treats a venture, not a founder, as the unit of analysis). Cohorted
    on venture_created (not a separate "activation timestamp" row -- a
    deliberate V1 simplification, documented in
    docs/product/PRODUCT_ANALYTICS_V1.md, that keeps this one query
    readable instead of introducing a second cohort-anchor concept).

    W1 = among ventures that (a) were created between 14 and `lookback_days`
    ago (so their day 7-13 window has actually elapsed) and (b) activated
    (per get_activation_report()'s own definition), what fraction
    performed >=1 qualifying event during days 7-13 after creation.

    D1/D7/D30 are simpler point checks: of the SAME activated cohort,
    what fraction had >=1 qualifying event at all within 1/7/30 days of
    creation (cumulative, not "on exactly that day").
    """
    qualifying = _qualifying_events_sql_list()
    exclusion = _test_exclusion_sql(exclude_test_users)
    scope = "AND pe.venture_id = ANY(:venture_ids)" if venture_ids else ""
    with engine.begin() as connection:
        row = connection.execute(text(f"""
            WITH cohort AS (
                SELECT pe.venture_id, pe.created_at
                FROM product_events pe
                WHERE pe.event_name = 'venture_created'
                  AND pe.created_at <= NOW() - INTERVAL '13 days'
                  AND pe.created_at >= NOW() - INTERVAL '1 day' * :lookback
                  AND {exclusion}
                  {scope}
            ),
            activated AS (
                SELECT cohort.venture_id, cohort.created_at
                FROM cohort
                WHERE EXISTS (
                    SELECT 1 FROM product_events q
                    WHERE q.venture_id = cohort.venture_id
                      AND q.event_name IN ({qualifying})
                      AND q.created_at > cohort.created_at
                      AND q.created_at <= cohort.created_at + INTERVAL '24 hours'
                )
            )
            SELECT
                COUNT(*) AS activated_total,
                COUNT(*) FILTER (WHERE EXISTS (
                    SELECT 1 FROM product_events q
                    WHERE q.venture_id = activated.venture_id
                      AND q.event_name IN ({qualifying})
                      AND q.created_at >= activated.created_at + INTERVAL '7 days'
                      AND q.created_at < activated.created_at + INTERVAL '14 days'
                )) AS retained_w1,
                COUNT(*) FILTER (WHERE EXISTS (
                    SELECT 1 FROM product_events q
                    WHERE q.venture_id = activated.venture_id
                      AND q.event_name IN ({qualifying})
                      AND q.created_at <= activated.created_at + INTERVAL '1 day'
                )) AS active_d1,
                COUNT(*) FILTER (WHERE EXISTS (
                    SELECT 1 FROM product_events q
                    WHERE q.venture_id = activated.venture_id
                      AND q.event_name IN ({qualifying})
                      AND q.created_at <= activated.created_at + INTERVAL '7 days'
                )) AS active_d7,
                COUNT(*) FILTER (WHERE EXISTS (
                    SELECT 1 FROM product_events q
                    WHERE q.venture_id = activated.venture_id
                      AND q.event_name IN ({qualifying})
                      AND q.created_at <= activated.created_at + INTERVAL '30 days'
                )) AS active_d30
            FROM activated
        """), {"lookback": lookback_days, "venture_ids": venture_ids}).mappings().first()

    total = row["activated_total"] or 0

    def _rate(count):
        return round(count / total, 4) if total else None

    return {
        "lookback_days": lookback_days,
        "cohort_unit": "venture",
        "activated_cohort_size": total,
        "w1_retention": _rate(row["retained_w1"] or 0),
        "d1_retention": _rate(row["active_d1"] or 0),
        "d7_retention": _rate(row["active_d7"] or 0),
        "d30_retention": _rate(row["active_d30"] or 0),
    }


def get_distribution_report(window_days: int, exclude_test_users: bool = True, venture_ids: list[int] | None = None) -> dict:
    """Part 11's distribution metrics, plus Part 12's funnel bottom two
    stages. share_activation_rate's denominator is ventures that reached
    'activated' status in the window (Part 25's own worked examples pair
    share activation against retained/activated ventures, not all-time
    venture count) -- ventures that never really got going are not a fair
    denominator for "did the founder choose to share.\""""
    exclusion = _test_exclusion_sql(exclude_test_users)
    scope = "AND pe.venture_id = ANY(:venture_ids)" if venture_ids else ""
    with engine.begin() as connection:
        activation = connection.execute(text(f"""
            WITH created AS (
                SELECT pe.venture_id, pe.created_at
                FROM product_events pe
                WHERE pe.event_name = 'venture_created'
                  AND pe.created_at >= NOW() - INTERVAL '1 day' * :days
                  AND {exclusion}
                  {scope}
            ),
            activated AS (
                SELECT created.venture_id FROM created
                WHERE EXISTS (
                    SELECT 1 FROM product_events q
                    WHERE q.venture_id = created.venture_id
                      AND q.event_name IN ({_qualifying_events_sql_list()})
                      AND q.created_at > created.created_at
                      AND q.created_at <= created.created_at + INTERVAL '24 hours'
                )
            )
            SELECT
                (SELECT COUNT(*) FROM activated) AS activated_total,
                (SELECT COUNT(DISTINCT pe.venture_id) FROM product_events pe
                    WHERE pe.event_name = 'snapshot_enabled'
                      AND pe.venture_id IN (SELECT venture_id FROM activated)
                      AND {exclusion}
                ) AS shared_among_activated
        """), {"days": window_days, "venture_ids": venture_ids}).mappings().first()

        counts = connection.execute(text(f"""
            SELECT
                COUNT(*) FILTER (WHERE pe.event_name = 'snapshot_enabled') AS snapshots_enabled,
                COUNT(*) FILTER (WHERE pe.event_name = 'snapshot_link_copied') AS links_copied,
                COUNT(*) FILTER (WHERE pe.event_name = 'snapshot_viewed_publicly') AS public_views,
                COUNT(*) FILTER (WHERE pe.event_name = 'snapshot_cta_clicked') AS cta_clicks,
                COUNT(*) FILTER (WHERE pe.event_name = 'venture_created' AND pe.source = 'snapshot') AS ventures_created_from_snapshot
            FROM product_events pe
            WHERE pe.created_at >= NOW() - INTERVAL '1 day' * :days
              AND {exclusion}
              {scope}
        """), {"days": window_days, "venture_ids": venture_ids}).mappings().first()

    activated_total = activation["activated_total"] or 0
    shared = activation["shared_among_activated"] or 0
    public_views = counts["public_views"] or 0
    cta_clicks = counts["cta_clicks"] or 0
    created_from_snapshot = counts["ventures_created_from_snapshot"] or 0

    return {
        "window_days": window_days,
        "activated_ventures": activated_total,
        "snapshots_enabled": counts["snapshots_enabled"] or 0,
        "share_activation_rate": round(shared / activated_total, 4) if activated_total else None,
        "snapshot_links_copied": counts["links_copied"] or 0,
        "public_snapshot_views": public_views,
        "snapshot_cta_clicks": cta_clicks,
        "snapshot_cta_click_rate": round(cta_clicks / public_views, 4) if public_views else None,
        "ventures_created_from_snapshot": created_from_snapshot,
        "snapshot_to_venture_creation_rate": round(created_from_snapshot / public_views, 4) if public_views else None,
    }


def get_full_analytics_report(window_days: int) -> dict:
    """The one function the admin reporting endpoint calls -- assembles
    every report above for a single window, plus the fixed 60-day
    retention lookback (Part 14: 7-day and 30-day windows are both
    supported by passing window_days; retention always looks back far
    enough to have at least one fully-elapsed W1 cohort regardless of
    which window_days the caller asked for)."""
    return {
        "north_star": get_north_star_report(window_days),
        "activation": get_activation_report(window_days),
        "retention": get_retention_report(),
        "meaningful_building_days": get_meaningful_building_days_report(window_days),
        "engagement": get_engagement_counts_report(window_days),
        "distribution": get_distribution_report(window_days),
    }


# ---------------------------------------------------------------------------
# Phase 31 -- Venture -> Startup Graduation V1.
#
# Closes the seam Phase 30's own audit identified: modeled_ventures and
# startups have zero database relationship, and the only prior bridge
# (lib/ventureToStartupHandoff.ts) carries forward free text only, never
# a durable link. This section adds exactly one new table --
# venture_graduations -- a pure relationship/provenance record. It never
# copies VentureAssumptions into startups (which has no columns to
# receive them -- canonical_name/normalized_name/created_at only, see
# create_startups_table()'s own schema); the founder's structured venture
# context instead flows through the EXISTING /analyze pipeline as
# reviewable free text (see app/api.py's build_graduation_prefill_text()),
# so SPS independently re-derives its own evidence/confidence exactly as
# it does for any other submission -- no second scoring system, no
# provenance system, no fabricated evidence.
#
# Graduation is always founder-initiated (POST /ventures/{id}/graduate).
# Nothing in this section is ever called from a background job, a
# migration, or in response to a VPS value -- grep app/ for
# "create_venture_graduation(" to confirm the one real call site.
#
# MEMBERSHIP INVARIANT PRESERVED: this section never inserts into
# startup_memberships directly. It calls the EXISTING, unchanged
# approve_startup_claim() -- still the only function in this codebase
# that may do that insert (test_no_new_membership_write_path remains
# true) -- immediately after creating a claim whose provenance is
# unambiguous (see create_venture_graduation()'s own docstring).
# ---------------------------------------------------------------------------


class StartupNameCollisionError(Exception):
    """Raised when graduation would otherwise create a startup whose
    normalized name collides with an EXISTING startup the founder does
    not already own. Deliberately fails closed rather than silently
    attaching the founder's venture to a stranger's analyzed company
    (Phase 30's own explicit finding: startups.normalized_name is
    globally unique and get_or_create_startup()'s ON CONFLICT DO NOTHING
    would otherwise resolve to whatever row already holds that name,
    regardless of who created it or what it represents). Never resolved
    by fuzzy matching, AI, or an automatic rename -- Part 13's own
    explicit instruction: "Never merge companies automatically based on
    name." The founder must pick a different name, or -- if the existing
    startup really is already theirs -- use the connect-existing-startup
    path instead, which this error's own caller directs them toward."""


class StartupAlreadyGraduatedError(Exception):
    """Raised when a graduation attempt's target startup already has a
    DIFFERENT venture's graduation linkage -- the
    venture_graduations_startup_id_key UNIQUE constraint's own violation,
    translated into a clean application-level error the same way
    StartupNameCollisionError translates the startups.normalized_name
    constraint. Reachable only via the "connect an existing startup"
    path (Part 13): a brand new startup this function just created can
    never already be graduation-linked to anything. Never resolved
    automatically -- a startup can only ever be one venture's origin
    story."""


def create_venture_graduations_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS venture_graduations (
                id SERIAL PRIMARY KEY,
                venture_id INTEGER NOT NULL UNIQUE
                    REFERENCES modeled_ventures(id) ON DELETE CASCADE,
                startup_id INTEGER NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                trigger TEXT NOT NULL CHECK (trigger IN ('suggested', 'manual')),
                connected_existing_startup BOOLEAN NOT NULL DEFAULT FALSE,
                fields_transferred_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_venture_graduations_startup
            ON venture_graduations (startup_id)
        """))

    print("venture_graduations table created successfully.")


def add_venture_graduations_startup_unique_constraint():
    """
    Phase 31A -- Graduation Integrity Hardening, database invariant
    audit (finding #3). A startup may be the graduation target of AT
    MOST ONE venture -- without this, "connect an existing startup"
    (Part 13) could let a second, unrelated venture attach itself to a
    startup that already has an originating venture, leaving
    get_venture_graduation_by_startup() to arbitrarily pick one of two
    equally-valid graduation rows for the Founder Workspace's "Created
    from your X venture" acknowledgment -- silently wrong provenance,
    never surfaced as an error. venture_id already had its own UNIQUE
    constraint (a venture can graduate at most once); this closes the
    matching gap on the startup side.

    Additive-only migration, matching this file's own established
    try/except-swallow idiom (see add_venture_share_columns() for the
    same pattern) -- Postgres has no `ADD CONSTRAINT IF NOT EXISTS`, so a
    second run against a table that already has this constraint simply
    hits (and swallows) a "constraint already exists" error, exactly
    like every ADD COLUMN migration in this file already does for its
    own re-run case.
    """
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                ALTER TABLE venture_graduations
                ADD CONSTRAINT venture_graduations_startup_id_key UNIQUE (startup_id)
            """))
        print("venture_graduations_startup_id_key constraint added")
    except Exception as e:
        print("venture_graduations_startup_id_key migration skipped", e)


def get_venture_graduation_for_owner(user_id: str, venture_id: int):
    """The caller's own graduation record for this venture, or None if it
    has never graduated. Scoped to user_id in the SQL itself (the venture
    ownership check this codebase's other per-user queries already use),
    not merely by trusting a caller-supplied venture_id -- so this can
    never leak another user's graduation linkage even if called with a
    venture_id that exists but belongs to someone else (it simply returns
    None, matching _require_owned_venture()'s own "venture not found"
    framing at the API layer)."""
    with engine.begin() as connection:
        row = connection.execute(text("""
            SELECT vg.id, vg.venture_id, vg.startup_id, vg.trigger,
                   vg.connected_existing_startup, vg.created_at,
                   s.canonical_name AS startup_name
            FROM venture_graduations vg
            JOIN modeled_ventures mv ON mv.id = vg.venture_id
            JOIN startups s ON s.id = vg.startup_id
            WHERE vg.venture_id = :venture_id AND mv.user_id = :user_id
        """), {"venture_id": venture_id, "user_id": user_id}).mappings().first()

        return dict(row) if row is not None else None


def get_venture_graduation_by_startup(startup_id: int):
    """The 'created from your venture' acknowledgment Founder Workspace
    shows (Part 11) -- looked up by startup_id, which
    get_founder_startup_workspace()'s own caller already has and has
    already verified membership for (RequireStartupMember runs first at
    the API layer). Returns venture name/id only -- never any venture
    assumption/evidence content -- so Founder Workspace can render one
    restrained link without a second, wider read of the venture itself."""
    with engine.begin() as connection:
        row = connection.execute(text("""
            SELECT vg.venture_id, mv.name AS venture_name
            FROM venture_graduations vg
            JOIN modeled_ventures mv ON mv.id = vg.venture_id
            WHERE vg.startup_id = :startup_id
        """), {"startup_id": startup_id}).mappings().first()

        return dict(row) if row is not None else None


def resolve_linked_venture_for_owned_startup(user_id: str, startup_id: int) -> int | None:
    """
    Phase 37B -- Company Identity + Workspace Routing Bridge. The one
    canonical resolution rule for "does this founder continue operating
    in the existing Venture Workspace for this startup, or does the
    legacy Founder Workspace apply?" -- see
    docs/product/SIE_UNIFIED_FOUNDER_WORKSPACE_ARCHITECTURE_V1.md's own
    Phase 37B section for the full design record.

    Returns the linked venture_id ONLY when BOTH hold:
      1. a venture_graduations row links this exact startup_id to some venture, AND
      2. that venture's own modeled_ventures.user_id matches user_id.

    Deliberately NOT the same query as get_venture_graduation_by_startup()
    (which powers the unrelated "created from your X venture"
    acknowledgment already shown inside Founder Workspace, and does not
    filter by ownership -- that acknowledgment is historically true
    regardless of who's asking). A ROUTING decision must fail closed the
    moment the linked venture belongs to someone other than the caller --
    e.g. a co-founder who legitimately holds a startup_memberships row
    for this startup but never owned the venture that originally
    graduated into it must never be sent into a venture that isn't
    theirs. No company-name matching, no "latest venture", no inference
    of any kind -- only this exact, explicit link, ownership-checked.

    Callers are responsible for having already established the caller is
    a member of startup_id (RequireStartupMember) before calling this --
    this function does not re-check startup membership itself, matching
    this file's existing division of responsibility (see
    get_founder_startup_workspace()'s own docstring for the same split).
    """
    with engine.begin() as connection:
        return connection.execute(text("""
            SELECT vg.venture_id
            FROM venture_graduations vg
            JOIN modeled_ventures mv ON mv.id = vg.venture_id
            WHERE vg.startup_id = :startup_id AND mv.user_id = :user_id
        """), {"startup_id": startup_id, "user_id": user_id}).scalar()


def _find_venture_graduation_claim(user_id: str, startup_id: int, connection=None):
    """
    Phase 31A -- Graduation Integrity Hardening. The most recent
    startup_claims row tagged verification_method='venture_graduation'
    for this exact (user_id, startup_id) pair, or None. This is the ONLY
    signal used to tell "this startup was created by this exact user's
    own (possibly crashed) graduation attempt" apart from "this is really
    some other, unrelated company that happens to share a name" -- a
    plain "zero members, zero claims" check would NOT be safe here, since
    plenty of real, legitimately unclaimed startups exist from the
    ordinary /analyze pipeline (get_or_create_startup() never creates a
    membership or claim for anyone). Only a claim actually tagged
    'venture_graduation' from this exact user proves this history.

    Accepts an optional existing `connection` so this can run INSIDE
    resolve_startup_for_graduation()'s own transaction (atomic with the
    existence check that decides whether to recover or collide) as well
    as standalone (a fresh connection is opened when none is given).
    """
    query = text("""
        SELECT id, status FROM startup_claims
        WHERE user_id = :user_id AND startup_id = :startup_id
          AND verification_method = 'venture_graduation'
        ORDER BY submitted_at DESC
        LIMIT 1
    """)
    params = {"user_id": user_id, "startup_id": startup_id}

    if connection is not None:
        row = connection.execute(query, params).mappings().first()
    else:
        with engine.begin() as fresh_connection:
            row = fresh_connection.execute(query, params).mappings().first()

    return dict(row) if row is not None else None


def _resolve_existing_startup_for_graduation(
    connection, startup_id: int, user_id: str, company_name: str
) -> tuple[int, bool, int | None]:
    """
    Phase 31A -- Graduation Integrity Hardening. Shared collision/recovery
    decision for resolve_startup_for_graduation() -- used both when a
    startup with this name already existed before the call, and by the
    concurrent-insert-race fallback, so this decision is made in exactly
    one place rather than duplicated.

    Returns (startup_id, connected_existing_startup, pending_claim_id) --
    see resolve_startup_for_graduation()'s own docstring for the full
    contract.
    """
    already_member = connection.execute(text("""
        SELECT 1 FROM startup_memberships
        WHERE user_id = :user_id AND startup_id = :startup_id
    """), {"user_id": user_id, "startup_id": startup_id}).scalar()

    if already_member is not None:
        return startup_id, True, None

    own_claim = _find_venture_graduation_claim(user_id, startup_id, connection=connection)

    if own_claim is not None and own_claim["status"] in ("pending", "approved"):
        # Provably this exact user's own prior graduation attempt at this
        # exact startup -- recoverable, never a collision. If the claim
        # is already 'approved' but membership is somehow still missing
        # (only reachable via external interference, e.g. a membership
        # later revoked by hand -- never by graduation's own write
        # sequence), pending_claim_id=None tells
        # _ensure_graduation_membership() to create a fresh claim rather
        # than re-approve a claim that isn't pending.
        pending_claim_id = own_claim["id"] if own_claim["status"] == "pending" else None
        return startup_id, False, pending_claim_id

    raise StartupNameCollisionError(
        f"A startup named {company_name!r} already exists."
    )


def resolve_startup_for_graduation(company_name: str, user_id: str) -> tuple[int, bool, int | None]:
    """
    Returns (startup_id, connected_existing_startup, pending_claim_id).
    Deliberately NOT get_or_create_startup() -- that function's own ON
    CONFLICT DO NOTHING is correct for Analyze (any two analyses of "the
    same company" really should resolve to one shared startup, regardless
    of who submitted them), but wrong for graduation: a venture named the
    same as some OTHER user's already-analyzed company must never
    silently attach this founder's evidence to it.

    pending_claim_id is the id of a PENDING startup_claims row that
    create_venture_graduation() (via _ensure_graduation_membership()) must
    still approve to complete the membership grant -- None when
    membership is already fully granted, or when a fresh claim must be
    created from scratch instead of reusing an existing one.

    Phase 31A -- Graduation Integrity Hardening, finding #1. When a BRAND
    NEW startup is created, a pending startup_claims row
    (verification_method='venture_graduation') is now inserted in the
    SAME transaction as the startup itself. Before this fix, a crash
    between "create the startup" and "grant membership" (two separate
    transactions in the old design) left an ORPHAN startup with no
    durable trace of who created it or why -- a retry under the same
    company name would find that orphan, see the founder wasn't yet a
    member of it, and raise StartupNameCollisionError, PERMANENTLY
    locking the founder out of ever graduating under that exact name
    again (their own abandoned attempt blocked their own retry, with no
    way to recover it). Committing the claim atomically with the startup
    closes this: a retry can now always prove "this is provably my own
    prior attempt" (a venture_graduation-tagged claim from this exact
    user_id exists for this exact startup_id) apart from "this is really
    someone else's company" (no such claim exists) -- see
    _resolve_existing_startup_for_graduation() for the shared decision
    both this function's "already existed" branch and its
    concurrent-insert-race branch now use.

    (original semantics, otherwise unchanged):
    - No existing startup with this normalized name: creates a fresh row
      plus its own pending claim (see above), returns (new_id, False,
      claim_id).
    - An existing startup with this normalized name that the caller
      already has an approved membership for: returns (existing_id, True,
      None) -- the safe "connect existing startup" case (Part 13),
      exact-name-match plus already-verified ownership, never fuzzy
      matching.
    - An existing startup with this normalized name that the caller does
      NOT already own, but DOES have their own venture-graduation claim
      for (pending or approved): the founder's own recoverable orphan
      from a previous partial attempt.
    - An existing startup with this normalized name the caller has no
      relationship to at all: raises StartupNameCollisionError rather
      than ever attaching to it.
    """
    normalized_name = company_name.strip().lower() if company_name else ""

    if not normalized_name:
        raise ValueError("company_name must not be empty")

    try:
        with engine.begin() as connection:
            existing = connection.execute(text("""
                SELECT id FROM startups WHERE normalized_name = :normalized_name
            """), {"normalized_name": normalized_name}).mappings().first()

            if existing is not None:
                return _resolve_existing_startup_for_graduation(
                    connection, existing["id"], user_id, company_name
                )

            result = connection.execute(text("""
                INSERT INTO startups (canonical_name, normalized_name)
                VALUES (:canonical_name, :normalized_name)
                RETURNING id
            """), {
                "canonical_name": company_name.strip(),
                "normalized_name": normalized_name,
            })
            new_startup_id = result.scalar()

            # Atomic with the startup insert above -- see this function's
            # own docstring (Phase 31A, finding #1). Never routed through
            # create_startup_claim() itself: that function opens its OWN
            # transaction (which would defeat the atomicity this fix
            # exists for) and its already-member/already-pending guards
            # are moot anyway -- this startup did not exist a moment ago,
            # so neither condition can be true.
            claim_result = connection.execute(text("""
                INSERT INTO startup_claims (
                    user_id, startup_id, status, verification_method, justification
                )
                VALUES (
                    :user_id, :startup_id, 'pending', 'venture_graduation',
                    'Created via venture graduation.'
                )
                RETURNING id
            """), {"user_id": user_id, "startup_id": new_startup_id})

            return new_startup_id, False, claim_result.scalar()
    except IntegrityError:
        # Race: another request created a startup with this exact
        # normalized name between our SELECT and our INSERT above.
        #
        # Phase 31A -- Graduation Integrity Hardening, a SECOND bug this
        # phase's own real-concurrency test
        # (test_parallel_graduation_requests_converge_to_one_relationship)
        # caught directly: the ORIGINAL recovery code re-queried using
        # the SAME `connection` still inside the SAME `with engine.begin()`
        # block whose INSERT had just failed. Postgres aborts an ENTIRE
        # transaction the instant any statement inside it fails and
        # refuses every further command (`InFailedSqlTransaction`) until
        # a rollback happens -- so that re-query itself always raised a
        # second, worse error under a REAL concurrent race, rather than
        # ever actually recovering. Letting the IntegrityError propagate
        # all the way out of the `with` block above (instead of being
        # caught inside it) is what triggers SQLAlchemy's own
        # rollback-on-exception behavior; the retry below then opens a
        # genuinely FRESH transaction on a clean connection, exactly as
        # this function's own docstring describes.
        with engine.begin() as connection:
            existing_id = connection.execute(text("""
                SELECT id FROM startups WHERE normalized_name = :normalized_name
            """), {"normalized_name": normalized_name}).scalar()
            return _resolve_existing_startup_for_graduation(
                connection, existing_id, user_id, company_name
            )


def _ensure_graduation_membership(user_id: str, startup_id: int, pending_claim_id: int | None) -> None:
    """
    Phase 31A -- Graduation Integrity Hardening. Idempotent, self-healing
    membership grant -- the ONLY place graduation grants startup access,
    called from create_venture_graduation() BEFORE the venture_graduations
    row is inserted (see that function's own comment for why the
    ordering itself is the fix for finding #2). Reuses, never duplicates,
    the only code path allowed to write startup_memberships
    (create_startup_claim() + approve_startup_claim() -- self-approval is
    safe here for the same provenance reasoning this module's own
    venture_graduations section docstring already gives).

    Self-heals every reachable partial state on this exact
    (user_id, startup_id) pair:
      - already a member -- no-op, nothing to do (this is what makes a
        RETRY of an already-fully-granted membership safe, and what makes
        the "connect existing startup" path -- which always arrives here
        already a member -- a guaranteed no-op).
      - a pending claim from a previous attempt exists (pending_claim_id
        given) -- approve it. approve_startup_claim() is itself a safe
        no-op if that claim is no longer pending for any reason.
      - no usable claim at all -- create one fresh and approve it,
        tolerating the race where membership or a pending claim from a
        concurrent request appeared between the caller's own check and
        this call.
    """
    if user_has_startup_membership(user_id, startup_id):
        return

    if pending_claim_id is not None:
        approve_startup_claim(pending_claim_id, admin_user_id=user_id)
        if user_has_startup_membership(user_id, startup_id):
            return
        # The claim we were given is no longer usable (e.g. rejected or
        # cancelled by an admin between attempts) -- fall through and
        # create a fresh one rather than leaving the founder stuck.

    try:
        claim_id = create_startup_claim(
            user_id=user_id,
            startup_id=startup_id,
            justification="Created via venture graduation.",
            contact_email=None,
            verification_method="venture_graduation",
        )
    except AlreadyMemberError:
        return
    except DuplicatePendingClaimError:
        # Race: a pending claim appeared between our check above and this
        # call (e.g. a concurrent retry) -- approve THAT one instead of
        # erroring.
        claim = _find_venture_graduation_claim(user_id, startup_id)
        if claim is not None and claim["status"] == "pending":
            approve_startup_claim(claim["id"], admin_user_id=user_id)
        return

    approve_startup_claim(claim_id, admin_user_id=user_id)


def create_venture_graduation(
    venture_id: int,
    startup_id: int,
    user_id: str,
    trigger: str,
    connected_existing_startup: bool,
    fields_transferred_count: int,
    pending_claim_id: int | None = None,
):
    """
    Idempotent from the founder's perspective (Part 7/12): the UNIQUE
    constraint on venture_graduations.venture_id is the database-level
    duplicate protection a disabled button alone can never guarantee
    (double-click, two parallel tabs, back-button-then-resubmit, a
    direct repeated API call -- all land here). ON CONFLICT DO NOTHING
    means a second graduation attempt for an already-graduated venture
    writes nothing and this function's caller (app/api.py) re-reads the
    existing row instead of treating a conflict as an error.

    Phase 31A -- Graduation Integrity Hardening, finding #2. Membership is
    now granted (via _ensure_graduation_membership(), self-healing) BEFORE
    the venture_graduations row is inserted, not after. This ordering is
    the fix: before this change, a crash between "insert
    venture_graduations" and "grant membership" (two separate
    transactions) left a venture that read as `graduated=true` whose
    founder had no actual startup_memberships row -- a state the old
    caller (the API endpoint) treated as fully successful on every
    subsequent read, since it only checked "does a venture_graduations
    row exist," never "does membership actually exist too." With
    membership granted FIRST, a venture_graduations row can only ever be
    inserted (this function raises before reaching that INSERT if
    _ensure_graduation_membership() itself fails) once membership is
    already durably committed -- "graduated but no membership" is no
    longer a reachable state at all, rather than a state that has to be
    detected and repaired on every read. The one remaining failure
    window (a crash strictly between the membership commit and the
    venture_graduations commit) is fully self-healing on a plain retry:
    resolve_startup_for_graduation() will find the startup with
    membership already granted (connected_existing_startup=True) and this
    function will insert the venture_graduations row it never got to the
    first time -- never a duplicate startup, never a duplicate
    membership, never a second claim.
    """
    _ensure_graduation_membership(user_id, startup_id, pending_claim_id)

    try:
        with engine.begin() as connection:
            result = connection.execute(text("""
                INSERT INTO venture_graduations (
                    venture_id, startup_id, user_id, trigger,
                    connected_existing_startup, fields_transferred_count
                )
                VALUES (
                    :venture_id, :startup_id, :user_id, :trigger,
                    :connected_existing_startup, :fields_transferred_count
                )
                ON CONFLICT (venture_id) DO NOTHING
                RETURNING id
            """), {
                "venture_id": venture_id,
                "startup_id": startup_id,
                "user_id": user_id,
                "trigger": trigger,
                "connected_existing_startup": connected_existing_startup,
                "fields_transferred_count": fields_transferred_count,
            })
            inserted_id = result.scalar()
    except IntegrityError as error:
        # ON CONFLICT (venture_id) DO NOTHING already absorbed the
        # expected idempotency case (this exact venture already
        # graduated) without ever reaching here -- any IntegrityError
        # that DOES reach here must be the OTHER unique constraint
        # (venture_graduations_startup_id_key, database invariant #3):
        # this startup already has a graduation link from a DIFFERENT
        # venture. Reachable only via "connect an existing startup"
        # (Part 13) -- a brand new startup this same call just created
        # can never already be linked to anything.
        raise StartupAlreadyGraduatedError(
            f"Startup {startup_id} is already linked to a different venture."
        ) from error

    if inserted_id is None:
        # Already graduated (idempotent no-op) -- caller re-reads via
        # get_venture_graduation_for_owner() rather than treating this as
        # an error. Membership was already (re-)ensured above regardless
        # of this outcome, which is exactly what self-heals a venture
        # whose ONE remaining failure window (see this function's own
        # docstring) was hit on a previous attempt.
        return None

    return inserted_id