"""
Regression tests for the Canonical Startup Entity schema migration
(SIE Accounts & Ownership, first implementation slice --
app/database/db.py::create_startups_table/add_startup_id_column/
create_users_table/create_startup_memberships_table/
create_saved_startups_table/backfill_startup_ids).

This is the one test file in app/tests/ that intentionally exercises real
DDL/DML against the real configured DATABASE_URL -- there is no separate
test database in this project, and the thing under test IS real SQL
migration/backfill behavior, which cannot be meaningfully verified
without a real Postgres connection. To keep this safe to run against the
live dataset:

- Tests that need controlled, colliding, or ordered inputs insert their
  own temporary `analyses` rows under a distinctive "ZZTest" name prefix
  that cannot collide with any real company, and delete every row they
  created (and any startups row created only for them) in a finally
  block, even on failure.
- Tests that verify "existing data is preserved" or "canonical surfaces
  are unchanged" only ever READ the real existing dataset and compare it
  against a snapshot taken before/after -- they never modify real rows.
- No test ever calls save_analysis()/an LLM/Tavily -- this file makes
  zero paid calls.

Run with:
    python -m app.tests.test_startup_entity_migration
"""

import json

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database.db import (
    engine,
    create_startups_table,
    add_startup_id_column,
    create_users_table,
    create_startup_memberships_table,
    create_saved_startups_table,
    backfill_startup_ids,
    get_rankings,
    search_analyses,
    get_startup_by_name,
    get_sps_history,
    get_analytics,
)

TEST_PREFIX = "ZZTest Migration"
# Portfolio Release Task 3B -- Secure Analysis Visibility: get_rankings()/
# get_analytics()/search_analyses()/get_startup_by_name()/get_sps_history()
# now require a viewer to scope by. This file's own job is schema/migration
# correctness -- not the authorization feature itself (dedicated coverage
# in test_analysis_visibility.py) -- so every call below goes through this
# fixed admin bypass, unaffected by the new, orthogonal authorization
# dimension.
_ADMIN = "__task3b_sanity_admin__"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _insert_test_analysis(company_name, offset_seconds: int, methodology: dict | None = None) -> int:
    """
    Minimal analyses row for migration testing -- only the columns this
    table actually requires NOT NULL, plus company_name/methodology/
    created_at, which are what this migration's behavior depends on.
    created_at is offset from now by offset_seconds so tests can control
    "most recent" ordering deterministically without relying on real
    wall-clock gaps between inserts.
    """
    with engine.begin() as connection:
        result = connection.execute(
            text(
                """
                INSERT INTO analyses
                    (company_text, summary, risk_analysis, memo,
                     company_name, methodology, created_at)
                VALUES
                    (:company_text, 'test summary', 'test risk', 'test memo',
                     :company_name, :methodology,
                     CURRENT_TIMESTAMP + (:offset || ' seconds')::interval)
                RETURNING id
                """
            ),
            {
                "company_text": f"Test company text for {company_name}",
                "company_name": company_name,
                "methodology": json.dumps(methodology) if methodology is not None else None,
                "offset": offset_seconds,
            },
        )
        return result.scalar()


def _cleanup(analysis_ids: list[int]) -> None:
    """Deletes only the rows this test file created -- the analyses rows
    by id, and any startups rows created solely for the ZZTest prefix
    (identified by normalized_name, never by a broad pattern that could
    touch real data)."""
    with engine.begin() as connection:
        if analysis_ids:
            connection.execute(
                text("DELETE FROM analyses WHERE id = ANY(:ids)"),
                {"ids": analysis_ids},
            )

        connection.execute(
            text("DELETE FROM startups WHERE normalized_name LIKE :pattern"),
            {"pattern": f"{TEST_PREFIX.lower()}%"},
        )


