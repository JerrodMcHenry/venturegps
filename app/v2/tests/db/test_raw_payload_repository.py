"""RawPayload persistence: exact bytes, content addressing, size policy, hash verification."""

import hashlib
import inspect
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.exc import IntegrityError

from app.v2.domain.errors import InvalidInputError, InvariantViolationError, UnsupportedInputError
from app.v2.domain.payload import MAX_INLINE_PAYLOAD_BYTES, RawPayload, StorageKind
from app.v2.repositories import raw_payloads as repo
from app.v2.tests.db.evidence_helpers import count, fetch_row, refused, tamper_payload

pytestmark = pytest.mark.db

ABC_HASH = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
EMPTY_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

AWKWARD_PAYLOADS = {
    "all_256_byte_values": bytes(range(256)),
    "crlf": b"line1\r\nline2\r\n",
    "lone_cr": b"a\rb",
    "trailing_whitespace": b"text   \n\n",
    "bom": b"\xef\xbb\xbf{\"a\": 1}",
    "nul_bytes": b"a\x00b\x00",
    "invalid_utf8": b"\xff\xfe\xfa\x80",
    "pretty_json_vs_compact": b'{ "a" :   1 }',
    "pdf_like": b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\nstream\x00\x01\x02",
    "html_with_script": b"<html><script>alert('x')</script></html>",
    "utf16": "café".encode("utf-16"),
}


def test_known_sha256_and_exact_round_trip(migrated_db):
    result = repo.store_raw_payload(migrated_db, b"abc")
    assert result.created is True and result.payload.content_hash == ABC_HASH
    loaded = repo.get_raw_payload(migrated_db, ABC_HASH)
    assert loaded == result.payload and loaded.payload_bytes == b"abc" and loaded.storage_kind is StorageKind.INLINE
    row = fetch_row(migrated_db, "raw_payload", "content_hash = :h", {"h": ABC_HASH})
    assert row["size_bytes"] == 3 and row["storage_kind"] == "inline" and bytes(row["payload_bytes"]) == b"abc"


@pytest.mark.parametrize("name", list(AWKWARD_PAYLOADS))
def test_awkward_bytes_round_trip_exactly_and_hash_is_of_the_exact_bytes(migrated_db, name):
    data = AWKWARD_PAYLOADS[name]
    stored = repo.store_raw_payload(migrated_db, data).payload
    assert stored.content_hash == hashlib.sha256(data).hexdigest()
    loaded = repo.get_raw_payload(migrated_db, stored.content_hash)
    assert loaded.payload_bytes == data                                                    # byte-for-byte: no normalization
    assert hashlib.sha256(bytes(fetch_row(migrated_db, "raw_payload", "content_hash = :h", {"h": stored.content_hash})["payload_bytes"])).hexdigest() == stored.content_hash


def test_normalization_variants_are_different_payloads(migrated_db):
    variants = [b"a\r\nb", b"a\nb", b'{"a":1}', b'{ "a" : 1 }', "é".encode(), "é".encode(), b"abc", b"abc "]
    hashes = {repo.store_raw_payload(migrated_db, v).payload.content_hash for v in variants}
    assert len(hashes) == len(variants) and count(migrated_db, "raw_payload") == len(variants)


def test_identical_bytes_reuse_the_same_payload(migrated_db):
    first = repo.store_raw_payload(migrated_db, b"same bytes")
    again = repo.store_raw_payload(migrated_db, bytearray(b"same bytes"))
    assert (first.created, again.created) == (True, False) and again.payload == first.payload
    assert count(migrated_db, "raw_payload") == 1


def test_changed_bytes_produce_a_different_payload(migrated_db):
    a = repo.store_raw_payload(migrated_db, b"payload").payload
    b = repo.store_raw_payload(migrated_db, b"payloae").payload
    assert a.content_hash != b.content_hash and count(migrated_db, "raw_payload") == 2


def test_empty_evidence_is_permitted(migrated_db):
    result = repo.store_raw_payload(migrated_db, b"")
    assert result.payload.content_hash == EMPTY_HASH
    loaded = repo.get_raw_payload(migrated_db, EMPTY_HASH)
    assert loaded.payload_bytes == b"" and loaded.size_bytes == 0


def test_the_maximum_payload_is_accepted_and_one_byte_more_is_rejected(migrated_db):
    biggest = bytes(i % 251 for i in range(MAX_INLINE_PAYLOAD_BYTES))
    stored = repo.store_raw_payload(migrated_db, biggest).payload
    assert stored.size_bytes == MAX_INLINE_PAYLOAD_BYTES
    assert repo.get_raw_payload(migrated_db, stored.content_hash).payload_bytes == biggest

    with pytest.raises(UnsupportedInputError) as info:
        repo.store_raw_payload(migrated_db, biggest + b"x")
    assert info.value.code == "payload_too_large"
    assert count(migrated_db, "raw_payload") == 1  # nothing was truncated or stored


def test_the_database_also_enforces_the_size_limit(migrated_db):
    too_big = b"x" * (MAX_INLINE_PAYLOAD_BYTES + 1)
    diag, _ = refused(migrated_db, "INSERT INTO v2.raw_payload (content_hash, storage_kind, size_bytes, payload_bytes) VALUES (:h, 'inline', :n, :b)",
                      {"h": hashlib.sha256(too_big).hexdigest(), "n": len(too_big), "b": too_big}, exc=IntegrityError)
    assert diag.constraint_name == "ck_raw_payload_size_within_limit"


@pytest.mark.parametrize("value", ["abc", None, 5, ["abc"]])
def test_only_bytes_can_be_stored(migrated_db, value):
    with pytest.raises(InvalidInputError):
        repo.store_raw_payload(migrated_db, value)


