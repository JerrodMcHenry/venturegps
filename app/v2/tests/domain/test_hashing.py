import hashlib
import unicodedata

import pytest

from app.v2.domain.content import validate_content_hash
from app.v2.domain.errors import InvalidInputError
from app.v2.observations.hashing import compute_content_hash

# Published SHA-256 test vectors.
VECTORS = [
    (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
    (b"hello world", "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"),
    (b"The quick brown fox jumps over the lazy dog", "d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592"),
    (b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq", "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
]


@pytest.mark.parametrize("data, expected", VECTORS)
def test_known_sha256_vectors(data, expected):
    assert compute_content_hash(data) == expected


def test_one_million_a_vector():
    assert compute_content_hash(b"a" * 1_000_000) == "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"


def test_empty_bytes_are_hashed_deterministically():
    assert compute_content_hash(b"") == compute_content_hash(b"") == hashlib.sha256(b"").hexdigest()


def test_same_bytes_same_hash_changed_bytes_different_hash():
    assert compute_content_hash(b"payload") == compute_content_hash(b"payload")
    assert compute_content_hash(b"payload") != compute_content_hash(b"payloae")
    assert compute_content_hash(b"payload") != compute_content_hash(b"payload ")
    assert compute_content_hash(b"payload") != compute_content_hash(b"payload\x00")
    assert compute_content_hash(b"ab") != compute_content_hash(b"ba")


def test_output_is_lowercase_hex_of_length_64():
    result = compute_content_hash(b"x")
    assert len(result) == 64 and result == result.lower() and validate_content_hash(result) == result


def test_hash_does_not_depend_on_text_decoding_or_normalization():
    invalid_utf8 = b"\xff\xfe\x00\x80"
    assert compute_content_hash(invalid_utf8) == hashlib.sha256(invalid_utf8).hexdigest()
    assert compute_content_hash(b"a\r\nb") != compute_content_hash(b"a\nb")            # no newline normalization
    assert compute_content_hash(b"\xef\xbb\xbfabc") != compute_content_hash(b"abc")   # BOM is content
    assert compute_content_hash(b"abc ") != compute_content_hash(b"abc")              # no trimming


def test_unicode_hashes_the_exact_bytes_supplied_not_a_re_encoding():
    text = "café"
    assert compute_content_hash(text.encode("utf-8")) == hashlib.sha256(b"caf\xc3\xa9").hexdigest()
    assert compute_content_hash(text.encode("utf-8")) != compute_content_hash(text.encode("latin-1"))
    assert compute_content_hash(text.encode("utf-8")) != compute_content_hash(text.encode("utf-16"))
    nfc = unicodedata.normalize("NFC", "é").encode()
    nfd = unicodedata.normalize("NFD", "é").encode()
    assert nfc != nfd and compute_content_hash(nfc) != compute_content_hash(nfd)       # no Unicode normalization


@pytest.mark.parametrize("wrapper", [bytes, bytearray, memoryview])
def test_bytes_like_inputs_hash_identically(wrapper):
    assert compute_content_hash(wrapper(b"abc")) == VECTORS[1][1]


@pytest.mark.parametrize("value", ["abc", "", None, 5, ["abc"], object()])
def test_text_and_non_bytes_are_refused_not_silently_encoded(value):
    with pytest.raises(InvalidInputError) as info:
        compute_content_hash(value)
    assert info.value.code == "content_must_be_bytes"


GOOD = VECTORS[0][1]


@pytest.mark.parametrize("value", [GOOD.upper(), GOOD[:-1], GOOD + "0", "g" * 64, " " + GOOD[1:], GOOD + "\n", "", None, 12, GOOD.encode()])
def test_content_hash_validation_rejects_malformed_values(value):
    with pytest.raises(InvalidInputError) as info:
        validate_content_hash(value)
    assert info.value.code == "invalid_content_hash"


def test_content_hash_validation_accepts_a_real_hash():
    assert validate_content_hash(GOOD) == GOOD
