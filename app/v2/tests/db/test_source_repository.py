"""The Source repository against the disposable database: register / get / update / (de)activate."""

import inspect
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.v2.domain.errors import InvalidInputError, InvariantViolationError, UnsupportedInputError
from app.v2.domain.source import CollectionMethod, Source, SourceType, StoredSource
from app.v2.repositories import sources as repo
from app.v2.repositories.errors import ConflictError, NotFoundError

pytestmark = pytest.mark.db


def make_source(**overrides) -> Source:
    base = dict(source_key="sec_edgar", name="SEC EDGAR", source_type=SourceType.GOVERNMENT_REGULATORY,
                collection_method=CollectionMethod.API, url="https://www.sec.gov/edgar", is_active=True)
    base.update(overrides)
    return Source(**base)


def raw_row(engine, key="sec_edgar"):
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT * FROM v2.source WHERE source_key = :k"), {"k": key}).mappings().one())


# ---------------- registration and retrieval

def test_register_a_valid_source(migrated_db):
    result = repo.register_source(migrated_db, make_source())
    assert result.created is True
    stored = result.stored
    assert isinstance(stored, StoredSource) and stored.id >= 1
    assert stored.source == make_source()
    assert stored.updated_time == stored.recorded_time


def test_persisted_values_round_trip_into_the_accepted_domain_model(migrated_db):
    original = make_source(name="Ünïcode Name ✓", url="http://example.com:8080/a?b=c#d", is_active=False)
    stored = repo.register_source(migrated_db, original).stored
    assert isinstance(stored.source, Source) and stored.source == original
    assert isinstance(stored.source.source_type, SourceType) and isinstance(stored.source.collection_method, CollectionMethod)
    assert repo.get_source_by_key(migrated_db, "sec_edgar").source == original


def test_retrieve_by_internal_id_and_by_source_key(migrated_db):
    stored = repo.register_source(migrated_db, make_source()).stored
    assert repo.get_source_by_id(migrated_db, stored.id) == stored
    assert repo.get_source_by_key(migrated_db, "sec_edgar") == stored


def test_missing_sources_are_none_not_errors(migrated_db):
    assert repo.get_source_by_id(migrated_db, 12345) is None
    assert repo.get_source_by_key(migrated_db, "no_such_source") is None


@pytest.mark.parametrize("bad", [0, -1, "1", None, 1.0, True])
def test_get_by_id_validates_its_argument(migrated_db, bad):
    with pytest.raises(InvalidInputError):
        repo.get_source_by_id(migrated_db, bad)


@pytest.mark.parametrize("bad", ["", "Bad Key", "x" * 65, None, 5])
def test_get_by_key_validates_its_argument(migrated_db, bad):
    with pytest.raises(InvalidInputError):
        repo.get_source_by_key(migrated_db, bad)


@pytest.mark.parametrize("source_type", list(SourceType))
def test_every_source_type_persists(migrated_db, source_type):
    stored = repo.register_source(migrated_db, make_source(source_type=source_type)).stored
    assert repo.get_source_by_key(migrated_db, "sec_edgar").source.source_type is source_type == stored.source.source_type


@pytest.mark.parametrize("method", list(CollectionMethod))
def test_every_collection_method_persists(migrated_db, method):
    stored = repo.register_source(migrated_db, make_source(collection_method=method)).stored
    assert repo.get_source_by_id(migrated_db, stored.id).source.collection_method is method


def test_a_source_without_a_url_persists_as_null(migrated_db):
    stored = repo.register_source(migrated_db, make_source(url=None)).stored
    assert stored.source.url is None and raw_row(migrated_db)["source_url"] is None


def test_register_requires_a_source(migrated_db):
    with pytest.raises(InvalidInputError):
        repo.register_source(migrated_db, {"source_key": "sec_edgar"})


def test_list_sources_is_ordered_and_can_filter_active(migrated_db):
    for key, active in (("b_source", True), ("a_source", False), ("c_source", True)):
        repo.register_source(migrated_db, make_source(source_key=key, is_active=active))
    assert [s.source.source_key for s in repo.list_sources(migrated_db)] == ["a_source", "b_source", "c_source"]
    assert [s.source.source_key for s in repo.list_sources(migrated_db, active_only=True)] == ["b_source", "c_source"]


# ---------------- identity and duplicate registration

def test_registering_the_same_source_again_is_idempotent_and_returns_the_existing_one(migrated_db):
    first = repo.register_source(migrated_db, make_source())
    again = repo.register_source(migrated_db, make_source())
    assert (first.created, again.created) == (True, False)
    assert again.stored == first.stored
    assert len(repo.list_sources(migrated_db)) == 1