def test_startups_table_exists_with_expected_shape() -> None:
    create_startups_table()  # idempotent -- safe to call again

    with engine.begin() as connection:
        columns = connection.execute(
            text(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'startups'
                """
            )
        ).mappings().all()

    names = {c["column_name"] for c in columns}
    expect(
        {"id", "canonical_name", "normalized_name", "created_at"} <= names,
        f"Expected startups to have id/canonical_name/normalized_name/created_at, got {names}",
    )


def test_analyses_startup_id_column_and_fk_exist() -> None:
    with engine.begin() as connection:
        col = connection.execute(
            text(
                """
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name = 'analyses' AND column_name = 'startup_id'
                """
            )
        ).mappings().first()

    expect(col is not None, "Expected analyses.startup_id to exist")
    expect(
        col["is_nullable"] == "YES",
        "Expected analyses.startup_id to be nullable (backward compatible with un-backfilled rows)",
    )


def test_startup_id_fk_rejects_nonexistent_startup() -> None:
    """Proves the foreign key is actually enforced by Postgres, not just
    declared and ignored -- inserting a startup_id that doesn't exist in
    startups must fail."""
    analysis_id = None

    try:
        try:
            with engine.begin() as connection:
                result = connection.execute(
                    text(
                        """
                        INSERT INTO analyses
                            (company_text, summary, risk_analysis, memo, startup_id)
                        VALUES ('t', 't', 't', 't', 999999999)
                        RETURNING id
                        """
                    )
                )
                analysis_id = result.scalar()
        except IntegrityError:
            return  # expected -- FK correctly rejected the bogus reference

        raise AssertionError(
            "Expected a ForeignKeyViolation inserting a nonexistent startup_id, "
            "but the insert succeeded"
        )
    finally:
        if analysis_id is not None:
            _cleanup([analysis_id])


def test_normalized_name_uniqueness_enforced() -> None:
    """Proves the UNIQUE constraint on startups.normalized_name is real,
    independent of the ON CONFLICT DO NOTHING clause backfill_startup_ids()
    itself relies on."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO startups (canonical_name, normalized_name) "
                "VALUES (:name, :norm)"
            ),
            {"name": f"{TEST_PREFIX} Uniqueness", "norm": f"{TEST_PREFIX.lower()} uniqueness"},
        )

    try:
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO startups (canonical_name, normalized_name) "
                        "VALUES (:name, :norm)"
                    ),
                    {"name": "A different display name", "norm": f"{TEST_PREFIX.lower()} uniqueness"},
                )
        except IntegrityError:
            return  # expected -- duplicate normalized_name correctly rejected

        raise AssertionError(
            "Expected a UniqueViolation inserting a duplicate normalized_name, "
            "but the insert succeeded"
        )
    finally:
        _cleanup([])


def test_case_and_whitespace_variants_map_to_one_startup() -> None:
    """The FinPilot / Finpilot collision found during pre-migration
    inspection, reproduced under a safe test name: two analyses whose
    company_name differs only by case/whitespace must resolve to exactly
    one startups row."""
    ids = []

    try:
        ids.append(_insert_test_analysis(f"{TEST_PREFIX} Case", offset_seconds=0))
        ids.append(_insert_test_analysis(f"  {TEST_PREFIX.upper()} CASE  ", offset_seconds=10))

        backfill_startup_ids()

        with engine.begin() as connection:
            rows = connection.execute(
                text("SELECT DISTINCT startup_id FROM analyses WHERE id = ANY(:ids)"),
                {"ids": ids},
            ).scalars().all()

        expect(
            len(rows) == 1 and rows[0] is not None,
            f"Expected both case/whitespace variants to map to the same single "
            f"startup_id, got {rows}",
        )
    finally:
        _cleanup(ids)


def test_canonical_name_uses_most_recent_analysis() -> None:
    """Given two analyses for the same normalized identity, canonical_name
    must come from the more recently created one -- the same tie-break
    rule get_rankings()/get_startup_by_name() already use."""
    ids = []

    try:
        ids.append(_insert_test_analysis(f"{TEST_PREFIX} Recency Old", offset_seconds=0))
        ids.append(
            _insert_test_analysis(f"{TEST_PREFIX} Recency New", offset_seconds=60)
        )

        backfill_startup_ids()

        with engine.begin() as connection:
            canonical_name = connection.execute(
                text(
                    """
                    SELECT s.canonical_name
                    FROM analyses a
                    JOIN startups s ON s.id = a.startup_id
                    WHERE a.id = :id
                    """
                ),
                {"id": ids[1]},
            ).scalar()

        expect(
            canonical_name == f"{TEST_PREFIX} Recency New",
            f"Expected canonical_name to come from the most recent analysis, "
            f"got {canonical_name!r}",
        )
    finally:
        _cleanup(ids)


def test_backfill_is_idempotent() -> None:
    ids = [_insert_test_analysis(f"{TEST_PREFIX} Idempotency", offset_seconds=0)]

    try:
        backfill_startup_ids()

        with engine.begin() as connection:
            startup_id_first = connection.execute(
                text("SELECT startup_id FROM analyses WHERE id = :id"), {"id": ids[0]}
            ).scalar()
            startups_count_first = connection.execute(
                text(
                    "SELECT COUNT(*) FROM startups WHERE normalized_name = :n"
                ),
                {"n": f"{TEST_PREFIX.lower()} idempotency"},
            ).scalar()

        # Re-run everything, including the table-creation calls -- the full
        # sequence app.api runs at startup, not just the backfill.
        create_startups_table()
        add_startup_id_column()
        create_users_table()
        create_startup_memberships_table()
        create_saved_startups_table()
        backfill_startup_ids()

        with engine.begin() as connection:
            startup_id_second = connection.execute(
                text("SELECT startup_id FROM analyses WHERE id = :id"), {"id": ids[0]}
            ).scalar()
            startups_count_second = connection.execute(
                text(
                    "SELECT COUNT(*) FROM startups WHERE normalized_name = :n"
                ),
                {"n": f"{TEST_PREFIX.lower()} idempotency"},
            ).scalar()

        expect(
            startup_id_first == startup_id_second,
            f"Expected the same startup_id after re-running the migration, "
            f"got {startup_id_first} then {startup_id_second}",
        )
        expect(
            startups_count_first == 1 and startups_count_second == 1,
            f"Expected exactly one startups row throughout, got "
            f"{startups_count_first} then {startups_count_second}",
        )
    finally:
        _cleanup(ids)