@pytest.mark.parametrize("bad", ["0" * 63, "G" * 64, ABC_HASH.upper(), "", None, 5])
def test_get_rejects_a_malformed_hash(migrated_db, bad):
    with pytest.raises(InvalidInputError):
        repo.get_raw_payload(migrated_db, bad)


def test_get_of_an_unknown_hash_is_none(migrated_db):
    assert repo.get_raw_payload(migrated_db, "0" * 64) is None


# ---------------- database integrity (direct SQL)

def raw_insert(engine, **overrides):
    values = dict(content_hash=ABC_HASH, storage_kind="inline", size_bytes=3, payload_bytes=b"abc")
    values.update(overrides)
    return refused(engine, "INSERT INTO v2.raw_payload (content_hash, storage_kind, size_bytes, payload_bytes) "
                           "VALUES (:content_hash, :storage_kind, :size_bytes, :payload_bytes)", values, exc=IntegrityError)


@pytest.mark.parametrize("bad", ["0" * 63, "0" * 65, "G" * 64, ABC_HASH.upper(), "", ABC_HASH + "\n"])
def test_malformed_hash_is_rejected_by_the_database(migrated_db, bad):
    diag, _ = raw_insert(migrated_db, content_hash=bad)
    assert diag.constraint_name in ("ck_raw_payload_content_hash_shape", "ck_raw_payload_hash_matches_bytes")


def test_a_hash_that_does_not_match_the_bytes_is_rejected_by_the_database(migrated_db):
    diag, _ = raw_insert(migrated_db, content_hash="0" * 64)
    assert diag.constraint_name == "ck_raw_payload_hash_matches_bytes"
    assert count(migrated_db, "raw_payload") == 0


def test_size_must_match_the_bytes_and_be_non_negative(migrated_db):
    assert raw_insert(migrated_db, size_bytes=4)[0].constraint_name == "ck_raw_payload_size_matches_bytes"
    # -1 breaks two CHECKs; PostgreSQL reports whichever it evaluates first
    assert raw_insert(migrated_db, size_bytes=-1)[0].constraint_name in ("ck_raw_payload_size_within_limit", "ck_raw_payload_size_matches_bytes")


def test_inline_storage_requires_bytes_and_only_inline_is_allowed(migrated_db):
    assert raw_insert(migrated_db, payload_bytes=None)[0].constraint_name == "ck_raw_payload_inline_bytes_present"
    assert raw_insert(migrated_db, storage_kind="external")[0].constraint_name in ("ck_raw_payload_storage_kind_allowed", "ck_raw_payload_inline_bytes_present")
    assert raw_insert(migrated_db, storage_kind="s3")[0].constraint_name in ("ck_raw_payload_storage_kind_allowed", "ck_raw_payload_inline_bytes_present")


def test_not_null_columns(migrated_db):
    for column in ("content_hash", "storage_kind", "size_bytes"):
        diag, _ = raw_insert(migrated_db, **{column: None})
        assert diag.column_name == column or diag.constraint_name


# ---------------- verification and tampering

def test_tampered_bytes_are_detected_on_read_and_never_repaired(migrated_db):
    stored = repo.store_raw_payload(migrated_db, b"original evidence").payload
    tampered = b"tampered evidence"
    assert len(tampered) == len(b"original evidence")  # same length: only the hash gives it away
    tamper_payload(migrated_db, stored.content_hash, new_bytes=tampered)
    with pytest.raises(InvariantViolationError) as info:
        repo.get_raw_payload(migrated_db, stored.content_hash)
    assert info.value.code == "payload_hash_mismatch" and "tampered" not in str(info.value)
    # still corrupted afterwards: nothing repaired it, and the audit escape hatch can still inspect it
    assert repo.get_raw_payload(migrated_db, stored.content_hash, verify=False).payload_bytes == tampered


def test_a_wrong_recorded_size_is_detected(migrated_db):
    stored = repo.store_raw_payload(migrated_db, b"abcdef").payload
    tamper_payload(migrated_db, stored.content_hash, new_size=99)
    with pytest.raises(InvariantViolationError) as info:
        repo.get_raw_payload(migrated_db, stored.content_hash)
    assert info.value.code == "payload_size_mismatch"


def test_reads_verify_by_default(migrated_db):
    assert inspect.signature(repo.get_raw_payload).parameters["verify"].default is True


# ---------------- API surface and concurrency

def test_the_repository_offers_no_update_or_delete_and_no_way_to_supply_a_hash():
    public = {n for n, v in vars(repo).items() if callable(v) and not n.startswith("_") and getattr(v, "__module__", "") == repo.__name__}
    assert public == {"store_raw_payload", "get_raw_payload", "PayloadStoreResult"}
    assert list(inspect.signature(repo.store_raw_payload).parameters) == ["db", "data"]
    source = inspect.getsource(repo).lower()
    assert "delete(" not in source and "delete from" not in source and ".update(" not in source and "update(" not in source


def test_concurrent_stores_of_identical_bytes_create_exactly_one_payload(migrated_db):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: repo.store_raw_payload(migrated_db, b"raced bytes"), range(16)))
    assert sum(r.created for r in results) == 1 and len({r.payload.content_hash for r in results}) == 1
    assert count(migrated_db, "raw_payload") == 1


def test_a_payload_model_round_trips_through_storage(migrated_db):
    stored = repo.store_raw_payload(migrated_db, b"x").payload
    assert isinstance(repo.get_raw_payload(migrated_db, stored.content_hash), RawPayload)