def test_replay_never_rewrites_existing_mutable_fields(migrated_db):
    repo.register_source(migrated_db, make_source())
    repo.update_source_metadata(migrated_db, "sec_edgar", name="Renamed by an admin")
    replay = repo.register_source(migrated_db, make_source(name="SEC EDGAR", url=None, is_active=False))
    assert replay.created is False
    assert replay.stored.source.name == "Renamed by an admin"          # not rewritten by the replay
    assert replay.stored.source.url == "https://www.sec.gov/edgar" and replay.stored.source.is_active is True


@pytest.mark.parametrize("override", [{"source_type": SourceType.RESEARCH}, {"collection_method": CollectionMethod.FEED}])
def test_conflicting_immutable_identity_fails_clearly_and_changes_nothing(migrated_db, override):
    repo.register_source(migrated_db, make_source())
    before = raw_row(migrated_db)
    with pytest.raises(ConflictError) as info:
        repo.register_source(migrated_db, make_source(**override))
    assert info.value.code == "source_identity_conflict"
    assert raw_row(migrated_db) == before


def test_source_name_is_not_identity(migrated_db):
    a = repo.register_source(migrated_db, make_source(source_key="alpha_source", name="Same Name")).stored
    b = repo.register_source(migrated_db, make_source(source_key="beta_source", name="Same Name")).stored
    assert a.id != b.id and a.source.name == b.source.name


def test_source_url_is_not_identity(migrated_db):
    a = repo.register_source(migrated_db, make_source(source_key="alpha_source", url="https://same.example.com")).stored
    b = repo.register_source(migrated_db, make_source(source_key="beta_source", url="https://same.example.com")).stored
    assert a.id != b.id


def test_same_key_with_a_different_name_and_url_is_the_same_source(migrated_db):
    a = repo.register_source(migrated_db, make_source()).stored
    b = repo.register_source(migrated_db, make_source(name="Other Name", url="https://other.example.com")).stored
    assert a.id == b.id


def test_concurrent_registration_of_one_key_creates_exactly_one_source(migrated_db):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: repo.register_source(migrated_db, make_source()), range(16)))
    assert sum(r.created for r in results) == 1
    assert len({r.stored.id for r in results}) == 1
    assert len(repo.list_sources(migrated_db)) == 1


# ---------------- mutability

def test_source_name_can_change(migrated_db):
    repo.register_source(migrated_db, make_source())
    updated = repo.update_source_metadata(migrated_db, "sec_edgar", name="SEC EDGAR (renamed)")
    assert updated.source.name == "SEC EDGAR (renamed)"
    assert updated.source.url == "https://www.sec.gov/edgar"  # untouched


def test_source_url_can_change_and_be_cleared(migrated_db):
    repo.register_source(migrated_db, make_source())
    assert repo.update_source_metadata(migrated_db, "sec_edgar", url="https://efts.sec.gov/").source.url == "https://efts.sec.gov/"
    cleared = repo.update_source_metadata(migrated_db, "sec_edgar", url=None)
    assert cleared.source.url is None and cleared.source.name == "SEC EDGAR"


def test_source_can_be_deactivated_and_reactivated_and_nothing_else_changes(migrated_db):
    created = repo.register_source(migrated_db, make_source()).stored
    off = repo.deactivate_source(migrated_db, "sec_edgar")
    assert off.source.is_active is False
    assert off.source.model_copy(update={"is_active": True}) == created.source  # only is_active moved
    assert off.id == created.id
    on = repo.reactivate_source(migrated_db, "sec_edgar")
    assert on.source == created.source and on.id == created.id


def test_updated_time_advances_on_change_and_recorded_time_never_moves(migrated_db):
    created = repo.register_source(migrated_db, make_source()).stored
    renamed = repo.update_source_metadata(migrated_db, "sec_edgar", name="A new name")
    off = repo.deactivate_source(migrated_db, "sec_edgar")
    assert created.updated_time < renamed.updated_time < off.updated_time
    assert created.recorded_time == renamed.recorded_time == off.recorded_time


def test_no_op_updates_do_not_move_updated_time(migrated_db):
    created = repo.register_source(migrated_db, make_source()).stored
    assert repo.update_source_metadata(migrated_db, "sec_edgar") == created                       # nothing requested
    assert repo.update_source_metadata(migrated_db, "sec_edgar", name="SEC EDGAR") == created     # same value
    assert repo.reactivate_source(migrated_db, "sec_edgar") == created                            # already active
    off = repo.deactivate_source(migrated_db, "sec_edgar")
    assert repo.deactivate_source(migrated_db, "sec_edgar") == off                                # idempotent