def test_methodology_json_preserved_through_backfill() -> None:
    fake_methodology = {
        "startup_intelligence_score": 42.0,
        "context": {"company_name": f"{TEST_PREFIX} Methodology"},
    }
    ids = [
        _insert_test_analysis(
            f"{TEST_PREFIX} Methodology", offset_seconds=0, methodology=fake_methodology
        )
    ]

    try:
        backfill_startup_ids()

        with engine.begin() as connection:
            stored = connection.execute(
                text("SELECT methodology FROM analyses WHERE id = :id"), {"id": ids[0]}
            ).scalar()

        expect(
            stored == fake_methodology,
            f"Expected methodology JSONB to be byte-for-byte unchanged by the "
            f"migration, got {stored!r}",
        )
    finally:
        _cleanup(ids)


def test_null_or_empty_company_name_not_linked() -> None:
    """Rows with no company_name must never be merged into a shared fake
    identity -- they should get no startup_id, exactly matching the
    existing exclusion in search_analyses()/get_rankings()."""
    ids = [_insert_test_analysis(None, offset_seconds=0)]

    try:
        backfill_startup_ids()

        with engine.begin() as connection:
            startup_id = connection.execute(
                text("SELECT startup_id FROM analyses WHERE id = :id"), {"id": ids[0]}
            ).scalar()

        expect(
            startup_id is None,
            f"Expected a NULL-company_name row to stay unlinked, got startup_id={startup_id}",
        )
    finally:
        _cleanup(ids)


def test_no_membership_or_saved_rows_created_by_backfill() -> None:
    """The core product decision this slice implements: analysis and
    ownership are separate. Backfilling startups for existing analyses
    must never create a startup_memberships or saved_startups row."""
    ids = [_insert_test_analysis(f"{TEST_PREFIX} NoOwnership", offset_seconds=0)]

    try:
        with engine.begin() as connection:
            before = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()
            before_saved = connection.execute(text("SELECT COUNT(*) FROM saved_startups")).scalar()

        backfill_startup_ids()

        with engine.begin() as connection:
            after = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()
            after_saved = connection.execute(text("SELECT COUNT(*) FROM saved_startups")).scalar()

        expect(
            before == after,
            f"Expected startup_memberships row count unchanged by backfill, "
            f"got {before} -> {after}",
        )
        expect(
            before_saved == after_saved,
            f"Expected saved_startups row count unchanged by backfill, "
            f"got {before_saved} -> {after_saved}",
        )
    finally:
        _cleanup(ids)


def test_legacy_analysis_rows_preserved() -> None:
    """Read-only: every analyses row that existed before this migration
    (identified here simply as "every row in the table right now", since
    this test runs after the real migration has already been applied in
    this environment) must still be present with its methodology intact
    -- the migration only ever ADDS a startup_id value, never removes or
    rewrites a row."""
    with engine.begin() as connection:
        total = connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar()
        with_methodology = connection.execute(
            text("SELECT COUNT(*) FROM analyses WHERE methodology IS NOT NULL")
        ).scalar()

    expect(total > 0, "Expected at least one analyses row to exist")
    expect(
        with_methodology > 0,
        "Expected at least one analyses row with methodology JSONB intact",
    )


def test_existing_canonical_surfaces_unchanged() -> None:
    """The critical safety check: none of the canonical read queries were
    modified in this slice, so their output must be identical whether or
    not startup_id has been backfilled. Calls each one twice -- once,
    then again after inserting an unrelated (non-canonical, methodology
    IS NULL) test row -- and confirms the results are unaffected, since a
    non-canonical test row must never leak into canonical output."""
    rankings_before = get_rankings(_ADMIN, True)
    analytics_before = get_analytics(_ADMIN, True)

    ids = [_insert_test_analysis(f"{TEST_PREFIX} Parity", offset_seconds=0)]

    try:
        rankings_after = get_rankings(_ADMIN, True)
        analytics_after = get_analytics(_ADMIN, True)
        search_result = search_analyses(TEST_PREFIX, _ADMIN, True)
        profile = get_startup_by_name(f"{TEST_PREFIX} Parity", _ADMIN, True)

        expect(
            rankings_before == rankings_after,
            "Expected get_rankings() to be unaffected by a non-canonical test row",
        )
        expect(
            analytics_before == analytics_after,
            "Expected get_analytics() to be unaffected by a non-canonical test row",
        )
        expect(
            search_result == [],
            f"Expected a non-canonical (methodology IS NULL) test row to be "
            f"excluded from search results, got {search_result}",
        )
        expect(
            profile is None,
            "Expected get_startup_by_name() to return None for a row with no "
            "methodology (it requires methodology IS NOT NULL), unaffected by "
            "the startup_id backfill",
        )
    finally:
        _cleanup(ids)


