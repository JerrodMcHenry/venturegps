"""
Database-level protection of v2.source, exercised with DIRECT SQL that bypasses
the repository: the database, not Python, must refuse these.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

pytestmark = pytest.mark.db

VALID = dict(source_key="sec_edgar", source_name="SEC EDGAR", source_type="government_regulatory",
             collection_method="api", source_url="https://www.sec.gov/edgar", is_active=True)


def insert(engine, **overrides) -> int:
    values = {**VALID, **overrides}
    cols = ", ".join(values)
    binds = ", ".join(f":{k}" for k in values)
    with engine.begin() as conn:
        return conn.execute(text(f"INSERT INTO v2.source ({cols}) VALUES ({binds}) RETURNING id"), values).scalar()


def fetch(engine, source_id):
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT * FROM v2.source WHERE id = :i"), {"i": source_id}).mappings().one())


def refused(engine, sql, params=None, *, exc=IntegrityError):
    """Run `sql` in its own transaction; assert the database refused it; return the diagnostics."""
    with pytest.raises(exc) as info:
        with engine.begin() as conn:
            conn.execute(text(sql), params or {})
    return getattr(info.value.orig, "diag", None), str(info.value.orig)


# ---------------- immutability (trigger)

@pytest.mark.parametrize(
    "column, new_value",
    [("source_key", "other_key"), ("source_type", "research"), ("collection_method", "feed")],
)
def test_direct_sql_cannot_mutate_immutable_identity_and_configuration(migrated_db, column, new_value):
    source_id = insert(migrated_db)
    before = fetch(migrated_db, source_id)
    _, message = refused(migrated_db, f"UPDATE v2.source SET {column} = :v WHERE id = :i", {"v": new_value, "i": source_id})
    assert f"v2.source.{column} is immutable" in message
    assert fetch(migrated_db, source_id) == before


def test_direct_sql_cannot_mutate_created_at_or_id(migrated_db):
    source_id = insert(migrated_db)
    before = fetch(migrated_db, source_id)
    _, message = refused(migrated_db, "UPDATE v2.source SET created_at = created_at - interval '1 day' WHERE id = :i", {"i": source_id})
    assert "created_at is immutable" in message
    # GENERATED ALWAYS refuses this before the trigger even runs (ProgrammingError); the trigger also guards id.
    refused(migrated_db, "UPDATE v2.source SET id = id + 1000 WHERE id = :i", {"i": source_id}, exc=(ProgrammingError, IntegrityError))
    assert fetch(migrated_db, source_id) == before


def test_an_immutable_change_bundled_with_a_legal_change_rolls_the_whole_update_back(migrated_db):
    source_id = insert(migrated_db)
    before = fetch(migrated_db, source_id)
    refused(migrated_db, "UPDATE v2.source SET source_name = 'Renamed', source_type = 'research' WHERE id = :i", {"i": source_id})
    assert fetch(migrated_db, source_id) == before


def test_setting_an_immutable_column_to_its_current_value_is_allowed(migrated_db):
    source_id = insert(migrated_db)
    with migrated_db.begin() as conn:
        conn.execute(text("UPDATE v2.source SET source_key = source_key, source_type = source_type WHERE id = :i"), {"i": source_id})


def test_mutable_fields_can_be_changed_by_direct_sql(migrated_db):
    source_id = insert(migrated_db)
    with migrated_db.begin() as conn:
        conn.execute(text("UPDATE v2.source SET source_name = 'New name', source_url = NULL, is_active = false WHERE id = :i"), {"i": source_id})
    row = fetch(migrated_db, source_id)
    assert (row["source_name"], row["source_url"], row["is_active"]) == ("New name", None, False)


# ---------------- timestamps (trigger)

def test_created_at_and_updated_at_are_assigned_by_the_database_and_equal_at_insert(migrated_db):
    source_id = insert(migrated_db)
    row = fetch(migrated_db, source_id)
    assert row["created_at"] == row["updated_at"] and row["created_at"].tzinfo is not None


def test_caller_supplied_timestamps_are_ignored_on_insert(migrated_db):
    source_id = insert(migrated_db, created_at="2000-01-01T00:00:00+00:00", updated_at="1999-01-01T00:00:00+00:00")
    row = fetch(migrated_db, source_id)
    assert row["created_at"].year >= 2026 and row["updated_at"] == row["created_at"]


def test_updated_at_moves_only_when_a_mutable_field_changes_and_the_caller_cannot_set_it(migrated_db):
    source_id = insert(migrated_db)
    original = fetch(migrated_db, source_id)

    with migrated_db.begin() as conn:  # no-op update: nothing changes, not even updated_at
        conn.execute(text("UPDATE v2.source SET source_name = source_name WHERE id = :i"), {"i": source_id})
    assert fetch(migrated_db, source_id)["updated_at"] == original["updated_at"]

    with migrated_db.begin() as conn:  # caller tries to backdate updated_at while changing nothing
        conn.execute(text("UPDATE v2.source SET updated_at = '2001-01-01T00:00:00+00:00' WHERE id = :i"), {"i": source_id})
    assert fetch(migrated_db, source_id)["updated_at"] == original["updated_at"]

    with migrated_db.begin() as conn:  # a real change, with a caller-chosen updated_at that must be overridden
        conn.execute(text("UPDATE v2.source SET is_active = false, updated_at = '2001-01-01T00:00:00+00:00' WHERE id = :i"), {"i": source_id})
    changed = fetch(migrated_db, source_id)
    assert changed["updated_at"] > original["updated_at"] and changed["created_at"] == original["created_at"]


# ---------------- uniqueness, nullability, generated id

def test_duplicate_source_key_is_rejected_by_the_database(migrated_db):
    insert(migrated_db)
    diag, _ = refused(migrated_db, "INSERT INTO v2.source (source_key, source_name, source_type, collection_method, is_active) "
                                   "VALUES ('sec_edgar', 'Different', 'research', 'feed', true)")
    assert diag.constraint_name == "uq_source_source_key"


def test_name_and_url_are_not_unique_so_they_are_not_identity(migrated_db):
    first = insert(migrated_db, source_key="one_source")
    second = insert(migrated_db, source_key="two_source")  # same name, same URL, same type, same method
    assert first != second


@pytest.mark.parametrize("column", ["source_key", "source_name", "source_type", "collection_method", "is_active"])
def test_not_null_columns_reject_null(migrated_db, column):
    diag, message = refused(migrated_db, f"INSERT INTO v2.source (source_key, source_name, source_type, collection_method, is_active) "
                                         f"SELECT " + ", ".join("NULL" if c == column else f"'{VALID[c]}'" if c != "is_active" else "true"
                                                                for c in ("source_key", "source_name", "source_type", "collection_method", "is_active")))
    assert diag.column_name == column


def test_is_active_has_no_default_so_it_must_be_stated(migrated_db):
    refused(migrated_db, "INSERT INTO v2.source (source_key, source_name, source_type, collection_method) "
                         "VALUES ('sec_edgar', 'SEC', 'government_regulatory', 'api')")


def test_source_url_is_nullable(migrated_db):
    assert fetch(migrated_db, insert(migrated_db, source_url=None))["source_url"] is None


def test_the_id_is_generated_always(migrated_db):
    refused(migrated_db, "INSERT INTO v2.source (id, source_key, source_name, source_type, collection_method, is_active) "
                         "VALUES (999, 'x_key', 'n', 'other', 'api', true)", exc=(ProgrammingError, IntegrityError))


# ---------------- CHECK constraints

@pytest.mark.parametrize("value", ["research ", "Research", "government", "", "unknown", "OTHER"])
def test_invalid_source_type_is_rejected(migrated_db, value):
    diag, _ = refused(migrated_db, "INSERT INTO v2.source (source_key, source_name, source_type, collection_method, is_active) "
                                   "VALUES ('x_key', 'n', :v, 'api', true)", {"v": value})
    assert diag.constraint_name == "ck_source_source_type_allowed"


@pytest.mark.parametrize("value", ["scrape", "API", "http", "", "manual"])
def test_invalid_collection_method_is_rejected(migrated_db, value):
    diag, _ = refused(migrated_db, "INSERT INTO v2.source (source_key, source_name, source_type, collection_method, is_active) "
                                   "VALUES ('x_key', 'n', 'other', :v, true)", {"v": value})
    assert diag.constraint_name == "ck_source_collection_method_allowed"


@pytest.mark.parametrize("key", ["", "a", "A_b", "1ab", "_ab", "sec-edgar", "sec edgar", "x" * 65, "sëc", "ab\n"])
def test_invalid_source_key_shape_is_rejected(migrated_db, key):
    diag, _ = refused(migrated_db, "INSERT INTO v2.source (source_key, source_name, source_type, collection_method, is_active) "
                                   "VALUES (:k, 'n', 'other', 'api', true)", {"k": key})
    assert diag.constraint_name == "ck_source_source_key_shape"


@pytest.mark.parametrize("name", ["", " leading", "trailing ", "   ", "line\nbreak", "tab\there", "nul\u0001ctl", "x" * 201, "del\u007f"])
def test_invalid_source_name_is_rejected(migrated_db, name):
    diag, _ = refused(migrated_db, "INSERT INTO v2.source (source_key, source_name, source_type, collection_method, is_active) "
                                   "VALUES ('x_key', :n, 'other', 'api', true)", {"n": name})
    assert diag.constraint_name == "ck_source_source_name_valid"


@pytest.mark.parametrize("name", ["A", "SEC EDGAR", "x" * 200, "Crunchbase (public) ✓"])
def test_valid_source_names_are_accepted(migrated_db, name):
    assert fetch(migrated_db, insert(migrated_db, source_name=name))["source_name"] == name


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com/x", "file:///etc/passwd", "javascript:alert(1)", "example.com", "//example.com",
     "https://user:pw@example.com/", "https://user@example.com/", "https://example.com@evil.com/", "http://a:b@[::1]/",
     "https:// example.com", "https://example.com/a b", "https://example.com/\n", "https://example.com\\evil",
     "https://exämple.com", "https://", "https:///path", "https://example.com/" + "a" * 2048, ""],
)
def test_invalid_source_url_is_rejected(migrated_db, url):
    diag, _ = refused(migrated_db, "INSERT INTO v2.source (source_key, source_name, source_type, collection_method, source_url, is_active) "
                                   "VALUES ('x_key', 'n', 'other', 'api', :u, true)", {"u": url})
    assert diag.constraint_name == "ck_source_source_url_valid"


@pytest.mark.parametrize("url", ["https://example.com", "http://example.com:8080/a?b=c#d", "HTTPS://Example.COM/x", "https://[2001:db8::1]/x"])
def test_valid_source_urls_are_accepted(migrated_db, url):
    assert fetch(migrated_db, insert(migrated_db, source_url=url))["source_url"] == url


def test_updates_are_also_checked(migrated_db):
    source_id = insert(migrated_db)
    refused(migrated_db, "UPDATE v2.source SET source_url = 'ftp://example.com' WHERE id = :i", {"i": source_id})
    refused(migrated_db, "UPDATE v2.source SET source_name = ' padded ' WHERE id = :i", {"i": source_id})
    refused(migrated_db, "UPDATE v2.source SET is_active = NULL WHERE id = :i", {"i": source_id})