def test_timestamps_are_database_assigned_and_utc(migrated_db):
    stored = repo.register_source(migrated_db, make_source()).stored
    assert stored.recorded_time.tzinfo is timezone.utc
    assert abs(datetime.now(timezone.utc) - stored.recorded_time) < timedelta(minutes=5)


def test_updating_an_unknown_source_is_not_found(migrated_db):
    for call in (lambda: repo.update_source_metadata(migrated_db, "ghost_source", name="x"),
                 lambda: repo.deactivate_source(migrated_db, "ghost_source"),
                 lambda: repo.reactivate_source(migrated_db, "ghost_source"),
                 lambda: repo.update_source_metadata(migrated_db, "ghost_source")):
        with pytest.raises(NotFoundError) as info:
            call()
        assert info.value.code == "source_not_found"


def test_invalid_updates_are_rejected_before_touching_the_row(migrated_db):
    created = repo.register_source(migrated_db, make_source()).stored
    for kwargs, error in (({"name": " padded "}, InvalidInputError), ({"name": ""}, InvalidInputError),
                          ({"url": "ftp://example.com"}, UnsupportedInputError),
                          ({"url": "https://u:p@example.com"}, InvalidInputError),
                          ({"name": None}, InvalidInputError)):
        with pytest.raises(error):
            repo.update_source_metadata(migrated_db, "sec_edgar", **kwargs)
    assert repo.get_source_by_key(migrated_db, "sec_edgar") == created


def test_the_update_api_offers_no_way_to_change_immutable_fields():
    params = set(inspect.signature(repo.update_source_metadata).parameters)
    assert params == {"db", "source_key", "name", "url"}
    with pytest.raises(TypeError):
        repo.update_source_metadata(None, "sec_edgar", source_type=SourceType.OTHER)  # type: ignore[call-arg]


# ---------------- no delete

def test_repository_exposes_no_delete_operation():
    public = {n for n, v in vars(repo).items() if callable(v) and not n.startswith("_") and getattr(v, "__module__", "") == repo.__name__}
    assert public == {"register_source", "get_source_by_id", "get_source_by_key", "list_sources",
                      "update_source_metadata", "deactivate_source", "reactivate_source", "RegistrationResult"}
    assert not any(word in name.lower() for name in public for word in ("delete", "remove", "drop", "purge", "truncate", "destroy"))
    source_text = inspect.getsource(repo).lower()
    assert "delete(" not in source_text and "delete from" not in source_text


def test_deactivation_preserves_the_row_and_its_history(migrated_db):
    created = repo.register_source(migrated_db, make_source()).stored
    repo.deactivate_source(migrated_db, "sec_edgar")
    row = raw_row(migrated_db)
    assert row["id"] == created.id and row["is_active"] is False and row["created_at"] == created.recorded_time
    assert [s.id for s in repo.list_sources(migrated_db)] == [created.id]
    assert repo.list_sources(migrated_db, active_only=True) == []
    assert repo.get_source_by_id(migrated_db, created.id).source.is_active is False


# ---------------- transactions and error translation

def test_a_connection_joins_the_callers_transaction_and_can_be_rolled_back(migrated_db):
    with migrated_db.connect() as conn:
        transaction = conn.begin()
        repo.register_source(conn, make_source())
        assert repo.get_source_by_key(conn, "sec_edgar") is not None
        transaction.rollback()
    assert repo.get_source_by_key(migrated_db, "sec_edgar") is None


def test_database_rejections_are_translated_without_leaking_data(migrated_db):
    secret = "SECRET-NAME-Zq93"
    unvalidated = Source.model_construct(source_key="sec_edgar", name=f"  {secret}  ", source_type=SourceType.OTHER,
                                         collection_method=CollectionMethod.API, url=None, is_active=True)  # bypasses domain validation
    with pytest.raises(InvariantViolationError) as info:
        repo.register_source(migrated_db, unvalidated)
    assert info.value.code == "persistence_constraint_violation"
    assert "ck_source_source_name_valid" in info.value.message
    assert secret not in str(info.value) and secret not in repr(info.value)
    assert repo.get_source_by_key(migrated_db, "sec_edgar") is None


def test_a_stored_row_that_violates_the_domain_model_is_reported_not_returned(migrated_db):
    # The database's btrim only trims spaces; the domain also rejects other surrounding whitespace.
    with migrated_db.begin() as conn:
        conn.execute(text("INSERT INTO v2.source (source_key, source_name, source_type, collection_method, is_active) "
                          "VALUES ('odd_source', :n, 'other', 'api', true)"), {"n": " padded"})
    with pytest.raises(InvariantViolationError) as info:
        repo.get_source_by_key(migrated_db, "odd_source")
    assert info.value.code == "stored_source_invalid" and "padded" not in str(info.value)