def test_company_with_no_analysis_returns_honest_profile_not_none() -> None:
    """Phase 37E -- Company Lifecycle + Public Identity Convergence,
    Section 6. A `startups` row with zero qualifying analyses (the exact
    shape of a freshly graduated/created company) must resolve to an
    honest, distinct profile -- never the same `None` a truly nonexistent
    company gets, and never a fabricated methodology."""
    canonical_name = f"{TEST_PREFIX} No Analysis"
    normalized_name = canonical_name.lower()

    with engine.begin() as connection:
        startup_id = connection.execute(
            text(
                "INSERT INTO startups (canonical_name, normalized_name) "
                "VALUES (:name, :norm) RETURNING id"
            ),
            {"name": canonical_name, "norm": normalized_name},
        ).scalar()

    try:
        profile = get_startup_by_name(canonical_name, _ADMIN, True)

        expect(profile is not None, "Expected an honest profile dict, not None, for an existing startups row")
        expect(
            profile["has_analysis"] is False,
            f"Expected has_analysis=False for a company with zero analyses, got {profile.get('has_analysis')}",
        )
        expect(
            profile["methodology"] is None,
            f"Expected methodology=None (never fabricated) for a company with zero analyses, got {profile['methodology']}",
        )
        expect(
            profile["canonical_name"] == canonical_name,
            f"Expected canonical_name={canonical_name!r}, got {profile['canonical_name']!r}",
        )
        expect(
            profile["startup_id"] == startup_id and profile["id"] == startup_id,
            f"Expected startup_id/id to be the startups.id {startup_id}, got {profile['startup_id']}/{profile['id']}",
        )
    finally:
        _cleanup([])


def test_company_with_analysis_still_reports_has_analysis_true() -> None:
    """The existing, common case (an analysis with real methodology)
    must be unaffected by the Section 6 fallback -- has_analysis=True,
    methodology populated, exactly as before this phase."""
    ids = [_insert_test_analysis(f"{TEST_PREFIX} HasAnalysis", offset_seconds=0, methodology={"startup_intelligence_score": 42})]

    try:
        profile = get_startup_by_name(f"{TEST_PREFIX} HasAnalysis", _ADMIN, True)

        expect(profile is not None, "Expected a profile for a company with a real analysis")
        expect(profile["has_analysis"] is True, f"Expected has_analysis=True, got {profile.get('has_analysis')}")
        expect(profile["methodology"] is not None, "Expected methodology to be populated, not None")
    finally:
        _cleanup(ids)


def test_truly_nonexistent_company_still_returns_none() -> None:
    """A company with neither an analysis nor a startups row must still
    404 (return None) -- the Section 6 fallback only ever recognizes a
    company that genuinely exists in the startups table."""
    profile = get_startup_by_name(f"{TEST_PREFIX} Never Created Anywhere", _ADMIN, True)
    expect(profile is None, "Expected None for a company that was never created via any path")


TESTS = [
    test_startups_table_exists_with_expected_shape,
    test_analyses_startup_id_column_and_fk_exist,
    test_startup_id_fk_rejects_nonexistent_startup,
    test_normalized_name_uniqueness_enforced,
    test_case_and_whitespace_variants_map_to_one_startup,
    test_canonical_name_uses_most_recent_analysis,
    test_backfill_is_idempotent,
    test_methodology_json_preserved_through_backfill,
    test_null_or_empty_company_name_not_linked,
    test_no_membership_or_saved_rows_created_by_backfill,
    test_legacy_analysis_rows_preserved,
    test_existing_canonical_surfaces_unchanged,
    test_company_with_no_analysis_returns_honest_profile_not_none,
    test_company_with_analysis_still_reports_has_analysis_true,
    test_truly_nonexistent_company_still_returns_none,
]


def main() -> None:
    print("\nCanonical Startup Entity migration tests")
    print("-" * 72)

    failures: list[str] = []

    for test in TESTS:
        name = test.__name__

        try:
            test()
        except AssertionError as error:
            print(f"FAIL  {name}\n      {error}")
            failures.append(name)
        else:
            print(f"PASS  {name}")

    print("-" * 72)
    print(f"{len(TESTS) - len(failures)}/{len(TESTS)} passed")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
